"""Fachada sincronica y autoridad atomica de despacho."""

from __future__ import annotations

from datetime import datetime, timedelta
from collections import Counter
from typing import Callable, Mapping, Sequence

from .arithmetic import ceil_div
from .failure_model import determine_failure, rolling_success_bps
from .fleet import FleetManager
from .ledger import Ledger
from .metrics import Metrics
from .models import CarrierState, ScheduledAttempt, ShipmentRecord
from .pricing import current_time_multiplier_bps, price_batch
from .public_codec import api_module


class EngineCarrierService:
    def __init__(
        self,
        rules: Mapping[str, object],
        holidays: frozenset,
        fleet: FleetManager,
        ledger: Ledger,
        shipments: dict[str, ShipmentRecord],
        metrics: Metrics,
        failure_key: bytes,
        on_accepted: Callable[[str, str, datetime, tuple[ScheduledAttempt, ...]], None],
    ) -> None:
        self.rules = rules
        self.holidays = holidays
        self.fleet = fleet
        self.ledger = ledger
        self.shipments = shipments
        self.metrics = metrics
        self.failure_key = failure_key
        self.on_accepted = on_accepted
        self.now: datetime | None = None
        self._batch_sequence = 0
        self.accepted_batches_by_carrier: Counter[str] = Counter()
        self.accepted_shipments_by_carrier: Counter[str] = Counter()
        self.dispatch_cents_by_carrier: Counter[str] = Counter()
        self.rejection_reasons = tuple(str(x) for x in rules["dispatch"]["rejection_precedence"])

    def set_now(self, now: datetime) -> None:
        self.now = now

    def _operates(self, state: CarrierState) -> bool:
        assert self.now is not None
        return self.fleet.operates(state, self.now, self.holidays)

    def snapshot(self):
        if self.now is None:
            raise RuntimeError("reloj de CarrierService no inicializado")
        api = api_module()
        snapshots = []
        for carrier_id in sorted(self.fleet.states):
            state = self.fleet.states[carrier_id]
            definition = state.definition
            active = self.fleet.active_upgrades(state, self.now)
            snapshots.append(api.CarrierSnapshot(
                carrier_id=carrier_id,
                allowed_zones=definition.allowed_zones,
                capabilities=definition.capabilities,
                supported_upgrades=definition.supported_upgrades,
                available_units=len(self.fleet.available_units(state, self.now)),
                base_total_units=definition.fleet_units,
                total_units=len(state.units),
                retiring_units=sum(unit.retiring for unit in state.units),
                base_batch_capacity=definition.batch_capacity,
                batch_capacity=self.fleet.batch_capacity(state, self.now),
                pickup_minutes=definition.pickup_minutes,
                speed_kmh=definition.speed_kmh,
                speed_multiplier_bps=self.fleet.speed_multiplier_bps(state, self.now),
                base_fee_cents=definition.base_fee_cents,
                zone_prices=tuple(
                    api.ZonePrice(zone, definition.zone_surcharge_cents[zone])
                    for zone in definition.allowed_zones
                ),
                night_multiplier_bps=definition.night_multiplier_bps,
                holiday_multiplier_bps=definition.holiday_multiplier_bps,
                current_time_multiplier_bps=current_time_multiplier_bps(
                    definition, self.now, self.holidays, self.rules
                ),
                operates_now=self._operates(state),
                next_available_at=self.fleet.next_available_at(state, self.now),
                operational_failure_bps=definition.operational_failure_bps,
                rolling_success_rate_bps=rolling_success_bps(state.rolling_results),
                active_upgrades=tuple(
                    api.ActiveUpgrade(name, quantity)
                    for name, quantity in sorted(active.items())
                ),
            ))
        return tuple(snapshots)

    def _reject(self, carrier_id: str, ids: tuple[str, ...], reason: str):
        assert self.now is not None
        api = api_module()
        self.metrics.rejected_dispatches += 1
        self.metrics.dispatch_rejections[reason] += 1
        return api.DispatchReceipt(
            accepted=False,
            carrier_id=carrier_id,
            shipment_ids=ids,
            dispatched_at=self.now,
            charged_cost_cents=0,
            rejection_reason=reason,
        )

    def dispatch_batch(self, carrier_id: str, shipment_ids: Sequence[str]):
        if self.now is None:
            raise RuntimeError("reloj de CarrierService no inicializado")
        api = api_module()
        original = tuple(str(value) for value in shipment_ids)
        canonical = tuple(sorted(original))
        state = self.fleet.state(str(carrier_id))
        if state is None:
            return self._reject(str(carrier_id), canonical, "UNKNOWN_CARRIER")
        if not original:
            return self._reject(str(carrier_id), canonical, "EMPTY_BATCH")
        if len(original) != len(set(original)):
            return self._reject(str(carrier_id), canonical, "DUPLICATE_SHIPMENT")
        if any(shipment_id not in self.shipments for shipment_id in canonical):
            return self._reject(str(carrier_id), canonical, "UNKNOWN_SHIPMENT")
        records = tuple(self.shipments[value] for value in canonical)
        if any(record.terminal for record in records):
            return self._reject(str(carrier_id), canonical, "TERMINAL_SHIPMENT")
        if any(record.state != "READY" or record.ready_at > self.now for record in records):
            return self._reject(str(carrier_id), canonical, "SHIPMENT_NOT_READY")
        if len({record.delivery_cluster_id for record in records}) != 1:
            return self._reject(str(carrier_id), canonical, "MIXED_DELIVERY_CLUSTER")
        if len({record.zone for record in records}) != 1:
            return self._reject(str(carrier_id), canonical, "MIXED_ZONE")
        if len({record.attempt_number for record in records}) != 1:
            return self._reject(str(carrier_id), canonical, "MIXED_ATTEMPT_NUMBER")
        definition = state.definition
        if records[0].zone not in definition.allowed_zones:
            return self._reject(str(carrier_id), canonical, "ZONE_UNSUPPORTED")
        if any(not record.required_capabilities.issubset(definition.capabilities) for record in records):
            return self._reject(str(carrier_id), canonical, "CAPABILITY_UNSUPPORTED")
        if len(records) > self.fleet.batch_capacity(state, self.now):
            return self._reject(str(carrier_id), canonical, "BATCH_CAPACITY_EXCEEDED")
        if not self._operates(state):
            return self._reject(str(carrier_id), canonical, "OUTSIDE_OPERATING_WINDOW")
        if not self.fleet.available_units(state, self.now):
            return self._reject(str(carrier_id), canonical, "NO_AVAILABLE_UNIT")
        price = price_batch(definition, records, self.now, self.holidays, self.rules)

        self._batch_sequence += 1
        batch_id = f"B-{self._batch_sequence:09d}"
        multiplier = self.fleet.speed_multiplier_bps(state, self.now)
        distance = int(self.rules["distances_km"][records[0].zone])
        outbound_minutes = ceil_div(distance * 60 * 10_000, definition.speed_kmh * multiplier)
        eta = self.now + timedelta(minutes=definition.pickup_minutes + outbound_minutes)
        return_at = eta + timedelta(minutes=outbound_minutes)
        self.ledger.charge_dispatch(price.total_cents)
        unit = self.fleet.reserve(state, self.now, return_at, batch_id)
        attempts: list[ScheduledAttempt] = []
        for record in records:
            failure = determine_failure(
                record, definition, self.now, self.holidays, self.rules, self.failure_key
            )
            attempts.append(ScheduledAttempt(
                batch_id=batch_id,
                carrier_id=carrier_id,
                shipment_id=record.shipment_id,
                attempt_number=record.attempt_number,
                eta=eta,
                failure_reason=failure,
            ))
            record.state = "IN_TRANSIT"
        self.metrics.on_attempt_accepted(len(records))
        self.accepted_batches_by_carrier[carrier_id] += 1
        self.accepted_shipments_by_carrier[carrier_id] += len(records)
        self.dispatch_cents_by_carrier[carrier_id] += price.total_cents
        self.on_accepted(carrier_id, unit.unit_id, return_at, tuple(attempts))
        return api.DispatchReceipt(
            accepted=True,
            carrier_id=carrier_id,
            shipment_ids=canonical,
            dispatched_at=self.now,
            charged_cost_cents=price.total_cents,
            batch_id=batch_id,
            estimated_delivery_at=eta,
        )

    def feasible_singleton_exists(self, record: ShipmentRecord) -> bool:
        if self.now is None or record.state != "READY" or record.ready_at > self.now:
            return False
        for state in self.fleet.states.values():
            definition = state.definition
            if record.zone not in definition.allowed_zones:
                continue
            if not record.required_capabilities.issubset(definition.capabilities):
                continue
            if self.fleet.batch_capacity(state, self.now) < 1:
                continue
            if not self._operates(state) or not self.fleet.available_units(state, self.now):
                continue
            return True
        return False
