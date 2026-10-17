from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta, timezone
from typing import Sequence, Tuple

from candidate_strategy import CandidateStrategy
from interfaces import (
    CarrierSnapshot,
    DeliveryAttemptResult,
    DispatchContext,
    DispatchReceipt,
    FailureAttemptRate,
    FailurePolicy,
    FailureZoneProfile,
    MonthlyPlanningContext,
    RcpAudienceProfile,
    RcpExpectationRange,
    RcpPolicy,
    ScenarioCalendar,
    Shipment,
    ZonePrice,
)


LIMA = timezone(timedelta(hours=-5))


def carrier_snapshot(now: datetime) -> CarrierSnapshot:
    return CarrierSnapshot(
        carrier_id="PUBLIC_TEST_CARRIER",
        allowed_zones=("URBANA",),
        capabilities=(),
        supported_upgrades=("EXTRA_UNIT",),
        available_units=1,
        base_total_units=1,
        total_units=1,
        retiring_units=0,
        base_batch_capacity=4,
        batch_capacity=4,
        pickup_minutes=10,
        speed_kmh=40,
        speed_multiplier_bps=10_000,
        base_fee_cents=500,
        zone_prices=(ZonePrice("URBANA", 0),),
        night_multiplier_bps=15_000,
        holiday_multiplier_bps=18_000,
        current_time_multiplier_bps=10_000,
        operates_now=True,
        next_available_at=now,
        operational_failure_bps=100,
        rolling_success_rate_bps=None,
        active_upgrades=(),
    )


def failure_policy() -> FailurePolicy:
    return FailurePolicy(
        attempts=(
            FailureAttemptRate(1, 700),
            FailureAttemptRate(2, 350),
            FailureAttemptRate(3, 150),
        ),
        zones=(
            FailureZoneProfile("URBANA", 0, 0),
            FailureZoneProfile("SUBURBANA", 50, 0),
            FailureZoneProfile("RURAL", 150, 400),
            FailureZoneProfile("REMOTA", 300, 1_200),
        ),
        sunday_operation_modifier_bps=100,
        holiday_operation_modifier_bps=200,
    )


def scenario_calendar() -> ScenarioCalendar:
    return ScenarioCalendar(
        timezone="America/Lima",
        holidays=(date(2026, 1, 29), date(2026, 3, 10)),
    )


def rcp_policy() -> RcpPolicy:
    return RcpPolicy(
        influencer_rate_bps=300,
        undelivered_rating=1,
        delivered_floor_rating=2,
        on_time_boundary_rating=6,
        late_floor_ratio_bps=15_000,
        expectations=(
            RcpExpectationRange("VIP_BLACK", 2_500, 4_500),
            RcpExpectationRange("BUSINESS", 3_500, 6_500),
            RcpExpectationRange("SME", 4_500, 7_500),
            RcpExpectationRange("STANDARD", 5_500, 8_500),
        ),
        audiences=(
            RcpAudienceProfile("VIP", 7_000, 2_000, 20_000),
            RcpAudienceProfile("NORMAL", 1_800, 4_200, 10_000),
            RcpAudienceProfile("INFLUENCER", 9_000, 800, 80_000),
        ),
    )


class FakeCarrierService:
    def __init__(self, now: datetime) -> None:
        self.now = now
        self.carriers = (carrier_snapshot(now),)
        self.dispatched: list[Tuple[str, Tuple[str, ...]]] = []

    def snapshot(self) -> Tuple[CarrierSnapshot, ...]:
        return self.carriers

    def dispatch_batch(
        self, carrier_id: str, shipment_ids: Sequence[str]
    ) -> DispatchReceipt:
        ids = tuple(shipment_ids)
        self.dispatched.append((carrier_id, ids))
        return DispatchReceipt(
            accepted=True,
            carrier_id=carrier_id,
            shipment_ids=ids,
            dispatched_at=self.now,
            charged_cost_cents=500,
            batch_id="PUBLIC-BATCH-1",
            estimated_delivery_at=self.now + timedelta(minutes=28),
        )


class CandidateStrategySmokeTest(unittest.TestCase):
    def test_starter_completes_the_public_happy_path(self) -> None:
        now = datetime(2026, 1, 5, 8, 0, tzinfo=LIMA)
        service = FakeCarrierService(now)
        strategy = CandidateStrategy(service)
        shipment = Shipment(
            shipment_id="PUBLIC-SHIPMENT-1",
            available_at=now,
            ready_at=now,
            sla_deadline=now + timedelta(hours=24),
            product="VIP_BLACK",
            zone="URBANA",
            delivery_cluster_id="PUBLIC-CLUSTER-1",
            is_metal=False,
            state="READY",
            attempt_number=1,
        )
        context = DispatchContext(
            now=now,
            reference_budget_cents=100_000,
            spent_cents=0,
            contingency_threshold_cents=110_000,
            carriers=service.snapshot(),
            calendar=scenario_calendar(),
            failure_policy=failure_policy(),
            rcp_policy=rcp_policy(),
        )

        strategy.on_shipments_available(now, (shipment,))
        strategy.on_dispatch_tick(context)

        self.assertEqual(
            service.dispatched,
            [("PUBLIC_TEST_CARRIER", ("PUBLIC-SHIPMENT-1",))],
        )
        self.assertFalse(strategy.pending)

        strategy.on_delivery_succeeded(
            DeliveryAttemptResult(
                shipment=shipment,
                carrier_id="PUBLIC_TEST_CARRIER",
                batch_id="PUBLIC-BATCH-1",
                attempt_number=1,
                occurred_at=now + timedelta(minutes=28),
                terminal=True,
            )
        )
        self.assertNotIn("PUBLIC-SHIPMENT-1", strategy.last_carrier_by_shipment)

    def test_monthly_planning_returns_a_tuple(self) -> None:
        now = datetime(2026, 1, 5, 0, 0, tzinfo=LIMA)
        service = FakeCarrierService(now)
        strategy = CandidateStrategy(service)
        context = MonthlyPlanningContext(
            now=now,
            period_index=0,
            reference_budget_cents=100_000,
            spent_cents=0,
            contingency_threshold_cents=110_000,
            carriers=service.snapshot(),
            calendar=scenario_calendar(),
            failure_policy=failure_policy(),
            rcp_policy=rcp_policy(),
        )

        decisions = strategy.on_monthly_planning(context)

        self.assertIsInstance(decisions, tuple)
        self.assertEqual(decisions, ())


if __name__ == "__main__":
    unittest.main()
