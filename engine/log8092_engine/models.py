"""Estado mutable exclusivamente interno del Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


TERMINAL_STATES = frozenset({"DELIVERED", "RETURNED_TO_VAULT", "UNRESOLVED"})


@dataclass(frozen=True, slots=True)
class CarrierDefinition:
    carrier_id: str
    display_name: str
    allowed_zones: tuple[str, ...]
    capabilities: tuple[str, ...]
    fleet_units: int
    batch_capacity: int
    pickup_minutes: int
    speed_kmh: int
    base_fee_cents: int
    zone_surcharge_cents: dict[str, int]
    night_multiplier_bps: int
    holiday_multiplier_bps: int
    operates_sundays: bool
    operates_holidays: bool
    operational_failure_bps: int
    supported_upgrades: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ShipmentInput:
    shipment_id: str
    available_at: datetime
    sla_deadline: datetime
    product: str
    zone: str
    delivery_cluster_id: str
    is_metal: bool


@dataclass(slots=True)
class ShipmentRecord:
    shipment_id: str
    available_at: datetime
    ready_at: datetime
    sla_deadline: datetime
    product: str
    zone: str
    delivery_cluster_id: str
    is_metal: bool
    state: str = "READY"
    attempt_number: int = 1
    required_capabilities: set[str] = field(default_factory=set)
    retry_eligible_at: datetime | None = None
    ready_epoch: int = 1
    hold_audited_epoch: int = 0
    delivered_at: datetime | None = None
    terminal_at: datetime | None = None

    @classmethod
    def from_input(cls, value: ShipmentInput) -> "ShipmentRecord":
        return cls(
            shipment_id=value.shipment_id,
            available_at=value.available_at,
            ready_at=value.available_at,
            sla_deadline=value.sla_deadline,
            product=value.product,
            zone=value.zone,
            delivery_cluster_id=value.delivery_cluster_id,
            is_metal=value.is_metal,
        )

    @property
    def terminal(self) -> bool:
        return self.state in TERMINAL_STATES


@dataclass(slots=True)
class UnitState:
    unit_id: str
    is_extra: bool
    available_at: datetime
    expires_at: datetime | None = None
    retiring: bool = False
    active_batch_id: str | None = None

    def reusable_at(self, now: datetime) -> bool:
        return not self.retiring and self.available_at <= now


@dataclass(slots=True)
class UpgradeLease:
    upgrade_type: str
    quantity: int
    period_index: int
    expires_at: datetime


@dataclass(slots=True)
class CarrierState:
    definition: CarrierDefinition
    units: list[UnitState]
    upgrades: list[UpgradeLease] = field(default_factory=list)
    rolling_results: list[bool] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ScheduledAttempt:
    batch_id: str
    carrier_id: str
    shipment_id: str
    attempt_number: int
    eta: datetime
    failure_reason: str | None


@dataclass(frozen=True, slots=True)
class EngineEvent:
    when: datetime
    priority: int
    order_key: str
    sequence: int
    kind: str
    payload: Any = None
