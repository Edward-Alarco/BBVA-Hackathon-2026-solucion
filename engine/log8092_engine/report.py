"""Composicion y escritura atomica del reporte autoritativo."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any


def validate_report(report: dict[str, Any]) -> None:
    required = {
        "schema_version", "spec_version", "scenario", "status", "counts",
        "sla", "failures", "rcp", "costs", "upgrades", "lead_time_minutes",
        "batching", "diagnostics", "resources", "integrity",
    }
    if set(report) != required:
        raise ValueError(f"reporte con claves invalidas: {sorted(set(report) ^ required)}")
    if report["schema_version"] != "0.4.0" or report["spec_version"] != "0.4.0":
        raise ValueError("version de reporte invalida")
    if report["status"] not in {
        "COMPLETED", "STRATEGY_ERROR", "TIMEOUT", "OOM", "INTEGRITY_ERROR",
    }:
        raise ValueError("status de reporte invalido")
    counts = report["counts"]
    if any(not isinstance(value, int) or value < 0 for value in counts.values()):
        raise ValueError("conteos de reporte invalidos")
    if counts["delivered"] + counts["returned_to_vault"] + counts["unresolved"] != counts["admitted"]:
        raise ValueError("la identidad de conteos terminales no se cumple")
    costs = report["costs"]
    expected_cost_keys = {
        "reference_budget_cents",
        "contingency_threshold_cents",
        "dispatch_cents",
        "upgrade_cents",
        "penalty_cents",
        "total_cents",
        "over_reference_cents",
        "over_contingency_cents",
        "contingency_used",
        "contingency_exceeded",
    }
    if set(costs) != expected_cost_keys:
        raise ValueError("claves contables invalidas")
    integer_cost_keys = expected_cost_keys - {
        "contingency_used", "contingency_exceeded"
    }
    if any(
        isinstance(costs[key], bool)
        or not isinstance(costs[key], int)
        or costs[key] < 0
        for key in integer_cost_keys
    ):
        raise ValueError("importe contable invalido")
    if any(
        not isinstance(costs[key], bool)
        for key in ("contingency_used", "contingency_exceeded")
    ):
        raise ValueError("indicador contable invalido")
    if costs["contingency_threshold_cents"] < costs["reference_budget_cents"]:
        raise ValueError("umbral de contingencia inferior a la referencia")
    if costs["total_cents"] != costs["dispatch_cents"] + costs["upgrade_cents"] + costs["penalty_cents"]:
        raise ValueError("la identidad contable no se cumple")
    if costs["over_reference_cents"] != max(
        0, costs["total_cents"] - costs["reference_budget_cents"]
    ):
        raise ValueError("el exceso sobre referencia es inconsistente")
    if costs["over_contingency_cents"] != max(
        0, costs["total_cents"] - costs["contingency_threshold_cents"]
    ):
        raise ValueError("el exceso sobre contingencia es inconsistente")
    if costs["contingency_used"] != (
        costs["total_cents"] > costs["reference_budget_cents"]
    ):
        raise ValueError("el indicador de uso de contingencia es inconsistente")
    if costs["contingency_exceeded"] != (
        costs["total_cents"] > costs["contingency_threshold_cents"]
    ):
        raise ValueError("el indicador de exceso de contingencia es inconsistente")


def write_report(path: Path, report: dict[str, Any]) -> None:
    validate_report(report)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise
