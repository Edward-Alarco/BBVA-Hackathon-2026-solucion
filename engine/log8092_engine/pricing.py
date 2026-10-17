"""PRICE-001..010: calculo puro y exacto de cada lote."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Mapping, Sequence

from .arithmetic import round_half_up_ratio
from .models import CarrierDefinition, ShipmentRecord


@dataclass(frozen=True, slots=True)
class BatchPrice:
    adjusted_linehaul_cents: int
    additional_cards_cents: int
    metal_security_cents: int
    total_cents: int


def is_night(now: datetime, rules: Mapping[str, object]) -> bool:
    start_h, start_m = (int(x) for x in str(rules["pricing"]["night_start"]).split(":"))
    end_h, end_m = (int(x) for x in str(rules["pricing"]["night_end"]).split(":"))
    clock = now.timetz().replace(tzinfo=None)
    start, end = time(start_h, start_m), time(end_h, end_m)
    return clock >= start or clock < end


def time_multipliers(
    carrier: CarrierDefinition,
    now: datetime,
    holidays: frozenset,
    rules: Mapping[str, object],
) -> tuple[int, int]:
    night = carrier.night_multiplier_bps if is_night(now, rules) else 10_000
    calendar = (
        carrier.holiday_multiplier_bps
        if now.isoweekday() == 7 or now.date() in holidays
        else 10_000
    )
    return night, calendar


def current_time_multiplier_bps(
    carrier: CarrierDefinition,
    now: datetime,
    holidays: frozenset,
    rules: Mapping[str, object],
) -> int:
    night, calendar = time_multipliers(carrier, now, holidays, rules)
    return round_half_up_ratio(night * calendar, 10_000)


def price_batch(
    carrier: CarrierDefinition,
    shipments: Sequence[ShipmentRecord],
    now: datetime,
    holidays: frozenset,
    rules: Mapping[str, object],
) -> BatchPrice:
    if not shipments:
        raise ValueError("No se tarifa un lote vacio")
    attempt = shipments[0].attempt_number
    attempt_bps = int(rules["pricing"]["attempt_multipliers_bps"][attempt - 1])
    linehaul = carrier.base_fee_cents + carrier.zone_surcharge_cents[shipments[0].zone]
    night_bps, calendar_bps = time_multipliers(carrier, now, holidays, rules)
    adjusted = round_half_up_ratio(
        linehaul * attempt_bps * night_bps * calendar_bps,
        10_000**3,
    )
    additional = int(rules["pricing"]["additional_card_cents"]) * (len(shipments) - 1)
    metal = int(rules["pricing"]["metal_security_cents"]) * sum(s.is_metal for s in shipments)
    return BatchPrice(adjusted, additional, metal, adjusted + additional + metal)
