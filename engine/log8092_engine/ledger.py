"""Libro mayor: autoridad contable sin bloquear decisiones por coste."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Ledger:
    reference_budget_cents: int
    contingency_threshold_bps: int
    dispatch_cents: int = 0
    upgrade_cents: int = 0
    penalty_cents: int = 0

    def __post_init__(self) -> None:
        self._validate(self.reference_budget_cents)
        if (
            isinstance(self.contingency_threshold_bps, bool)
            or not isinstance(self.contingency_threshold_bps, int)
            or self.contingency_threshold_bps < 10_000
        ):
            raise ValueError("umbral de contingencia invalido")

    @property
    def contingency_threshold_cents(self) -> int:
        return self.reference_budget_cents * self.contingency_threshold_bps // 10_000

    @property
    def spent_cents(self) -> int:
        return self.dispatch_cents + self.upgrade_cents + self.penalty_cents

    @property
    def over_reference_cents(self) -> int:
        return max(0, self.spent_cents - self.reference_budget_cents)

    @property
    def over_contingency_cents(self) -> int:
        return max(0, self.spent_cents - self.contingency_threshold_cents)

    @staticmethod
    def _validate(amount: int) -> None:
        if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
            raise ValueError("cargo invalido")

    def charge_dispatch(self, amount: int) -> None:
        self._validate(amount)
        self.dispatch_cents += amount

    def charge_upgrade(self, amount: int) -> None:
        self._validate(amount)
        self.upgrade_cents += amount

    def charge_penalty(self, amount: int) -> None:
        self._validate(amount)
        self.penalty_cents += amount
