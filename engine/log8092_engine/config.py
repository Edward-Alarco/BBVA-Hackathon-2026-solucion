"""Carga estricta de los cinco inputs publicos y la clave privada opcional."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import hashlib
import json
from pathlib import Path
import tomllib
from typing import Iterator, Mapping

from .business_calendar import BusinessCalendar, SlaRule
from .models import CarrierDefinition, ShipmentInput


SPEC_VERSION = "0.4.0"
SHIPMENT_HEADER = (
    "shipment_id",
    "available_at",
    "product",
    "zone",
    "delivery_cluster_id",
    "is_metal",
)


class ConfigurationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ScenarioConfig:
    scenario_id: str
    simulation_start: datetime
    admission_days: int
    reference_budget_cents: int
    resource_profile: str
    upgrades_enabled: bool
    seed_fingerprint: str

    @property
    def admission_end(self) -> datetime:
        return self.simulation_start + timedelta(days=self.admission_days)


@dataclass(frozen=True, slots=True)
class SecretConfig:
    failure_key: bytes
    opinion_key: bytes


@dataclass(frozen=True, slots=True)
class EngineConfig:
    data_dir: Path
    scenario: ScenarioConfig
    rules: Mapping[str, object]
    carriers: tuple[CarrierDefinition, ...]
    holidays: frozenset[date]
    calendar: BusinessCalendar
    secrets: SecretConfig


def _aware_second(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ConfigurationError(f"{field}: datetime ISO invalido") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ConfigurationError(f"{field}: se requiere offset de zona")
    if parsed.microsecond:
        raise ConfigurationError(f"{field}: precision superior a un segundo")
    return parsed


def _load_holidays(path: Path) -> frozenset[date]:
    values: list[date] = []
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != ("date", "name"):
            raise ConfigurationError("holidays.csv: cabecera invalida")
        for row in reader:
            try:
                value = date.fromisoformat(row["date"])
            except ValueError as exc:
                raise ConfigurationError("holidays.csv: fecha invalida") from exc
            values.append(value)
    if len(values) != len(set(values)):
        raise ConfigurationError("holidays.csv: fecha duplicada")
    if values != sorted(values):
        raise ConfigurationError("holidays.csv: fechas no ordenadas")
    return frozenset(values)


def _load_carriers(path: Path, rules: Mapping[str, object]) -> tuple[CarrierDefinition, ...]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != "0.2.0" or not isinstance(raw.get("carriers"), list):
        raise ConfigurationError("carriers.json: schema no soportado")
    zones = set(rules["distances_km"])
    known_upgrades = set(rules["upgrades"])
    result: list[CarrierDefinition] = []
    ids: set[str] = set()
    for item in raw["carriers"]:
        carrier_id = str(item["carrier_id"])
        if carrier_id in ids:
            raise ConfigurationError(f"carrier duplicado: {carrier_id}")
        ids.add(carrier_id)
        allowed = tuple(str(zone) for zone in item["allowed_zones"])
        prices = {str(k): int(v) for k, v in item["zone_surcharge_cents"].items()}
        if not allowed or any(zone not in zones for zone in allowed):
            raise ConfigurationError(f"{carrier_id}: zonas invalidas")
        if any(zone not in prices for zone in allowed):
            raise ConfigurationError(f"{carrier_id}: falta un recargo de zona")
        supported = tuple(str(value) for value in item.get("supported_upgrades", ()))
        if any(value not in known_upgrades for value in supported):
            raise ConfigurationError(f"{carrier_id}: upgrade desconocido")
        positive = ("fleet_units", "batch_capacity", "speed_kmh")
        if any(int(item[name]) <= 0 for name in positive):
            raise ConfigurationError(f"{carrier_id}: capacidad no positiva")
        result.append(CarrierDefinition(
            carrier_id=carrier_id,
            display_name=str(item["display_name"]),
            allowed_zones=allowed,
            capabilities=tuple(str(v) for v in item.get("capabilities", ())),
            fleet_units=int(item["fleet_units"]),
            batch_capacity=int(item["batch_capacity"]),
            pickup_minutes=int(item["pickup_minutes"]),
            speed_kmh=int(item["speed_kmh"]),
            base_fee_cents=int(item["base_fee_cents"]),
            zone_surcharge_cents=prices,
            night_multiplier_bps=int(item["night_multiplier_bps"]),
            holiday_multiplier_bps=int(item["holiday_multiplier_bps"]),
            operates_sundays=bool(item["operates_sundays"]),
            operates_holidays=bool(item["operates_holidays"]),
            operational_failure_bps=int(item["operational_failure_bps"]),
            supported_upgrades=supported,
        ))
    if not (1 <= len(result) <= int(rules["scenario_ranges"]["max_carriers"])):
        raise ConfigurationError("cantidad de carriers invalida")
    return tuple(result)


def _development_secrets(fingerprint: str) -> SecretConfig:
    # El caso publico necesita ser ejecutable; estas claves no se usan al puntuar.
    root = hashlib.sha256(("log8092-public-demo|" + fingerprint).encode()).digest()
    return SecretConfig(
        failure_key=hashlib.sha256(root + b"|failure-v1").digest(),
        opinion_key=hashlib.sha256(root + b"|opinion-v1").digest(),
    )


def _load_secrets(path: Path | None, scenario_id: str, fingerprint: str) -> SecretConfig:
    if path is None:
        return _development_secrets(fingerprint)
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    if raw.get("scenario_id") != scenario_id:
        raise ConfigurationError("private config pertenece a otro escenario")
    try:
        return SecretConfig(
            failure_key=bytes.fromhex(raw["secrets"]["failure_key_hex"]),
            opinion_key=bytes.fromhex(raw["secrets"]["opinion_key_hex"]),
        )
    except (KeyError, ValueError) as exc:
        raise ConfigurationError("private config invalida") from exc


def load_config(data_dir: Path, private_path: Path | None = None) -> EngineConfig:
    data_dir = data_dir.resolve()
    required = ("scenario.toml", "rules.toml", "carriers.json", "holidays.csv", "shipments.csv")
    missing = [name for name in required if not (data_dir / name).is_file()]
    if missing:
        raise ConfigurationError(f"faltan inputs: {', '.join(missing)}")
    scenario_raw = tomllib.loads((data_dir / "scenario.toml").read_text(encoding="utf-8"))
    rules = tomllib.loads((data_dir / "rules.toml").read_text(encoding="utf-8"))
    if scenario_raw.get("spec_version") != SPEC_VERSION or rules.get("spec_version") != SPEC_VERSION:
        raise ConfigurationError("spec_version no soportada")
    scenario = ScenarioConfig(
        scenario_id=str(scenario_raw["scenario_id"]),
        simulation_start=_aware_second(str(scenario_raw["simulation_start"]), "simulation_start"),
        admission_days=int(scenario_raw["admission_days"]),
        reference_budget_cents=int(scenario_raw["reference_budget_cents"]),
        resource_profile=str(scenario_raw["resource_profile"]),
        upgrades_enabled=bool(scenario_raw["upgrades_enabled"]),
        seed_fingerprint=str(scenario_raw["seed_fingerprint"]),
    )
    if scenario.reference_budget_cents < 0:
        raise ConfigurationError("reference_budget_cents no puede ser negativo")
    if scenario.admission_days != int(rules["simulation"]["admission_days"]):
        raise ConfigurationError("admission_days difiere de rules.toml")
    holidays = _load_holidays(data_dir / "holidays.csv")
    sla_rules = {
        product: SlaRule.from_mapping(product, raw)
        for product, raw in rules["sla"].items()
    }
    calendar = BusinessCalendar(holidays, sla_rules)
    carriers = _load_carriers(data_dir / "carriers.json", rules)
    secrets = _load_secrets(private_path, scenario.scenario_id, scenario.seed_fingerprint)
    return EngineConfig(data_dir, scenario, rules, carriers, holidays, calendar, secrets)


def stream_shipments(config: EngineConfig) -> Iterator[ShipmentInput]:
    path = config.data_dir / "shipments.csv"
    products = set(config.rules["sla"])
    zones = set(config.rules["distances_km"])
    seen: set[str] = set()
    previous: tuple[datetime, str] | None = None
    count = 0
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != SHIPMENT_HEADER:
            raise ConfigurationError("shipments.csv: cabecera invalida")
        for line_number, row in enumerate(reader, start=2):
            shipment_id = row["shipment_id"]
            if not shipment_id or shipment_id in seen:
                raise ConfigurationError(f"shipments.csv:{line_number}: ID vacio o duplicado")
            seen.add(shipment_id)
            available = _aware_second(row["available_at"], f"shipments.csv:{line_number}")
            key = (available, shipment_id)
            if previous is not None and key < previous:
                raise ConfigurationError(f"shipments.csv:{line_number}: orden invalido")
            previous = key
            if not (config.scenario.simulation_start <= available < config.scenario.admission_end):
                raise ConfigurationError(f"shipments.csv:{line_number}: fuera de admision")
            product, zone = row["product"], row["zone"]
            if product not in products or zone not in zones:
                raise ConfigurationError(f"shipments.csv:{line_number}: enum invalido")
            if row["is_metal"] not in {"true", "false"}:
                raise ConfigurationError(f"shipments.csv:{line_number}: booleano invalido")
            count += 1
            if count > int(config.rules["simulation"]["max_shipments"]):
                raise ConfigurationError("shipments.csv supera max_shipments")
            yield ShipmentInput(
                shipment_id=shipment_id,
                available_at=available,
                sla_deadline=config.calendar.deadline(available, product),
                product=product,
                zone=zone,
                delivery_cluster_id=row["delivery_cluster_id"],
                is_metal=row["is_metal"] == "true",
            )
