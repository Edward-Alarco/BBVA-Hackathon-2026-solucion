"""Hashes de entrega y comprobacion de inputs publicados."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def public_data_pristine(data_dir: Path) -> bool:
    manifest_path = data_dir / "generation_manifest.json"
    if not manifest_path.is_file():
        return True
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return all(
            (data_dir / name).is_file() and sha256_file(data_dir / name) == expected
            for name, expected in manifest["public_files"].items()
        )
    except (OSError, ValueError, KeyError, TypeError):
        return False


def protected_files_pristine(candidate_path: Path, data_dir: Path) -> bool:
    """Valida el manifest del kit cuando existe; la entrega queda excluida."""
    kit_root = candidate_path.resolve().parent
    manifest_path = kit_root / "protected_files.sha256"
    if not manifest_path.is_file():
        return public_data_pristine(data_dir)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("schema_version") != "0.1.0":
            return False
        files = manifest["files"]
        return all(
            relative != "candidate_strategy.py"
            and (kit_root / relative).is_file()
            and sha256_file(kit_root / relative) == expected
            for relative, expected in files.items()
        )
    except (OSError, ValueError, KeyError, TypeError):
        return False
