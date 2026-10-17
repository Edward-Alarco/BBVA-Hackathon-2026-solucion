"""Regression tests for public dispatch invariants, independent of starter policy."""
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from candidate_strategy import CandidateStrategy
from interfaces import DeliveryAttemptResult, DispatchContext, DispatchReceipt, Shipment, ZonePrice
from test_candidate_strategy_smoke import carrier_snapshot, failure_policy, scenario_calendar, rcp_policy


NOW = datetime(2026, 1, 5, 8, tzinfo=timezone(timedelta(hours=-5)))


def shipment(sid="S1", **changes):
    s = Shipment(sid, NOW, NOW, NOW + timedelta(hours=24), "VIP_BLACK", "URBANA", "C1", False, "READY", 1)
    return replace(s, **changes)


class Service:
    def __init__(self, carriers=None):
        self.now = NOW
        self.carriers = carriers or (carrier_snapshot(NOW),)
        self.calls = []
        self.receipts = []
        self.reject = set()

    def snapshot(self):
        return self.carriers

    def dispatch_batch(self, carrier_id, ids):
        ids = tuple(ids)
        self.calls.append((carrier_id, ids))
        c = next(c for c in self.carriers if c.carrier_id == carrier_id)
        accepted = carrier_id not in self.reject and c.available_units > 0
        reason = None if accepted else "NO_AVAILABLE_UNIT"
        if accepted:
            self.carriers = tuple(replace(x, available_units=x.available_units - 1) if x.carrier_id == carrier_id else x for x in self.carriers)
        r = DispatchReceipt(accepted, carrier_id, ids, self.now, 500 if accepted else 0, "B" if accepted else None, self.now + timedelta(minutes=30) if accepted else None, reason)
        self.receipts.append(r)
        return r


def context(service):
    return DispatchContext(service.now, 3000000, 0, 3300000, service.snapshot(), scenario_calendar(), failure_policy(), rcp_policy())


