"""Build independent development fixtures; never edits the published datasets.

Run from the kit root: python validate_variants.py
These are local integration checks, not the hidden evaluation scenarios.
"""
import csv
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parent
if not (ROOT / "run.py").exists():
    ROOT = ROOT.parent.parent


def main():
    reports = ROOT / "output" / "development_checks"
    reports.mkdir(parents=True, exist_ok=True)
    scratch = ROOT / "output" / "_temporary_fixtures"
    scratch.mkdir(parents=True, exist_ok=True)
    results = []
    with (ROOT / "data" / "shipments.csv").open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        source = list(reader)
    for index, name in enumerate(("renamed_catalog", "rural_holidays", "cluster_burst", "price_speed_variant")):
        rng = random.Random(9000 + index)
        with tempfile.TemporaryDirectory(prefix="bbva-development-", dir=scratch) as directory:
            target = Path(directory)
            assert target.resolve().is_relative_to(scratch.resolve())
            for file in ("rules.toml", "scenario.toml", "holidays.csv", "carriers.json"):
                shutil.copy2(ROOT / "data" / file, target / file)
            catalog = json.loads((target / "carriers.json").read_text(encoding="utf-8"))
            rng.shuffle(catalog["carriers"])
            for i, carrier in enumerate(catalog["carriers"]):
                carrier["carrier_id"] = f"DEV_{i}_{index}"
                carrier["display_name"] = carrier["carrier_id"]
                if name == "price_speed_variant":
                    carrier["base_fee_cents"] = carrier["base_fee_cents"] * (70 + 13 * i) // 100
                    carrier["speed_kmh"] = max(10, carrier["speed_kmh"] * (75 + 12 * i) // 100)
                    carrier["batch_capacity"] = max(1, carrier["batch_capacity"] // 2)
            (target / "carriers.json").write_text(json.dumps(catalog), encoding="utf-8")
            rows = [dict(r) for r in rng.sample(source, 500)]
            if name == "rural_holidays":
                for i, row in enumerate(rows):
                    row["zone"] = "RURAL" if i % 2 else "REMOTA"
                    row["delivery_cluster_id"] = f"R{i // 4}"
                (target / "holidays.csv").write_text("date,name\n2026-01-06,Development\n2026-01-07,Development\n2026-02-06,Development\n", encoding="utf-8")
            if name == "cluster_burst":
                start = datetime.fromisoformat("2026-01-05T08:00:00-05:00")
                for i, row in enumerate(rows):
                    row["available_at"] = (start + timedelta(minutes=(i // 25) * 15)).isoformat()
                    row["delivery_cluster_id"] = f"B{i // 25}"
                    row["zone"] = ("URBANA", "SUBURBANA", "RURAL", "REMOTA")[(i // 25) % 4]
            rows.sort(key=lambda r: (r["available_at"], r["shipment_id"]))
            with (target / "shipments.csv").open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            manifest = {"public_files": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in target.iterdir()}}
            (target / "generation_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            output = reports / f"{name}.json"
            result = subprocess.run([sys.executable, "-S", str(ROOT / "run.py"), "--data", str(target), "--strategy", str(ROOT / "submission" / "candidate_strategy.py"), "--output", str(output)], cwd=ROOT, capture_output=True, text=True, timeout=900)
            print(result.stdout, end="")
            if result.returncode:
                raise RuntimeError(result.stderr + result.stdout)
            report = json.loads(output.read_text(encoding="utf-8"))
            assert report["status"] == "COMPLETED", name
            assert report["counts"]["unresolved"] == 0, name
            assert report["counts"]["voluntary_hold_breaches"] == 0, name
            assert report["sla"]["breach_rate"] <= .06, name
            assert report["integrity"]["protected_files_pristine"], name
            assert report["counts"]["rejected_dispatches"] == 0, name
            results.append({"development_fixture": name, "counts": report["counts"], "sla": report["sla"]["breach_rate"], "candidate_sha256": report["integrity"]["candidate_sha256"]})
    (reports / "summary.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("4/4 local development fixtures passed (not official hidden tests).")


if __name__ == "__main__":
    main()
