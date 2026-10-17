"""Realizaciones de entrega estables, privadas e independientes del orden."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import hmac
from typing import Mapping

from .arithmetic import clamp, round_half_up_ratio
from .models import CarrierDefinition, ShipmentRecord


U64_SPACE = 1 << 64


def hmac_u64(key: bytes, message: str) -> int:
    return int.from_bytes(hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()[:8], "big")


def derive_domain_key(root_key: bytes, label: str) -> bytes:
    return hmac.new(
        root_key,
        f"log8092|{label}|v0.4".encode("utf-8"),
        hashlib.sha256,
    ).digest()


def draw_occurs(draw: int, probability_bps: int) -> bool:
    return draw * 10_000 < probability_bps * U64_SPACE


@dataclass(frozen=True, slots=True)
class FailureProbabilities:
    inaccessible_route_bps: int
    customer_absence_bps: int
    operational_delay_bps: int


def effective_probabilities(
    shipment: ShipmentRecord,
    carrier: CarrierDefinition,
    dispatched_at: datetime,
    holidays: frozenset,
    rules: Mapping[str, object],
) -> FailureProbabilities:
    failure = rules["failure"]
    access = 0 if "HARD_ACCESS" in carrier.capabilities else int(
        failure["inaccessible_route_bps"][shipment.zone]
    )
    absence = clamp(
        int(failure["customer_absence_bps"][f"attempt_{shipment.attempt_number}"])
        + int(failure["zone_modifier_bps"][shipment.zone])
    )
    operation = carrier.operational_failure_bps
    if dispatched_at.isoweekday() == 7:
        operation += int(failure["calendar_modifier_bps"]["sunday"])
    if dispatched_at.date() in holidays:
        operation += int(failure["calendar_modifier_bps"]["holiday"])
    return FailureProbabilities(access, absence, clamp(operation))


def determine_failure(
    shipment: ShipmentRecord,
    carrier: CarrierDefinition,
    dispatched_at: datetime,
    holidays: frozenset,
    rules: Mapping[str, object],
    failure_key: bytes,
) -> str | None:
    p = effective_probabilities(shipment, carrier, dispatched_at, holidays, rules)
    identity = f"{shipment.shipment_id}|{shipment.attempt_number}"
    draws = (
        (
            "INACCESSIBLE_ROUTE", p.inaccessible_route_bps,
            derive_domain_key(failure_key, "access-v1"),
            f"access|{identity}|{carrier.carrier_id}",
        ),
        (
            "CUSTOMER_ABSENT", p.customer_absence_bps,
            derive_domain_key(failure_key, "absence-v1"),
            f"absence|{identity}",
        ),
        (
            "OPERATIONAL_DELAY", p.operational_delay_bps,
            derive_domain_key(failure_key, "operation-v1"),
            f"operation|{identity}|{carrier.carrier_id}",
        ),
    )
    for reason, probability, domain_key, message in draws:
        if draw_occurs(hmac_u64(domain_key, message), probability):
            return reason
    return None


def rolling_success_bps(results: list[bool]) -> int | None:
    if not results:
        return None
    tail = results[-200:]
    return round_half_up_ratio(sum(tail) * 10_000, len(tail))