class DispatchContractTest(unittest.TestCase):
    def setup_strategy(self, shipments, carriers=None):
        service = Service(carriers)
        strategy = CandidateStrategy(service)
        strategy.on_shipments_available(NOW, tuple(shipments))
        return service, strategy

    def test_same_destination_batches(self):
        svc, strategy = self.setup_strategy([shipment("A"), shipment("B")])
        strategy.on_dispatch_tick(context(svc))
        self.assertEqual(svc.calls, [("PUBLIC_TEST_CARRIER", ("A", "B"))])
        self.assertFalse(strategy.pending)

    def test_different_destinations_never_mix(self):
        svc, strategy = self.setup_strategy([shipment("A"), shipment("B", delivery_cluster_id="C2")], (replace(carrier_snapshot(NOW), available_units=2),))
        strategy.on_dispatch_tick(context(svc))
        self.assertEqual([len(ids) for _, ids in svc.calls], [1, 1])

    def test_different_attempts_never_mix(self):
        svc, strategy = self.setup_strategy([shipment("A"), shipment("B", attempt_number=2)], (replace(carrier_snapshot(NOW), available_units=2),))
        strategy.on_dispatch_tick(context(svc))
        self.assertEqual([len(ids) for _, ids in svc.calls], [1, 1])

    def test_different_zones_never_mix(self):
        c = replace(carrier_snapshot(NOW), available_units=2, allowed_zones=("URBANA", "SUBURBANA"), zone_prices=(ZonePrice("URBANA", 0), ZonePrice("SUBURBANA", 100)))
        svc, strategy = self.setup_strategy([shipment("A"), shipment("B", zone="SUBURBANA")], (c,))
        strategy.on_dispatch_tick(context(svc))
        self.assertEqual([len(ids) for _, ids in svc.calls], [1, 1])

    def test_capacity_splits_batches(self):
        c = replace(carrier_snapshot(NOW), available_units=3, batch_capacity=2)
        svc, strategy = self.setup_strategy([shipment(str(i)) for i in range(5)], (c,))
        strategy.on_dispatch_tick(context(svc))
        self.assertEqual([len(ids) for _, ids in svc.calls], [2, 2, 1])

    def test_consumed_unit_is_not_reused(self):
        svc, strategy = self.setup_strategy([shipment("A"), shipment("B", delivery_cluster_id="C2")])
        strategy.on_dispatch_tick(context(svc))
        self.assertEqual(len(svc.calls), 1)
        self.assertEqual(len(strategy.pending), 1)

    def test_no_fleet_preserves_work(self):
        svc, strategy = self.setup_strategy([shipment()], (replace(carrier_snapshot(NOW), available_units=0),))
        strategy.on_dispatch_tick(context(svc))
        self.assertFalse(svc.calls)
        self.assertEqual(len(strategy.pending), 1)

    def test_closed_carrier_not_called(self):
        svc, strategy = self.setup_strategy([shipment()], (replace(carrier_snapshot(NOW), operates_now=False),))
        strategy.on_dispatch_tick(context(svc))
        self.assertFalse(svc.calls)

    def test_exact_zone_membership(self):
        svc, strategy = self.setup_strategy([shipment()], (replace(carrier_snapshot(NOW), allowed_zones=("SUBURBANA",)),))
        strategy.on_dispatch_tick(context(svc))
        self.assertFalse(svc.calls)

    def test_hard_access_uses_compatible_carrier(self):
        c1 = carrier_snapshot(NOW)
        c2 = replace(c1, carrier_id="OTHER", capabilities=("HARD_ACCESS",))
        svc, strategy = self.setup_strategy([shipment(required_capabilities=("HARD_ACCESS",))], (c1, c2))
        strategy.on_dispatch_tick(context(svc))
        self.assertEqual(svc.calls[0][0], "OTHER")

    def test_incompatible_first_does_not_block_others(self):
        svc, strategy = self.setup_strategy([shipment("A", required_capabilities=("HARD_ACCESS",)), shipment("B")])
        strategy.on_dispatch_tick(context(svc))
        self.assertEqual(svc.calls[0][1], ("B",))
        self.assertIn("A", strategy.pending)

    def test_terminal_failure_is_not_requeued(self):
        svc, strategy = self.setup_strategy([])
        s = shipment(state="RETURNED_TO_VAULT", attempt_number=3)
        strategy.on_delivery_failed(DeliveryAttemptResult(s, "OLD", "B", 3, NOW, True, "CUSTOMER_ABSENT"))
        strategy.on_dispatch_tick(context(svc))
        self.assertFalse(svc.calls)
        self.assertFalse(strategy.retries)

    def test_retry_exact_eligibility_and_new_requirements(self):
        c = replace(carrier_snapshot(NOW), capabilities=("HARD_ACCESS",))
        svc, strategy = self.setup_strategy([], (c,))
        s = shipment(state="WAITING_RETRY", attempt_number=2, ready_at=NOW + timedelta(hours=24), required_capabilities=("HARD_ACCESS",))
        strategy.on_delivery_failed(DeliveryAttemptResult(s, "OLD", "B", 1, NOW, False, "INACCESSIBLE_ROUTE"))
        strategy.on_dispatch_tick(context(svc))
        self.assertFalse(svc.calls)
        svc.now = s.ready_at
        strategy.on_dispatch_tick(context(svc))
        self.assertEqual(len(svc.calls), 1)
        self.assertFalse(strategy.retries)

    def test_nonvip_is_dispatched_without_voluntary_hold(self):
        svc, strategy = self.setup_strategy([shipment(product="STANDARD")])
        strategy.on_dispatch_tick(context(svc))
        self.assertEqual(len(svc.calls), 1)

    def test_urgent_nonvip_not_delayed(self):
        svc, strategy = self.setup_strategy([shipment(product="STANDARD", sla_deadline=NOW + timedelta(hours=1))])
        strategy.on_dispatch_tick(context(svc))
        self.assertEqual(len(svc.calls), 1)

    def test_earliest_deadline_wins(self):
        svc, strategy = self.setup_strategy([shipment("LATE", delivery_cluster_id="C2"), shipment("URGENT", sla_deadline=NOW + timedelta(hours=1))])
        strategy.on_dispatch_tick(context(svc))
        self.assertEqual(svc.calls[0][1], ("URGENT",))

    def test_rejection_preserves_work_and_tries_alternative(self):
        c1 = carrier_snapshot(NOW)
        c2 = replace(c1, carrier_id="Z")
        svc, strategy = self.setup_strategy([shipment()], (c1, c2))
        svc.reject.add(c1.carrier_id)
        strategy.on_dispatch_tick(context(svc))
        self.assertEqual(len(svc.calls), 2)
        self.assertFalse(strategy.pending)

    def test_all_rejections_terminate_without_losing_work(self):
        svc, strategy = self.setup_strategy([shipment()])
        svc.reject.add("PUBLIC_TEST_CARRIER")
        strategy.on_dispatch_tick(context(svc))
        self.assertEqual(len(svc.calls), 1)
        self.assertIn("S1", strategy.pending)

    def test_price_rounding_attempt_night_and_metals(self):
        svc = Service()
        c = svc.carriers[0]
        self.assertEqual(CandidateStrategy._price(c, "URBANA", 2, 3, 1, context(svc)), 940)
        svc.now = NOW.replace(hour=21)
        self.assertEqual(CandidateStrategy._price(c, "URBANA", 2, 1, 0, context(svc)), 375)

    def test_no_upgrades_requested(self):
        svc, strategy = self.setup_strategy([])
        self.assertEqual(strategy.on_monthly_planning(None), ())

    def test_empty_tick_does_not_contact_service(self):
        svc, strategy = self.setup_strategy([])
        strategy.on_dispatch_tick(context(svc))
        self.assertFalse(svc.calls)

    def test_future_ready_at_is_respected(self):
        svc, strategy = self.setup_strategy([shipment(ready_at=NOW + timedelta(minutes=30))])
        strategy.on_dispatch_tick(context(svc))
        self.assertFalse(svc.calls)
        svc.now += timedelta(minutes=30)
        strategy.on_dispatch_tick(context(svc))
        self.assertEqual(len(svc.calls), 1)

    def test_overdue_hold_dispatches_at_first_feasible_tick(self):
        svc, strategy = self.setup_strategy([shipment(ready_at=NOW - timedelta(minutes=45))])
        strategy.on_dispatch_tick(context(svc))
        self.assertEqual(len(svc.calls), 1)

    def test_success_releases_pending_state(self):
        svc, strategy = self.setup_strategy([shipment()])
        strategy.on_delivery_succeeded(DeliveryAttemptResult(shipment(state="DELIVERED"), "C", "B", 1, NOW, True))
        strategy.on_dispatch_tick(context(svc))
        self.assertFalse(strategy.pending)
        self.assertFalse(svc.calls)

    def test_catalog_names_and_order_have_no_assumed_roles(self):
        c = replace(carrier_snapshot(NOW), carrier_id="X93")
        svc, strategy = self.setup_strategy([shipment("ARBITRARY")], (c,))
        strategy.on_dispatch_tick(context(svc))
        self.assertEqual(svc.calls, [("X93", ("ARBITRARY",))])

    def test_expensive_on_time_carrier_beats_cheap_late_carrier(self):
        slow = replace(carrier_snapshot(NOW), carrier_id="SLOW", speed_kmh=1, base_fee_cents=1)
        fast = replace(carrier_snapshot(NOW), carrier_id="FAST", base_fee_cents=1000000)
        svc, strategy = self.setup_strategy([shipment(sla_deadline=NOW + timedelta(hours=1))], (slow, fast))
        strategy.on_dispatch_tick(context(svc))
        self.assertEqual(svc.calls[0][0], "FAST")

    def test_calendar_multiplier_applied_once_on_sunday_holiday(self):
        svc = Service()
        svc.now = NOW.replace(day=11, hour=21)
        ctx = context(svc)
        ctx = replace(ctx, calendar=replace(ctx.calendar, holidays=(svc.now.date(),)))
        self.assertEqual(CandidateStrategy._price(svc.carriers[0], "URBANA", 1, 1, 0, ctx), 1350)

    def test_half_up_rounding_is_not_bankers_rounding(self):
        svc = Service()
        c = replace(svc.carriers[0], base_fee_cents=1)
        self.assertEqual(CandidateStrategy._price(c, "URBANA", 2, 1, 0, context(svc)), 1)

    def test_retry_queue_orders_equal_ready_times(self):
        svc, strategy = self.setup_strategy([])
        for sid in ("Z", "A"):
            s = shipment(sid, state="WAITING_RETRY", attempt_number=2)
            strategy.on_delivery_failed(DeliveryAttemptResult(s, "OLD", "B", 1, NOW, False, "CUSTOMER_ABSENT"))
        strategy.on_dispatch_tick(context(svc))
        self.assertEqual(svc.calls[0][1], ("A", "Z"))

    def test_mixed_capability_batch_uses_union_of_requirements(self):
        plain = carrier_snapshot(NOW)
        hard = replace(plain, carrier_id="HARD", capabilities=("HARD_ACCESS",))
        svc, strategy = self.setup_strategy([shipment("A", required_capabilities=("HARD_ACCESS",)), shipment("B")], (plain, hard))
        strategy.on_dispatch_tick(context(svc))
        self.assertEqual(svc.calls, [("HARD", ("A", "B"))])


if __name__ == "__main__":
    unittest.main()
