"""Lightweight file validation."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .utils import merge_rules


class ValidationError(Exception):
    pass


def _ext(filename: str) -> str:
    return Path(filename).suffix.lower()


def validate_file(
    file_path: Path,
    flow_data: dict[str, Any],
    global_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    global_wl = (global_config or {}).get("global_whitelist", {})
    global_bl = (global_config or {}).get("global_blacklist", {})
    flow_global = flow_data.get("global", {})
    whitelist = merge_rules(global_wl, flow_global.get("whitelist", {}))
    blacklist = merge_rules(global_bl, flow_global.get("blacklist", {}))
    ext = _ext(file_path.name)
    wl = [e.lower() for e in whitelist.get("extensions", [])]
    bl = [e.lower() for e in blacklist.get("extensions", [])]

    if bl and ext in bl:
        return {"path": str(file_path), "passed": False, "errors": [{"layer": "basic", "reason": f"Blacklisted extension: {ext}"}]}
    if wl and ext not in wl:
        return {"path": str(file_path), "passed": False, "errors": [{"layer": "basic", "reason": f"Extension not in whitelist: {ext}"}]}

    max_mb = whitelist.get("max_size_mb")
    if max_mb is not None and file_path.stat().st_size / (1024 * 1024) > max_mb:
        return {"path": str(file_path), "passed": False, "errors": [{"layer": "basic", "reason": f"File size exceeds limit {max_mb}MB"}]}

    return {"path": str(file_path), "passed": True, "errors": []}
