"""Entrada estable de consola para el Engine."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .config import ConfigurationError, load_config
from .runner import EngineRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Simulador LOG-8092")
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--strategy", type=Path, required=True)
    parser.add_argument("--interfaces", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--private", type=Path)
    parser.add_argument("--progress-events", type=int, default=0, help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.data, args.private)
        result = EngineRunner(
            config, args.strategy, args.interfaces, args.output,
            progress_every_events=args.progress_events,
        ).run()
    except ConfigurationError as exc:
        print(f"INPUT_ERROR: {exc}", file=sys.stderr)
        return 4
    report = result.report
    print(f"LOG-8092 | {report['scenario']['scenario_id']} | {result.status}")
    print(
        "envios={admitted} entregados={delivered} SLA={sla} RCP={rcp} "
        "lead={lead}min coste={cost} RSS={rss}".format(
            admitted=report["counts"]["admitted"],
            delivered=report["counts"]["delivered"],
            sla=report["sla"]["breach_rate"],
            rcp=report["rcp"]["weighted_score"],
            lead=report["lead_time_minutes"]["mean"],
            cost=report["costs"]["total_cents"],
            rss=report["resources"]["peak_rss_bytes"],
        )
    )
    print(f"reporte={result.report_path}")
    return 0 if result.status == "COMPLETED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
