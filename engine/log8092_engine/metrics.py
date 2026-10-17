"""Agregadores online y serializacion de KPIs normativos."""

from __future__ import annotations

from array import array
from collections import Counter
from dataclasses import dataclass, field
import math
from typing import Mapping

from .arithmetic import decimal_ratio, round_half_up_ratio
from .models import ShipmentRecord
from .opinion_model import OpinionOutcome


PRODUCTS = ("VIP_BLACK", "BUSINESS", "SME", "STANDARD")
AUDIENCES = ("VIP", "NORMAL", "INFLUENCER")
FAILURE_REASONS = ("INACCESSIBLE_ROUTE", "CUSTOMER_ABSENT", "OPERATIONAL_DELAY")


@dataclass(slots=True)
class Metrics:
    admitted: int = 0
    delivered: int = 0
    returned: int = 0
    unresolved: int = 0
    accepted_attempts: int = 0
    successful_attempts: int = 0
    failed_attempts: int = 0
    accepted_batches: int = 0
    rejected_dispatches: int = 0
    voluntary_hold_breaches: int = 0
    admitted_by_product: Counter[str] = field(default_factory=Counter)
    breached_by_product: Counter[str] = field(default_factory=Counter)
    failure_reasons: Counter[str] = field(default_factory=Counter)
    dispatch_rejections: Counter[str] = field(default_factory=Counter)
    upgrade_rejections: Counter[str] = field(default_factory=Counter)
    accepted_upgrade_quantity: Counter[str] = field(default_factory=Counter)
    accepted_upgrade_decisions: int = 0
    rejected_upgrade_decisions: int = 0
    dispatched_shipments: int = 0
    lead_seconds: array = field(default_factory=lambda: array("q"))
    eligible_by_audience: Counter[str] = field(default_factory=Counter)
    opinions_by_audience: Counter[str] = field(default_factory=Counter)
    rating_weight_sum_by_audience: Counter[str] = field(default_factory=Counter)
    impact_sum_by_audience: Counter[str] = field(default_factory=Counter)
    rating_sum: int = 0

    def on_admitted(self, shipment: ShipmentRecord) -> None:
        self.admitted += 1
        self.admitted_by_product[shipment.product] += 1

    def on_attempt_accepted(self, size: int) -> None:
        self.accepted_batches += 1
        self.accepted_attempts += size
        self.dispatched_shipments += size

    def on_attempt_result(self, success: bool, reason: str | None) -> None:
        if success:
            self.successful_attempts += 1
        else:
            self.failed_attempts += 1
            if reason:
                self.failure_reasons[reason] += 1

    def on_terminal(self, shipment: ShipmentRecord, opinion: OpinionOutcome) -> None:
        if shipment.state == "DELIVERED":
            self.delivered += 1
            assert shipment.delivered_at is not None
            self.lead_seconds.append(int((shipment.delivered_at - shipment.available_at).total_seconds()))
            breached = shipment.delivered_at > shipment.sla_deadline
        elif shipment.state == "RETURNED_TO_VAULT":
            self.returned += 1
            breached = True
        else:
            self.unresolved += 1
            breached = True
        if breached:
            self.breached_by_product[shipment.product] += 1
        self.eligible_by_audience[opinion.audience] += 1
        if opinion.submitted:
            self.opinions_by_audience[opinion.audience] += 1
            self.rating_sum += opinion.rating
            self.rating_weight_sum_by_audience[opinion.audience] += opinion.rating * opinion.impact_weight_bps
            self.impact_sum_by_audience[opinion.audience] += opinion.impact_weight_bps

    def on_administrative_unresolved(self, shipment: ShipmentRecord) -> None:
        """MET-010: cierre diagnostico sin callbacks, cargo ni opinion."""
        self.unresolved += 1
        self.breached_by_product[shipment.product] += 1

    def _lead_report(self) -> dict[str, int | float | None]:
        if not self.lead_seconds:
            return {"mean": None, "p50": None, "p95": None, "max": None}
        values = sorted(self.lead_seconds)
        n = len(values)
        def percentile(pct: int) -> int:
            index = math.ceil(pct * n / 100) - 1
            return round_half_up_ratio(values[index], 60)
        return {
            "mean": decimal_ratio(sum(values), 60 * n, 3),
            "p50": percentile(50),
            "p95": percentile(95),
            "max": round_half_up_ratio(values[-1], 60),
        }

    def report_sections(
        self,
        dispatch_reasons: tuple[str, ...],
        upgrade_reasons: tuple[str, ...],
    ) -> dict[str, object]:
        breached = sum(self.breached_by_product.values())
        by_product = {}
        for product in PRODUCTS:
            admitted = self.admitted_by_product[product]
            product_breached = self.breached_by_product[product]
            by_product[product] = {
                "admitted": admitted,
                "breached": product_breached,
                "breach_rate": decimal_ratio(product_breached, admitted, 6),
            }
        opinion_count = sum(self.opinions_by_audience.values())
        total_impact = sum(self.impact_sum_by_audience.values())
        weighted_numerator = sum(self.rating_weight_sum_by_audience.values())
        by_audience = {}
        for audience in AUDIENCES:
            impact = self.impact_sum_by_audience[audience]
            by_audience[audience] = {
                "eligible_recipients": self.eligible_by_audience[audience],
                "submitted_opinions": self.opinions_by_audience[audience],
                "weighted_score": decimal_ratio(
                    self.rating_weight_sum_by_audience[audience], impact, 3
                ),
            }
        average_batch = decimal_ratio(self.dispatched_shipments, self.accepted_batches, 3)
        efficiency = (
            decimal_ratio(self.dispatched_shipments - self.accepted_batches, self.dispatched_shipments, 6)
            if self.dispatched_shipments else 0.0
        )
        return {
            "counts": {
                "admitted": self.admitted,
                "delivered": self.delivered,
                "returned_to_vault": self.returned,
                "unresolved": self.unresolved,
                "accepted_attempts": self.accepted_attempts,
                "successful_attempts": self.successful_attempts,
                "failed_attempts": self.failed_attempts,
                "accepted_batches": self.accepted_batches,
                "rejected_dispatches": self.rejected_dispatches,
                "voluntary_hold_breaches": self.voluntary_hold_breaches,
            },
            "sla": {
                "breached": breached,
                "breach_rate": decimal_ratio(breached, self.admitted, 6),
                "by_product": by_product,
            },
            "failures": {
                "attempt_failure_rate": decimal_ratio(self.failed_attempts, self.accepted_attempts, 6),
                "delivery_failure_rate": decimal_ratio(self.returned + self.unresolved, self.admitted, 6),
                "by_reason": {reason: self.failure_reasons[reason] for reason in FAILURE_REASONS},
            },
            "rcp": {
                "weighted_score": decimal_ratio(weighted_numerator, total_impact, 3),
                "unweighted_score": decimal_ratio(self.rating_sum, opinion_count, 3),
                "submitted_opinions": opinion_count,
                "total_impact_weight_bps": total_impact,
                "by_audience": by_audience,
            },
            "lead_time_minutes": self._lead_report(),
            "batching": {
                "dispatched_shipments": self.dispatched_shipments,
                "accepted_batches": self.accepted_batches,
                "average_batch_size": average_batch or 0.0,
                "efficiency": efficiency,
            },
            "upgrades": {
                "accepted_decisions": self.accepted_upgrade_decisions,
                "rejected_decisions": self.rejected_upgrade_decisions,
                "accepted_quantity_by_type": {
                    name: self.accepted_upgrade_quantity[name]
                    for name in ("EXTRA_UNIT", "SPEED_SHIFT", "EXPANDED_CAPACITY")
                },
            },
            "diagnostics": {
                "dispatch_rejections": {name: self.dispatch_rejections[name] for name in dispatch_reasons},
                "upgrade_rejections": {name: self.upgrade_rejections[name] for name in upgrade_reasons},
            },
        }
