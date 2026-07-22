"""General utilities."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_global_config(source_root: Path) -> dict[str, Any]:
    path = source_root / "global_config.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def merge_rules(global_rule: dict[str, Any], local_rule: dict[str, Any] | None) -> dict[str, Any]:
    result = dict(global_rule)
    if not local_rule:
        return result
    for key, value in local_rule.items():
        result[key] = ({**result[key], **value} if isinstance(value, dict) and isinstance(result.get(key), dict) else value)
    return result


def resolve_path(base_dir: Path, path_str: str) -> Path:
    target = (base_dir / path_str).resolve()
    base = base_dir.resolve()
    if not str(target).startswith(str(base)):
        raise ValueError(f"Path traversal blocked: {path_str}")
    return target


def ensure_ascii_id(name: str) -> str:
    forbidden = {'{', '}', '[', ']', ':', '"', "'", '<', '>'}
    return "".join(c for c in name if c not in forbidden)
