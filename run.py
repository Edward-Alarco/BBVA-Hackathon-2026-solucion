"""Ejecuta el caso publico; este fichero esta protegido y no se entrega editado."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
EMBEDDED_ENGINE = ROOT / "engine"
SOURCE_ENGINE = ROOT.parent / "caso_completo" / "src"
sys.path.insert(0, str(EMBEDDED_ENGINE if EMBEDDED_ENGINE.is_dir() else SOURCE_ENGINE))

from log8092_engine.cli import main


if __name__ == "__main__":
    raise SystemExit(main([
        "--data", str(ROOT / "data"),
        "--strategy", str(ROOT / "candidate_strategy.py"),
        "--interfaces", str(ROOT / "interfaces.py"),
        "--output", str(ROOT / "output" / "performance_report.json"),
        *sys.argv[1:],
    ]))
