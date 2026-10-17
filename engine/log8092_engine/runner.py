"""Bucle de eventos: unico propietario del reloj y los estados terminales."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import heapq
from pathlib import Path
import sys
import time
from typing import Any, Iterator, Mapping

from .arithmetic import ceil_div
from .candidate_worker import WorkerClient, WorkerError
from .carrier_service import EngineCarrierService
from .config import EngineConfig, stream_shipments
from .fleet import FleetManager
from .integrity import protected_files_pristine, sha256_file
from .ledger import Ledger
from .metrics import Metrics
from .models import ScheduledAttempt, ShipmentInput, ShipmentRecord
from .opinion_model import evaluate_opinion
from .public_codec import (
    api_module,
    decision_policy,
    failure_policy,
    rcp_policy,
    scenario_calendar,
    shipment_view,
)
from .report import write_report


PRIORITY_INTERNAL = 0
PRIORITY_RESULT = 1
PRIORITY_PLANNING = 2
PRIORITY_ARRIVAL = 3
PRIORITY_TICK = 4
PRIORITY_HOLD = 5


@dataclass(frozen=True, slots=True)
class RunResult:
    status: str
    report: dict[str, Any]
    report_path: Path


class EngineRunner:
    def __init__(
        self,
        config: EngineConfig,
        candidate_path: Path,
        interfaces_path: Path,
        output_path: Path,
        progress_every_events: int = 0,
    ) -> None:
        self.config = config
        self.candidate_path = candidate_path.resolve()
        self.interfaces_path = interfaces_path.resolve()
        self.output_path = output_path.resolve()
        self.progress_every_events = max(0, progress_every_events)
        if str(self.interfaces_path.parent) not in sys.path:
            sys.path.insert(0, str(self.interfaces_path.parent))

        self.shipments: dict[str, ShipmentRecord] = {}
        self.metrics = Metrics()
        self.ledger = Ledger(
            config.scenario.reference_budget_cents,
            int(config.rules["pricing"]["contingency_threshold_bps"]),
        )
        self.fleet = FleetManager(config.carriers, config.scenario.simulation_start)
        self.events: list[tuple[datetime, int, str, int, str, Any]] = []
        self._sequence = 0
        self._arrival_iterator: Iterator[ShipmentInput] | None = None
        self._arrival_lookahead: ShipmentInput | None = None
        self._period_upgrade_quantities: dict[tuple[int, str, str], int] = {}
        self.now = config.scenario.simulation_start
        self.simulation_end = config.scenario.admission_end
        self.status = "COMPLETED"
        self.status_detail: str | None = None

        self.service = EngineCarrierService(
            config.rules,
            config.holidays,
            self.fleet,
            self.ledger,
            self.shipments,
            self.metrics,
            config.secrets.failure_key,
            self._on_dispatch_accepted,
        )
        self.worker = WorkerClient(
            self.candidate_path,
            self.interfaces_path,
            timeout_seconds=30.0,
        )
        self._calendar_view = None
        self._failure_view = None
        self._rcp_view = None
        self._decision_view = None

    def _push(self, when: datetime, priority: int, order_key: str, kind: str, payload: Any = None) -> None:
        self._sequence += 1
        heapq.heappush(
            self.events, (when, priority, order_key, self._sequence, kind, payload)
        )

    def _validate_and_find_end(self) -> tuple[int, datetime]:
        count = 0
        latest: datetime | None = None
        for shipment in stream_shipments(self.config):
            count += 1
            latest = shipment.sla_deadline if latest is None else max(latest, shipment.sla_deadline)
        drain_days = int(self.config.rules["simulation"]["drain_days_after_latest_deadline"])
        basis = latest if latest is not None else self.config.scenario.admission_end
        return count, basis + timedelta(days=drain_days)

    def _schedule_next_arrival_group(self) -> None:
        assert self._arrival_iterator is not None
        first = self._arrival_lookahead
        if first is None:
            try:
                first = next(self._arrival_iterator)
            except StopIteration:
                return
        timestamp = first.available_at
        group = [first]
        self._arrival_lookahead = None
        for value in self._arrival_iterator:
            if value.available_at != timestamp:
                self._arrival_lookahead = value
                break
            group.append(value)
        chunk_size = int(self.config.rules["simulation"]["shipment_callback_chunk_size"])
        chunks = [tuple(group[index:index + chunk_size]) for index in range(0, len(group), chunk_size)]
        for index, chunk in enumerate(chunks):
            self._push(
                timestamp,
                PRIORITY_ARRIVAL,
                f"{index:09d}",
                "ARRIVAL",
                (chunk, index == len(chunks) - 1),
            )

    def _schedule_hold_audit(self, record: ShipmentRecord) -> None:
        hold_seconds = int(self.config.rules["simulation"]["max_voluntary_hold_minutes"]) * 60
        tick_seconds = int(self.config.rules["simulation"]["dispatch_tick_minutes"]) * 60
        target = record.ready_at + timedelta(seconds=hold_seconds)
        delta = max(0, int((target - self.config.scenario.simulation_start).total_seconds()))
        tick_index = ceil_div(delta, tick_seconds)
        audit_at = self.config.scenario.simulation_start + timedelta(seconds=tick_index * tick_seconds)
        if audit_at < self.simulation_end:
            self._push(
                audit_at,
                PRIORITY_HOLD,
                record.shipment_id,
                "HOLD_AUDIT",
                (record.shipment_id, record.ready_epoch),
            )

    def _on_dispatch_accepted(
        self,
        carrier_id: str,
        unit_id: str,
        return_at: datetime,
        attempts: tuple[ScheduledAttempt, ...],
    ) -> None:
        batch_id = attempts[0].batch_id
        self._push(
            return_at,
            PRIORITY_INTERNAL,
            f"{carrier_id}|{unit_id}",
            "UNIT_RETURN",
            (carrier_id, unit_id, batch_id),
        )
        for attempt in attempts:
            self._push(
                attempt.eta,
                PRIORITY_RESULT,
                f"{attempt.batch_id}|{attempt.shipment_id}",
                "ATTEMPT_RESULT",
                attempt,
            )

    def _dispatch_context(self):
        api = api_module()
        return api.DispatchContext(
            now=self.now,
            reference_budget_cents=self.ledger.reference_budget_cents,
            spent_cents=self.ledger.spent_cents,
            contingency_threshold_cents=self.ledger.contingency_threshold_cents,
            carriers=self.service.snapshot(),
            calendar=self._calendar_view,
            failure_policy=self._failure_view,
            rcp_policy=self._rcp_view,
            decision_policy=self._decision_view,
        )

    def _planning_context(self, period_index: int):
        api = api_module()
        return api.MonthlyPlanningContext(
            now=self.now,
            period_index=period_index,
            reference_budget_cents=self.ledger.reference_budget_cents,
            spent_cents=self.ledger.spent_cents,
            contingency_threshold_cents=self.ledger.contingency_threshold_cents,
            carriers=self.service.snapshot(),
            calendar=self._calendar_view,
            failure_policy=self._failure_view,
            rcp_policy=self._rcp_view,
            upgrades_enabled=self.config.scenario.upgrades_enabled,
            decision_policy=self._decision_view,
        )

    def _reject_upgrade(self, reason: str) -> None:
        self.metrics.rejected_upgrade_decisions += 1
        self.metrics.upgrade_rejections[reason] += 1

    def _apply_upgrade_decision(self, decision: Any, period_index: int) -> None:
        try:
            carrier_id = str(decision.carrier_id)
            upgrade_type = str(decision.upgrade_type)
            quantity = decision.quantity
        except AttributeError:
            raise WorkerError("on_monthly_planning devolvio una decision no contractual")
        state = self.fleet.state(carrier_id)
        if state is None:
            self._reject_upgrade("UNKNOWN_CARRIER")
            return
        if upgrade_type not in self.config.rules["upgrades"]:
            self._reject_upgrade("UNKNOWN_UPGRADE")
            return
        if not self.config.scenario.upgrades_enabled or upgrade_type not in state.definition.supported_upgrades:
            self._reject_upgrade("UNSUPPORTED_UPGRADE")
            return
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            self._reject_upgrade("INVALID_QUANTITY")
            return
        policy = self.config.rules["upgrades"][upgrade_type]
        key = (period_index, carrier_id, upgrade_type)
        accepted = self._period_upgrade_quantities.get(key, 0)
        if accepted + quantity > int(policy["max_per_carrier_period"]):
            self._reject_upgrade("PER_PERIOD_LIMIT_EXCEEDED")
            return
        cost = int(policy["cost_cents"]) * quantity
        self.ledger.charge_upgrade(cost)
        period_days = int(self.config.rules["simulation"]["planning_period_days"])
        expires_at = self.config.scenario.simulation_start + timedelta(
            days=(period_index + 1) * period_days
        )
        self.fleet.add_upgrade(
            carrier_id, upgrade_type, quantity, period_index, self.now, expires_at
        )
        self._period_upgrade_quantities[key] = accepted + quantity
        self.metrics.accepted_upgrade_decisions += 1
        self.metrics.accepted_upgrade_quantity[upgrade_type] += quantity

    def _terminalize(self, record: ShipmentRecord) -> None:
        outcome = evaluate_opinion(
            record,
            record.delivered_at if record.state == "DELIVERED" else None,
            self.config.calendar,
            self.config.rules,
            self.config.secrets.opinion_key,
        )
        self.metrics.on_terminal(record, outcome)

    def _handle_attempt_result(self, attempt: ScheduledAttempt) -> None:
        record = self.shipments.get(attempt.shipment_id)
        if record is None or record.state != "IN_TRANSIT" or record.attempt_number != attempt.attempt_number:
            return
        state = self.fleet.states[attempt.carrier_id]
        success = attempt.failure_reason is None
        self.fleet.register_result(state, success)
        self.metrics.on_attempt_result(success, attempt.failure_reason)
        api = api_module()
        if success:
            record.state = "DELIVERED"
            record.delivered_at = attempt.eta
            record.terminal_at = attempt.eta
            self._terminalize(record)
            result = api.DeliveryAttemptResult(
                shipment=shipment_view(record),
                carrier_id=attempt.carrier_id,
                batch_id=attempt.batch_id,
                attempt_number=attempt.attempt_number,
                occurred_at=attempt.eta,
                terminal=True,
                failure_reason=None,
            )
            self.worker.call("on_delivery_succeeded", result)
            return

        if attempt.failure_reason == "INACCESSIBLE_ROUTE":
            record.required_capabilities.add("HARD_ACCESS")
        max_attempts = int(self.config.rules["retry"]["max_attempts"])
        if attempt.attempt_number >= max_attempts:
            record.state = "RETURNED_TO_VAULT"
            record.terminal_at = attempt.eta
            self.ledger.charge_penalty(int(self.config.rules["pricing"]["terminal_penalty_cents"]))
            terminal = True
            self._terminalize(record)
        else:
            wait = timedelta(minutes=int(self.config.rules["retry"]["wait_minutes"]))
            record.state = "WAITING_RETRY"
            record.attempt_number += 1
            record.ready_at = attempt.eta + wait
            record.retry_eligible_at = record.ready_at
            terminal = False
            self._push(
                record.ready_at,
                PRIORITY_INTERNAL,
                record.shipment_id,
                "RETRY_READY",
                record.shipment_id,
            )
        result = api.DeliveryAttemptResult(
            shipment=shipment_view(record),
            carrier_id=attempt.carrier_id,
            batch_id=attempt.batch_id,
            attempt_number=attempt.attempt_number,
            occurred_at=attempt.eta,
            terminal=terminal,
            failure_reason=attempt.failure_reason,
        )
        self.worker.call("on_delivery_failed", result)

    def _process_event(self, kind: str, payload: Any) -> bool:
        if kind == "UNIT_RETURN":
            carrier_id, unit_id, batch_id = payload
            self.fleet.release(carrier_id, unit_id, batch_id, self.now)
        elif kind == "RETRY_READY":
            record = self.shipments.get(payload)
            if record is not None and record.state == "WAITING_RETRY" and record.ready_at <= self.now:
                record.state = "READY"
                record.ready_epoch += 1
                self._schedule_hold_audit(record)
        elif kind == "UPGRADE_EXPIRY":
            self.fleet.expire_period(int(payload), self.now)
        elif kind == "ATTEMPT_RESULT":
            self._handle_attempt_result(payload)
        elif kind == "PLANNING":
            period_index = int(payload)
            decisions = self.worker.call(
                "on_monthly_planning", self._planning_context(period_index)
            )
            if not isinstance(decisions, tuple):
                raise WorkerError("on_monthly_planning debe devolver tuple")
            for decision in decisions:
                self._apply_upgrade_decision(decision, period_index)
        elif kind == "ARRIVAL":
            chunk, last_chunk = payload
            records = []
            for item in chunk:
                record = ShipmentRecord.from_input(item)
                self.shipments[record.shipment_id] = record
                self.metrics.on_admitted(record)
                self._schedule_hold_audit(record)
                records.append(shipment_view(record))
            self.worker.call("on_shipments_available", self.now, tuple(records))
            if last_chunk:
                self._schedule_next_arrival_group()
        elif kind == "TICK":
            self.worker.call("on_dispatch_tick", self._dispatch_context())
            tick = timedelta(minutes=int(self.config.rules["simulation"]["dispatch_tick_minutes"]))
            next_tick = self.now + tick
            if next_tick < self.simulation_end:
                self._push(next_tick, PRIORITY_TICK, "", "TICK")
        elif kind == "HOLD_AUDIT":
            shipment_id, epoch = payload
            record = self.shipments.get(shipment_id)
            if (
                record is not None
                and record.state == "READY"
                and record.ready_epoch == epoch
                and record.hold_audited_epoch < epoch
            ):
                record.hold_audited_epoch = epoch
                if self.service.feasible_singleton_exists(record):
                    self.metrics.voluntary_hold_breaches += 1
        elif kind == "CUTOFF":
            self._normal_cutoff()
            return False
        return True

    def _normal_cutoff(self) -> None:
        penalty = int(self.config.rules["pricing"]["terminal_penalty_cents"])
        for shipment_id in sorted(self.shipments):
            record = self.shipments[shipment_id]
            if record.terminal:
                continue
            record.state = "UNRESOLVED"
            record.terminal_at = self.now
            self.ledger.charge_penalty(penalty)
            self._terminalize(record)
        self.status = "COMPLETED"

    def _administrative_close(self) -> None:
        for record in self.shipments.values():
            if not record.terminal:
                record.state = "UNRESOLVED"
                record.terminal_at = self.now
                self.metrics.on_administrative_unresolved(record)

    def _build_report(self) -> dict[str, Any]:
        sections = self.metrics.report_sections(
            self.service.rejection_reasons,
            tuple(str(x) for x in self.config.rules["upgrade_policy"]["rejection_precedence"]),
        )
        sections["diagnostics"]["status_detail"] = self.status_detail
        sections["diagnostics"]["carrier_dispatch"] = {
            carrier_id: {
                "accepted_batches": self.service.accepted_batches_by_carrier[carrier_id],
                "accepted_attempts": self.service.accepted_shipments_by_carrier[carrier_id],
                "cost_cents": self.service.dispatch_cents_by_carrier[carrier_id],
            }
            for carrier_id in sorted(self.service.accepted_batches_by_carrier)
        }
        report = {
            "schema_version": "0.4.0",
            "spec_version": "0.4.0",
            "scenario": {
                "scenario_id": self.config.scenario.scenario_id,
                "seed_fingerprint": self.config.scenario.seed_fingerprint,
                "simulation_start": self.config.scenario.simulation_start.isoformat(),
                "admission_end": self.config.scenario.admission_end.isoformat(),
                "simulation_end": self.simulation_end.isoformat(),
            },
            "status": self.status,
            **{key: sections[key] for key in (
                "counts", "sla", "failures", "rcp", "upgrades",
                "lead_time_minutes", "batching", "diagnostics",
            )},
            "costs": {
                "reference_budget_cents": self.ledger.reference_budget_cents,
                "contingency_threshold_cents": self.ledger.contingency_threshold_cents,
                "dispatch_cents": self.ledger.dispatch_cents,
                "upgrade_cents": self.ledger.upgrade_cents,
                "penalty_cents": self.ledger.penalty_cents,
                "total_cents": self.ledger.spent_cents,
                "over_reference_cents": self.ledger.over_reference_cents,
                "over_contingency_cents": self.ledger.over_contingency_cents,
                "contingency_used": self.ledger.spent_cents > self.ledger.reference_budget_cents,
                "contingency_exceeded": (
                    self.ledger.spent_cents > self.ledger.contingency_threshold_cents
                ),
            },
            "resources": {
                "cpu_seconds": round(self.worker.cpu_seconds, 6),
                "peak_rss_bytes": self.worker.peak_rss_bytes,
            },
            "integrity": {
                "candidate_sha256": sha256_file(self.candidate_path),
                "protected_files_pristine": protected_files_pristine(
                    self.candidate_path, self.config.data_dir
                ),
            },
        }
        return report

    def run(self) -> RunResult:
        _, self.simulation_end = self._validate_and_find_end()
        if not protected_files_pristine(self.candidate_path, self.config.data_dir):
            self.status = "INTEGRITY_ERROR"
            self.status_detail = "un input protegido no coincide con generation_manifest.json"
            report = self._build_report()
            write_report(self.output_path, report)
            return RunResult(self.status, report, self.output_path)

        self._arrival_iterator = iter(stream_shipments(self.config))
        self._schedule_next_arrival_group()
        start = self.config.scenario.simulation_start
        period_days = int(self.config.rules["simulation"]["planning_period_days"])
        period_count = int(self.config.rules["simulation"]["planning_period_count"])
        for period in range(period_count):
            planning_at = start + timedelta(days=period * period_days)
            self._push(planning_at, PRIORITY_PLANNING, f"{period:03d}", "PLANNING", period)
            expiry_at = start + timedelta(days=(period + 1) * period_days)
            self._push(expiry_at, PRIORITY_INTERNAL, f"{period:03d}", "UPGRADE_EXPIRY", period)
        self._push(start, PRIORITY_TICK, "", "TICK")
        self._push(self.simulation_end, PRIORITY_PLANNING, "CUTOFF", "CUTOFF")

        self._calendar_view = scenario_calendar(
            self.config.holidays, str(self.config.rules["timezone"])
        )
        self._failure_view = failure_policy(self.config.rules)
        self._rcp_view = rcp_policy(self.config.rules)
        self._decision_view = decision_policy(self.config.rules)

        worker_started = False
        try:
            self.service.set_now(start)
            self.worker.start(self.service)
            worker_started = True
            keep_running = True
            processed_events = 0
            while self.events and keep_running:
                when, _, _, _, kind, payload = heapq.heappop(self.events)
                self.now = when
                self.service.set_now(when)
                keep_running = self._process_event(kind, payload)
                processed_events += 1
                if self.progress_every_events and processed_events % self.progress_every_events == 0:
                    print(
                        "PROGRESS "
                        f"events={processed_events} now={self.now.isoformat()} "
                        f"admitted={self.metrics.admitted} active="
                        f"{self.metrics.admitted - self.metrics.delivered - self.metrics.returned - self.metrics.unresolved} "
                        f"spent={self.ledger.spent_cents}",
                        file=sys.stderr,
                        flush=True,
                    )
                    print(
                        "PROGRESS_CARRIERS "
                        + " ".join(
                            f"{carrier_id}:b{self.service.accepted_batches_by_carrier[carrier_id]}"
                            f"/s{self.service.accepted_shipments_by_carrier[carrier_id]}"
                            f"/c{self.service.dispatch_cents_by_carrier[carrier_id]}"
                            for carrier_id in sorted(self.service.accepted_batches_by_carrier)
                        ),
                        file=sys.stderr,
                        flush=True,
                    )
        except WorkerError as exc:
            self.status = exc.status
            self.status_detail = str(exc)[-4000:]
        except BaseException as exc:
            self.status = "STRATEGY_ERROR"
            self.status_detail = f"error interno durante hook: {type(exc).__name__}: {exc}"
        finally:
            if worker_started:
                try:
                    self.worker.close()
                except WorkerError as exc:
                    if self.status == "COMPLETED":
                        self.status = exc.status
                        self.status_detail = str(exc)

        if self.status != "COMPLETED" or self.now < self.simulation_end:
            self._administrative_close()
        report = self._build_report()
        write_report(self.output_path, report)
        return RunResult(self.status, report, self.output_path)
