"""Audiencia latente, expectativas, rating y respuesta RCP."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from .arithmetic import clamp, round_half_up_ratio
from .business_calendar import BusinessCalendar
from .failure_model import derive_domain_key, draw_occurs, hmac_u64
from .models import ShipmentRecord


@dataclass(frozen=True, slots=True)
class OpinionOutcome:
    audience: str
    eligible: bool
    submitted: bool
    rating: int
    impact_weight_bps: int


def response_probability_bps(
    rating: int, audience: str, rules: Mapping[str, object]
) -> int:
    profile = rules["rcp"]["audience"][audience]
    return clamp(
        int(profile["base_response_bps"])
        + round_half_up_ratio(
            int(profile["dissatisfaction_uplift_bps"]) * (10 - rating), 9
        )
    )


def audience_for(shipment: ShipmentRecord, rules: Mapping[str, object], key: bytes) -> str:
    if shipment.product == "VIP_BLACK":
        return "VIP"
    rate = int(rules["rcp"]["influencer_rate_bps"])
    return (
        "INFLUENCER"
        if draw_occurs(
            hmac_u64(
                derive_domain_key(key, "influencer-v1"),
                f"influencer|{shipment.shipment_id}",
            ),
            rate,
        )
        else "NORMAL"
    )


def expectation_bps(shipment: ShipmentRecord, rules: Mapping[str, object], key: bytes) -> int:
    profile = rules["rcp"]["expectation"][shipment.product]
    low = int(profile["min_full_satisfaction_ratio_bps"])
    high = int(profile["max_full_satisfaction_ratio_bps"])
    return low + hmac_u64(
        derive_domain_key(key, "expectation-v1"),
        f"expectation|{shipment.shipment_id}",
    ) % (high - low + 1)


def delivered_rating(
    shipment: ShipmentRecord,
    delivered_at: datetime,
    calendar: BusinessCalendar,
    x_bps: int,
) -> int:
    elapsed, duration = calendar.ratio_parts(
        shipment.available_at, delivered_at, shipment.product
    )
    q_scaled = elapsed * 10_000
    if q_scaled <= duration * x_bps:
        return 10
    if elapsed <= duration:
        denominator = duration * (10_000 - x_bps)
        distance = q_scaled - duration * x_bps
        return round_half_up_ratio(10 * denominator - 4 * distance, denominator)
    if 2 * elapsed <= 3 * duration:
        return round_half_up_ratio(14 * duration - 8 * elapsed, duration)
    return 2


def evaluate_opinion(
    shipment: ShipmentRecord,
    delivered_at: datetime | None,
    calendar: BusinessCalendar,
    rules: Mapping[str, object],
    opinion_key: bytes,
) -> OpinionOutcome:
    audience = audience_for(shipment, rules, opinion_key)
    profile = rules["rcp"]["audience"][audience]
    weight = int(profile["impact_weight_bps"])
    if delivered_at is None:
        return OpinionOutcome(audience, True, True, int(rules["rcp"]["undelivered_rating"]), weight)
    x_bps = expectation_bps(shipment, rules, opinion_key)
    rating = delivered_rating(shipment, delivered_at, calendar, x_bps)
    probability = response_probability_bps(rating, audience, rules)
    submitted = draw_occurs(
        hmac_u64(
            derive_domain_key(opinion_key, "opinion-v1"),
            f"opinion|{shipment.shipment_id}",
        ),
        probability,
    )
    return OpinionOutcome(audience, True, submitted, rating, weight)
