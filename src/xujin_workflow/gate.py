"""Agent gate + single-run anti-counterfeit hash ID."""
from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

from .utils import sha256_file


RUN_STATE_FILE = "run_state.json"


def load_run_state(root: Path) -> dict[str, Any]:
    path = root / "state_store" / RUN_STATE_FILE
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"run_id": None, "id_pool": {}, "agent_states": {}}


def save_run_state(root: Path, state: dict[str, Any]) -> None:
    path = root / "state_store" / RUN_STATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state), encoding="utf-8")


def clear_run_state(root: Path) -> dict[str, Any]:
    state_store = root / "state_store"
    for f in state_store.glob("*"):
        if f.is_file():
            f.unlink()
    state = {"run_id": uuid.uuid4().hex, "id_pool": {}, "agent_states": {}}
    save_run_state(root, state)
    return state


def generate_deliverable_id(file_path: Path, id_pool: dict[str, str], run_id: str) -> str:
    base = sha256_file(file_path)
    counter = 0
    candidate = base
    while candidate in id_pool:
        candidate = hashlib.sha256(f"{base}:{run_id}:{counter}".encode("utf-8")).hexdigest()
        counter += 1
    return candidate


def register_deliverable(
    root: Path,
    agent_name: str,
    file_path: Path,
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    st = state if state is not None else load_run_state(root)
    run_id = st["run_id"]
    if not run_id:
        raise RuntimeError("Run state not initialized")
    did = generate_deliverable_id(file_path, st["id_pool"], run_id)
    rel_path = str(file_path.relative_to(root))
    st["id_pool"][did] = rel_path
    if state is None:
        save_run_state(root, st)
    return {"id": did, "path": str(file_path), "relative_path": rel_path}


def set_agent_state(root: Path, agent_name: str, status: str, state: dict[str, Any] | None = None) -> None:
    st = state if state is not None else load_run_state(root)
    st["agent_states"][agent_name] = status
    if state is None:
        save_run_state(root, st)


def get_agent_state(root: Path, agent_name: str) -> str | None:
    return load_run_state(root)["agent_states"].get(agent_name)


def verify_upstream_ids(root: Path, file_paths: list[Path], state: dict[str, Any] | None = None) -> dict[str, Any]:
    id_pool = (state if state is not None else load_run_state(root)).get("id_pool", {})
    values = set(id_pool.values())
    missing = [str(fp) for fp in file_paths if str(fp.relative_to(root)) not in values]
    return {"passed": not missing, "missing": missing}
