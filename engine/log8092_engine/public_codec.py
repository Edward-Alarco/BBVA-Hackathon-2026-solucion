"""Construccion centralizada de dataclasses del contrato publico."""

from __future__ import annotations

from datetime import datetime
import importlib
from typing import Mapping

from .models import ShipmentRecord


def api_module():
    return importlib.import_module("interfaces")


def shipment_view(record: ShipmentRecord):
    api = api_module()
    return api.Shipment(
        shipment_id=record.shipment_id,
        available_at=record.available_at,
        ready_at=record.ready_at,
        sla_deadline=record.sla_deadline,
        product=record.product,
        zone=record.zone,
        delivery_cluster_id=record.delivery_cluster_id,
        is_metal=record.is_metal,
        state=record.state,
        attempt_number=record.attempt_number,
        required_capabilities=tuple(sorted(record.required_capabilities)),
        retry_eligible_at=record.retry_eligible_at,
    )


def scenario_calendar(holidays: frozenset, timezone: str):
    api = api_module()
    return api.ScenarioCalendar(timezone=timezone, holidays=tuple(sorted(holidays)))


def failure_policy(rules: Mapping[str, object]):
    api = api_module()
    failure = rules["failure"]
    attempts = tuple(
        api.FailureAttemptRate(
            attempt_number=index,
            customer_absence_bps=int(failure["customer_absence_bps"][f"attempt_{index}"]),
        )
        for index in range(1, int(rules["retry"]["max_attempts"]) + 1)
    )
    zones = tuple(
        api.FailureZoneProfile(
            zone=zone,
            absence_modifier_bps=int(failure["zone_modifier_bps"][zone]),
            inaccessible_route_bps=int(failure["inaccessible_route_bps"][zone]),
        )
        for zone in rules["distances_km"]
    )
    return api.FailurePolicy(
        attempts=attempts,
        zones=zones,
        sunday_operation_modifier_bps=int(failure["calendar_modifier_bps"]["sunday"]),
        holiday_operation_modifier_bps=int(failure["calendar_modifier_bps"]["holiday"]),
    )


def rcp_policy(rules: Mapping[str, object]):
    api = api_module()
    rcp = rules["rcp"]
    expectations = tuple(
        api.RcpExpectationRange(
            product=product,
            min_full_satisfaction_ratio_bps=int(values["min_full_satisfaction_ratio_bps"]),
            max_full_satisfaction_ratio_bps=int(values["max_full_satisfaction_ratio_bps"]),
        )
        for product, values in rcp["expectation"].items()
    )
    audiences = tuple(
        api.RcpAudienceProfile(
            audience=audience,
            base_response_bps=int(values["base_response_bps"]),
            dissatisfaction_uplift_bps=int(values["dissatisfaction_uplift_bps"]),
            impact_weight_bps=int(values["impact_weight_bps"]),
        )
        for audience, values in rcp["audience"].items()
    )
    return api.RcpPolicy(
        influencer_rate_bps=int(rcp["influencer_rate_bps"]),
        undelivered_rating=int(rcp["undelivered_rating"]),
        delivered_floor_rating=int(rcp["delivered_floor_rating"]),
        on_time_boundary_rating=int(rcp["on_time_boundary_rating"]),
        late_floor_ratio_bps=int(rcp["late_floor_ratio_bps"]),
        expectations=expectations,
        audiences=audiences,
    )


def decision_policy(rules: Mapping[str, object]):
    api = api_module()
    pricing = rules["pricing"]
    return api.DecisionPolicy(
        admission_days=int(rules["simulation"]["admission_days"]),
        distances=tuple(
            api.ZoneDistance(zone=zone, distance_km=int(distance))
            for zone, distance in rules["distances_km"].items()
        ),
        sla=tuple(
            api.SlaDefinition(
                product=product,
                duration_minutes=int(values["duration_minutes"]),
                clock=str(values["clock"]),
                days=tuple(int(day) for day in values["days"]),
                open=str(values["open"]),
                close=str(values["close"]),
            )
            for product, values in rules["sla"].items()
        ),
        upgrades=tuple(
            api.UpgradeDefinition(
                upgrade_type=name,
                cost_cents=int(values["cost_cents"]),
                max_per_carrier_period=int(values["max_per_carrier_period"]),
                multiplier_bps=(
                    int(values["multiplier_bps"])
                    if "multiplier_bps" in values else None
                ),
            )
            for name, values in rules["upgrades"].items()
        ),
        pricing=api.PricingPolicy(
            additional_card_cents=int(pricing["additional_card_cents"]),
            metal_security_cents=int(pricing["metal_security_cents"]),
            terminal_penalty_cents=int(pricing["terminal_penalty_cents"]),
            attempt_multipliers_bps=tuple(
                int(value) for value in pricing["attempt_multipliers_bps"]
            ),
            max_voluntary_hold_minutes=int(
                rules["simulation"]["max_voluntary_hold_minutes"]
            ),
            dispatch_tick_minutes=int(rules["simulation"]["dispatch_tick_minutes"]),
        ),
    )
