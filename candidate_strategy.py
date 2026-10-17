"""Online dispatch using public snapshots, compatible batches and bounded state."""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
import heapq

from interfaces import BaseDispatcherStrategy


class CandidateStrategy(BaseDispatcherStrategy):
    def __init__(self, carrier_service):
        super().__init__(carrier_service)
        self.pending = {}
        self.retries = []
        # Empty compatibility field for the supplied starter smoke test.
        # Reattempts deliberately do not pin a shipment to a previous carrier.
        self.last_carrier_by_shipment = {}

    def on_shipments_available(self, now, shipments):
        for shipment in shipments:
            self.pending[shipment.shipment_id] = shipment

    def on_delivery_succeeded(self, result):
        self.pending.pop(result.shipment.shipment_id, None)

    def on_delivery_failed(self, result):
        shipment = result.shipment
        self.pending.pop(shipment.shipment_id, None)
        if not result.terminal:
            heapq.heappush(self.retries, (shipment.ready_at, shipment.shipment_id, shipment))

    def on_monthly_planning(self, context):
        return ()

    @staticmethod
    def _price(carrier, zone, attempt, size, metals, context):
        policy = context.decision_policy.pricing if context.decision_policy else None
        factors = policy.attempt_multipliers_bps if policy else (10000, 5000, 10000)
        base = carrier.base_fee_cents + next(p.surcharge_cents for p in carrier.zone_prices if p.zone == zone)
        night = carrier.night_multiplier_bps if context.now.hour >= 20 or context.now.hour < 6 else 10000
        special = context.now.isoweekday() == 7 or context.now.date() in context.calendar.holidays
        calendar = carrier.holiday_multiplier_bps if special else 10000
        numerator = base * factors[attempt - 1] * night * calendar
        adjusted = (numerator + 500000000000) // 1000000000000
        return adjusted + (policy.additional_card_cents if policy else 120) * (size - 1) + (policy.metal_security_cents if policy else 450) * metals

    def on_dispatch_tick(self, context):
        now = context.now
        while self.retries and self.retries[0][0] <= now:
            _, sid, shipment = heapq.heappop(self.retries)
            self.pending[sid] = shipment
        if not self.pending:
            return
        carriers = context.carriers
        units = {c.carrier_id: c.available_units for c in carriers}
        distances = {d.zone: d.distance_km for d in context.decision_policy.distances} if context.decision_policy else {"URBANA": 12, "SUBURBANA": 35, "RURAL": 80, "REMOTA": 150}
        absence = {p.attempt_number: p.customer_absence_bps for p in context.failure_policy.attempts}
        zones = {p.zone: p for p in context.failure_policy.zones}
        groups = defaultdict(list)
        for s in self.pending.values():
            if s.ready_at <= now:
                groups[(s.delivery_cluster_id, s.zone, s.attempt_number)].append(s)
        ordered = sorted(groups.values(), key=lambda group: (min(s.sla_deadline for s in group), -max(len(s.required_capabilities) for s in group), min(s.ready_at for s in group)))
        for group in ordered:
            group.sort(key=lambda s: (s.sla_deadline, s.ready_at, s.shipment_id))
            remaining = group
            blocked = set()
            while remaining:
                first = remaining[0]
                choices = []
                for c in carriers:
                    if c.carrier_id in blocked or not c.operates_now or units[c.carrier_id] <= 0 or first.zone not in c.allowed_zones:
                        continue
                    caps = set(c.capabilities)
                    if not set(first.required_capabilities).issubset(caps):
                        continue
                    batch = [s for s in remaining if set(s.required_capabilities).issubset(caps)][:c.batch_capacity]
                    if not batch:
                        continue
                    size = len(batch)
                    outbound = (distances[first.zone] * 600000 + c.speed_kmh * c.speed_multiplier_bps - 1) // (c.speed_kmh * c.speed_multiplier_bps)
                    travel = c.pickup_minutes + outbound
                    eta = now + timedelta(minutes=travel)
                    profile = zones[first.zone]
                    route = 0 if "HARD_ACCESS" in caps else min(10000, max(0, profile.inaccessible_route_bps))
                    absent = min(10000, max(0, absence[first.attempt_number] + profile.absence_modifier_bps))
                    op = c.operational_failure_bps
                    if now.isoweekday() == 7:
                        op += context.failure_policy.sunday_operation_modifier_bps
                    if now.date() in context.calendar.holidays:
                        op += context.failure_policy.holiday_operation_modifier_bps
                    op = min(10000, max(0, op))
                    success = (1 - route / 10000) * (1 - absent / 10000) * (1 - op / 10000)
                    price = self._price(c, first.zone, first.attempt_number, size, sum(s.is_metal for s in batch), context)
                    late = sum(eta > s.sla_deadline for s in batch)
                    vip = sum(s.product == "VIP_BLACK" for s in batch)
                    score = price / size + (5 + 5 * vip / size) * travel + (1 - success) * (3000 + 8000 * vip / size) + 20000 * late / size
                    score += (c.pickup_minutes + 2 * outbound) / size
                    # Prefer an on-time first delivery over any cheaper late option.
                    choices.append((eta > first.sla_deadline, score, c.carrier_id, c, batch))
                if not choices:
                    remaining = remaining[1:]
                    continue
                _, _, _, chosen, batch = min(choices, key=lambda item: item[:3])
                ids = tuple(s.shipment_id for s in batch)
                receipt = self.carrier_service.dispatch_batch(chosen.carrier_id, ids)
                if receipt.accepted:
                    units[chosen.carrier_id] -= 1
                    selected = set(ids)
                    for sid in ids:
                        self.pending.pop(sid, None)
                    remaining = [s for s in remaining if s.shipment_id not in selected]
                else:
                    carriers = self.carrier_service.snapshot()
                    units = {c.carrier_id: c.available_units for c in carriers}
                    blocked.add(chosen.carrier_id)
