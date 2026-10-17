"""Flota base, unidades arrendadas y efectos temporales de upgrades."""

from __future__ import annotations

from datetime import datetime
from typing import Mapping

from .arithmetic import round_half_up_ratio
from .models import CarrierDefinition, CarrierState, UnitState, UpgradeLease


class FleetManager:
    def __init__(self, carriers: tuple[CarrierDefinition, ...], start: datetime) -> None:
        self.states: dict[str, CarrierState] = {}
        self._extra_sequences: dict[str, int] = {}
        for definition in carriers:
            units = [
                UnitState(f"{definition.carrier_id}:BASE:{index:03d}", False, start)
                for index in range(1, definition.fleet_units + 1)
            ]
            self.states[definition.carrier_id] = CarrierState(definition, units)
            self._extra_sequences[definition.carrier_id] = 0

    def state(self, carrier_id: str) -> CarrierState | None:
        return self.states.get(carrier_id)

    @staticmethod
    def operates(state: CarrierState, now: datetime, holidays: frozenset) -> bool:
        definition = state.definition
        if now.isoweekday() == 7 and not definition.operates_sundays:
            return False
        if now.date() in holidays and not definition.operates_holidays:
            return False
        return True

    @staticmethod
    def _usable_future(unit: UnitState) -> bool:
        if unit.retiring:
            return False
        if unit.is_extra and unit.expires_at is not None and unit.expires_at <= unit.available_at:
            return False
        return True

    def available_units(self, state: CarrierState, now: datetime) -> list[UnitState]:
        return sorted(
            (unit for unit in state.units if self._usable_future(unit) and unit.reusable_at(now)),
            key=lambda unit: unit.unit_id,
        )

    def next_available_at(self, state: CarrierState, now: datetime) -> datetime | None:
        if self.available_units(state, now):
            return now
        candidates = [unit.available_at for unit in state.units if self._usable_future(unit)]
        return min(candidates) if candidates else None

    @staticmethod
    def speed_multiplier_bps(state: CarrierState, now: datetime) -> int:
        return 12_500 if any(
            lease.upgrade_type == "SPEED_SHIFT" and lease.expires_at > now
            for lease in state.upgrades
        ) else 10_000

    @staticmethod
    def batch_capacity(state: CarrierState, now: datetime) -> int:
        expanded = any(
            lease.upgrade_type == "EXPANDED_CAPACITY" and lease.expires_at > now
            for lease in state.upgrades
        )
        if not expanded:
            return state.definition.batch_capacity
        return state.definition.batch_capacity * 15_000 // 10_000

    @staticmethod
    def active_upgrades(state: CarrierState, now: datetime) -> dict[str, int]:
        result: dict[str, int] = {}
        for lease in state.upgrades:
            if lease.expires_at > now:
                result[lease.upgrade_type] = result.get(lease.upgrade_type, 0) + lease.quantity
        return result

    def reserve(
        self, state: CarrierState, now: datetime, return_at: datetime, batch_id: str
    ) -> UnitState:
        available = self.available_units(state, now)
        if not available:
            raise RuntimeError("reserva sin unidad disponible")
        unit = available[0]
        unit.available_at = return_at
        unit.active_batch_id = batch_id
        return unit

    def release(self, carrier_id: str, unit_id: str, batch_id: str, now: datetime) -> None:
        state = self.states[carrier_id]
        unit = next((value for value in state.units if value.unit_id == unit_id), None)
        if unit is None or unit.active_batch_id != batch_id:
            return
        unit.active_batch_id = None
        unit.available_at = now
        if unit.retiring:
            state.units.remove(unit)

    def add_upgrade(
        self,
        carrier_id: str,
        upgrade_type: str,
        quantity: int,
        period_index: int,
        now: datetime,
        expires_at: datetime,
    ) -> None:
        state = self.states[carrier_id]
        state.upgrades.append(UpgradeLease(upgrade_type, quantity, period_index, expires_at))
        if upgrade_type == "EXTRA_UNIT":
            for _ in range(quantity):
                self._extra_sequences[carrier_id] += 1
                sequence = self._extra_sequences[carrier_id]
                state.units.append(UnitState(
                    unit_id=f"{carrier_id}:EXTRA:{sequence:03d}",
                    is_extra=True,
                    available_at=now,
                    expires_at=expires_at,
                ))

    def expire_period(self, period_index: int, now: datetime) -> None:
        for state in self.states.values():
            expiring = [
                lease for lease in state.upgrades
                if lease.period_index == period_index and lease.expires_at <= now
            ]
            if not expiring:
                continue
            extra_quantity = sum(
                lease.quantity for lease in expiring if lease.upgrade_type == "EXTRA_UNIT"
            )
            if extra_quantity:
                extras = sorted(
                    (u for u in state.units if u.is_extra and u.expires_at == now),
                    key=lambda u: u.unit_id,
                )
                for unit in extras:
                    if unit.active_batch_id is None and unit.available_at <= now:
                        state.units.remove(unit)
                    else:
                        unit.retiring = True
            state.upgrades[:] = [lease for lease in state.upgrades if lease not in expiring]

    @staticmethod
    def register_result(state: CarrierState, success: bool) -> None:
        state.rolling_results.append(success)
        if len(state.rolling_results) > 200:
            del state.rolling_results[:-200]
