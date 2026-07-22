"""Workflow data model and directory operations."""
from __future__ import annotations

import json
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


DEFAULT_FLOW_YML = """name: {name}
description: ""
aliases: ["/{name}"]
input_schema:
  type: object
  required: ["input"]
  properties:
    input:
      type: string
      description: "输入给 {name} 工作流的首节点上下文或文件路径"
rules: []
mode: beginner
offline_command: /xujin
log_level: 2
agents: []
global:
  whitelist:
    extensions: []
    max_size_mb: 50
  blacklist:
    extensions: []
  validation:
    enable_basic: true
"""


WORKFLOW_DIRS = [
    "templates",
    "validate_rules",
    "flow_fragments",
    "input_source",
    "output_delivery",
    "logs",
    "state_store",
    "versions",
]


def sanitize_name(name: str) -> str:
    return re.sub(r"\s+", "_", re.sub(r"[\\/:*?\"<>|]", "_", name.strip())) or "workflow"


def ensure_workflow_dirs(root: Path) -> None:
    for d in WORKFLOW_DIRS:
        (root / d).mkdir(parents=True, exist_ok=True)
        (root / d / ".gitkeep").touch(exist_ok=True)


def create_workflow(root: Path, name: str, advanced: bool = False) -> Path:
    root = Path(root)
    flow_path = root / "flow.yml"
    if flow_path.exists():
        raise FileExistsError(f"Workflow already exists: {flow_path}")
    ensure_workflow_dirs(root)
    flow_path.write_text(DEFAULT_FLOW_YML.format(name=name).replace("mode: beginner", f"mode: {'advanced' if advanced else 'beginner'}"), encoding="utf-8")
    return flow_path


def load_flow(root: Path) -> dict[str, Any]:
    data = yaml.safe_load((Path(root) / "flow.yml").read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def save_flow(root: Path, data: dict[str, Any]) -> None:
    (Path(root) / "flow.yml").write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _normalize_template(template: str) -> str:
    """Strip markdown code block language prefixes (json\\n, yaml\\n, etc.) from template text."""
    t = template.strip()
    for prefix in ("json\n", "json\r\n", "yaml\n", "yml\n", "xml\n", "html\n", "md\n", "markdown\n"):
        if t.startswith(prefix):
            return t[len(prefix):]
    return template


def _normalize_deliverables(deliverables: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not deliverables:
        return []
    return [{**d, "template": _normalize_template(d.get("template", ""))} for d in deliverables]


def add_agent(
    root: Path,
    agent_name: str,
    identity: str = "",
    skills: list[str] | None = None,
    rules: list[str] | None = None,
    deliverables: list[dict[str, Any]] | None = None,
    next_agents: list[str] | None = None,
    branch_conditions: dict[str, Any] | None = None,
    max_retry_count: int = 3,
) -> None:
    data = load_flow(root)
    agents = data.setdefault("agents", [])
    if any(a.get("name") == agent_name for a in agents):
        raise ValueError(f"Agent '{agent_name}' already exists")
    agents.append({
        "name": agent_name,
        "identity": identity,
        "skills": skills or [],
        "rules": rules or [],
        "deliverables": _normalize_deliverables(deliverables),
        "next_agents": next_agents or [],
        "branch_conditions": branch_conditions or {},
        "max_retry_count": max_retry_count,
    })
    save_flow(root, data)


def update_agent(root: Path, agent_name: str, **fields: Any) -> None:
    data = load_flow(root)
    agent = next((a for a in data.get("agents", []) if a.get("name") == agent_name), None)
    if agent is None:
        raise ValueError(f"Agent '{agent_name}' not found")
    if "deliverables" in fields:
        fields["deliverables"] = _normalize_deliverables(fields["deliverables"])
    agent.update(fields)
    save_flow(root, data)


def delete_agent(root: Path, agent_name: str) -> None:
    data = load_flow(root)
    data["agents"] = [a for a in data.get("agents", []) if a.get("name") != agent_name]
    save_flow(root, data)


def list_agents(root: Path) -> list[str]:
    return [a.get("name") for a in load_flow(root).get("agents", []) if a.get("name")]


def _zip_add(zf: zipfile.ZipFile, root: Path, name: str) -> None:
    src = root / name
    if not src.exists():
        return
    if src.is_file():
        zf.write(src, arcname=src.name)
    else:
        for path in src.rglob("*"):
            if path.is_file():
                zf.write(path, arcname=str(path.relative_to(root)))


def snapshot_create(root: Path) -> Path:
    root = Path(root)
    versions_dir = root / "versions"
    versions_dir.mkdir(parents=True, exist_ok=True)
    zip_path = versions_dir / f"snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in ["flow.yml", "templates", "validate_rules", "flow_fragments"]:
            _zip_add(zf, root, name)
    return zip_path


def snapshot_rollback(root: Path, snapshot_name: str) -> None:
    root = Path(root)
    snapshot_path = root / "versions" / snapshot_name
    if not snapshot_path.exists():
        raise FileNotFoundError(f"Snapshot not found: {snapshot_path}")
    backup = snapshot_create(root)
    with zipfile.ZipFile(snapshot_path, "r") as zf:
        for member in zf.namelist():
            if member.startswith(("templates/", "validate_rules/", "flow_fragments/", "flow.yml")):
                zf.extract(member, root)
    return backup


def export_template(root: Path, output_dir: Path | None = None) -> Path:
    root = Path(root)
    name = sanitize_name(load_flow(root).get("name", "workflow"))
    output_dir = Path(output_dir) if output_dir else root.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_dir / f"{name}_template.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in ["flow.yml", "templates", "validate_rules", "flow_fragments"]:
            _zip_add(zf, root, item)
    return zip_path


def import_template(zip_path: Path, target_dir: Path) -> Path:
    target_dir = Path(target_dir)
    ensure_workflow_dirs(target_dir)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(target_dir)
    return target_dir / "flow.yml"


def convert_external(source: Path, target_dir: Path) -> Path:
    source = Path(source)
    target_dir = Path(target_dir)
    ensure_workflow_dirs(target_dir)
    for sub in ["input_source", "output_delivery"]:
        src = source / sub
        if src.exists():
            shutil.copytree(src, target_dir / sub, dirs_exist_ok=True)
    flow_path = target_dir / "flow.yml"
    if not flow_path.exists():
        create_workflow(target_dir, name=target_dir.name)
    for name in ["flow.yml", "templates", "validate_rules", "flow_fragments"]:
        src = source / name
        if src.exists():
            (shutil.copy2 if src.is_file() else shutil.copytree)(src, target_dir / src.name, dirs_exist_ok=True)
    return flow_path


def set_mode(root: Path, advanced: bool) -> None:
    data = load_flow(root)
    data["mode"] = "advanced" if advanced else "beginner"
    data["log_level"] = 3 if advanced else 2
    save_flow(root, data)


def get_agent(root: Path, agent_name: str) -> dict[str, Any] | None:
    return next((a for a in load_flow(root).get("agents", []) if a.get("name") == agent_name), None)


def build_skill_markdown(root: Path) -> str | None:
    """Generate SKILL.md from flow.yml. Returns path to written file or None if no flow.yml."""
    from . import skill_builder
    return skill_builder.build_skill_markdown(root)
