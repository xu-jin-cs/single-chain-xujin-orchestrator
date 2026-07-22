"""Lightweight flow state container — engine-exclusive, agent has zero r/w access."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .utils import sha256_file

STATE_FILE = "engine_state.json"


@dataclass
class FlowState:
    flow_id: str = ""
    current_node: str = ""
    finished_nodes: set[str] = field(default_factory=set)
    deliverable_registry: list[dict[str, Any]] = field(default_factory=list)
    retry_count: int = 0
    max_retry: int = 3
    gate_logs: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "flow_id": self.flow_id,
            "current_node": self.current_node,
            "finished_nodes": sorted(self.finished_nodes),
            "deliverable_registry": self.deliverable_registry,
            "retry_count": self.retry_count,
            "max_retry": self.max_retry,
            "gate_logs": self.gate_logs,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FlowState:
        return cls(
            flow_id=d.get("flow_id", ""),
            current_node=d.get("current_node", ""),
            finished_nodes=set(d.get("finished_nodes", [])),
            deliverable_registry=d.get("deliverable_registry", []),
            retry_count=d.get("retry_count", 0),
            max_retry=d.get("max_retry", 3),
            gate_logs=d.get("gate_logs", []),
        )


def init_state(root: Path, agents: list[dict[str, Any]]) -> FlowState:
    """Create a fresh engine state for a new run."""
    state = FlowState(flow_id=uuid.uuid4().hex)
    state.current_node = agents[0]["name"] if agents else ""
    state.max_retry = agents[0].get("max_retry_count", 3) if agents else 3
    (root / "state_store").mkdir(parents=True, exist_ok=True)
    save_state(root, state)
    return state


def load_state(root: Path) -> FlowState:
    path = root / "state_store" / STATE_FILE
    if not path.exists():
        raise FileNotFoundError(f"Engine state not found: {path}")
    return FlowState.from_dict(json.loads(path.read_text(encoding="utf-8")))


def save_state(root: Path, state: FlowState) -> None:
    (root / "state_store").mkdir(parents=True, exist_ok=True)
    (root / "state_store" / STATE_FILE).write_text(
        json.dumps(state.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def register_deliverable(root: Path, state: FlowState, node_id: str, file_path: Path) -> dict[str, Any]:
    """Register an output deliverable with SHA256 hash into state."""
    fhash = sha256_file(file_path)
    rel = str(file_path.relative_to(root))
    entry = {"path": rel, "node_id": node_id, "sha256": fhash}
    # Replace if already registered for this path
    state.deliverable_registry = [d for d in state.deliverable_registry if d["path"] != rel]
    state.deliverable_registry.append(entry)
    save_state(root, state)
    return entry


def find_registry_entry(state: FlowState, path: str) -> dict[str, Any] | None:
    return next((d for d in state.deliverable_registry if d["path"] == path), None)
