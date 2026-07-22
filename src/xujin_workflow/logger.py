"""Layered logging for offline execution."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class WorkflowLogger:
    """In-memory batch JSON-line logger."""

    def __init__(self, root: Path, level: int = 2) -> None:
        self.root = Path(root)
        self.level = level
        self.log_dir = self.root / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / f"{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        self._buffer: list[dict[str, Any]] = []

    def _record(self, record: dict[str, Any]) -> None:
        record["ts"] = datetime.now().isoformat()
        record["level"] = self.level
        self._buffer.append(record)

    def log(
        self,
        agent: str,
        status: str,
        message: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self._record({"agent": agent, "status": status, "message": message, **(extra or {})})

    def log_gate(
        self,
        agent: str,
        file_path: Path,
        passed: bool,
        reason: str,
        evidence_path: Path | None = None,
    ) -> None:
        if self.level < 3:
            return
        self._record({
            "agent": agent,
            "status": "gate_audit",
            "message": reason,
            "file_path": str(file_path),
            "passed": passed,
            **({"evidence_path": str(evidence_path)} if evidence_path else {}),
        })

    def flush(self) -> None:
        if self._buffer:
            with self.log_file.open("a", encoding="utf-8") as f:
                f.write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in self._buffer))
            self._buffer.clear()

    def summary(self, run_id: str, deliverables: list[dict[str, Any]]) -> None:
        self._record({"agent": "_SUMMARY_", "status": "completed", "message": "Run finished", "run_id": run_id, "deliverables": deliverables})
        self.flush()
