"""Execution engine — dual-gate validation + single-chain scheduler.

Gate A (pre-execution): upstream nodes finished + deliverables registered with valid hash.
Gate B (post-execution): output matches schema, non-empty, format correct, hash registered.

No agent has r/w access to state — engine exclusively maintains it.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import content_generator, engine_state, workflow

# jsonschema is optional — only used if deliverable schema is valid JSON Schema
try:
    from jsonschema import validate as jsonschema_validate, ValidationError as JsonSchemaError
    _HAS_JSONSCHEMA = True
except ImportError:
    _HAS_JSONSCHEMA = False


def _upstream_agents(agent_name: str, agents: list[dict[str, Any]]) -> list[str]:
    """Return names of all agents that have agent_name in their next_agents."""
    return [a["name"] for a in agents if agent_name in (a.get("next_agents") or [])]


def _upstream_deliverables(upstream_names: list[str], agents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collect deliverable definitions from all upstream agents."""
    result: list[dict[str, Any]] = []
    for name in upstream_names:
        agent = next((a for a in agents if a["name"] == name), None)
        if agent:
            for d in agent.get("deliverables") or []:
                result.append({"agent_name": name, "filename": d.get("filename", ""), "template": d.get("template", "")})
    return result


def _parse_json_schema(template: str) -> dict | None:
    """Extract a valid JSON Schema dict from template text.

    Handles markdown code block prefixes like 'json\\n{...}'.
    """
    t = template.strip()
    # Direct parse
    try:
        v = json.loads(t)
        return v if isinstance(v, dict) and ("type" in v or "properties" in v or "$schema" in v) else None
    except (json.JSONDecodeError, TypeError):
        pass
    # Strip markdown code block language tag (e.g. "json\n{...}")
    for marker in ("json\n", "json\r\n", "yaml\n", "yml\n"):
        if t.startswith(marker):
            try:
                v = json.loads(t[len(marker):])
                return v if isinstance(v, dict) and ("type" in v or "properties" in v or "$schema" in v) else None
            except (json.JSONDecodeError, TypeError):
                pass
    # Try from first brace/bracket
    for start_char in ("{", "["):
        idx = t.find(start_char)
        if idx > 0:
            try:
                v = json.loads(t[idx:])
                return v if isinstance(v, dict) and ("type" in v or "properties" in v or "$schema" in v) else None
            except (json.JSONDecodeError, TypeError):
                pass
    return None


def _validate_schema(content: str, template: str) -> tuple[list[str], bool]:
    """Validate output content against schema template.

    Returns (errors, schema_was_applied).
    """
    errors: list[str] = []
    if not content.strip():
        return ["产出文件为空"], False

    schema = _parse_json_schema(template)
    if schema is None:
        return [], False  # Not a JSON Schema — skip validation, caller may log warning

    if _HAS_JSONSCHEMA:
        try:
            instance = json.loads(content)
            jsonschema_validate(instance=instance, schema=schema)
            return [], True
        except json.JSONDecodeError:
            errors.append("产出内容非合法JSON，无法按Schema校验")
        except JsonSchemaError as e:
            errors.append(f"Schema校验失败: {e.message}")
    else:
        try:
            instance = json.loads(content)
            for field in schema.get("required", []):
                if field not in instance:
                    errors.append(f"缺少必填字段: {field}")
        except json.JSONDecodeError:
            errors.append("产出内容非合法JSON，无法校验必填字段")
    return errors, True


def _find_agent_by_name(agents: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    return next((a for a in agents if a["name"] == name), None)


def _agent_index(agents: list[dict[str, Any]], name: str) -> int:
    for i, a in enumerate(agents):
        if a["name"] == name:
            return i
    return -1


def gate_a_check(root: Path, state: engine_state.FlowState, agent: dict[str, Any], agents: list[dict[str, Any]]) -> dict[str, Any]:
    """Gate A — pre-execution准入校验.

    Checks:
    1. All upstream nodes exist in finished_nodes
    2. All upstream deliverables exist in registry with valid hash
    """
    agent_name = agent["name"]
    upstream = _upstream_agents(agent_name, agents)
    if not upstream:
        # Root node — no upstream, pass
        return {"passed": True, "errors": [], "agent": agent_name}

    errors: list[str] = []
    # Check 1: upstream nodes finished
    for up_name in upstream:
        if up_name not in state.finished_nodes:
            errors.append(f"上游节点「{up_name}」未完成，当前无法执行「{agent_name}」")
    if errors:
        return {"passed": False, "errors": errors, "agent": agent_name}

    # Check 2: upstream deliverables in registry with valid hash
    up_deliverables = _upstream_deliverables(upstream, agents)
    for d in up_deliverables:
        fname = d["filename"]
        if not fname:
            errors.append(f"上游节点「{d['agent_name']}」的交付物定义缺少文件名")
            continue
        # Look for registered deliverable from this agent with this filename
        rel_path = f"output_delivery/{d['agent_name']}/{fname}"
        entry = next((r for r in state.deliverable_registry if r["path"] == rel_path), None)
        if not entry:
            errors.append(f"缺少上游交付物: {d['agent_name']}/{fname}（注册表中不存在）")
        else:
            # Verify file still exists and hash matches
            full_path = root / rel_path
            if not full_path.exists():
                errors.append(f"上游交付物文件不存在: {d['agent_name']}/{fname}")
            else:
                from .utils import sha256_file
                current_hash = sha256_file(full_path)
                if current_hash != entry["sha256"]:
                    errors.append(f"上游交付物哈希不匹配: {d['agent_name']}/{fname}（文件已被修改）")

    passed = len(errors) == 0
    log_entry = {
        "gate": "A",
        "agent": agent_name,
        "passed": passed,
        "errors": errors,
        "upstream_checked": upstream,
    }
    state.gate_logs.append(log_entry)
    engine_state.save_state(root, state)
    return {"passed": passed, "errors": errors, "agent": agent_name, "log": log_entry}


def gate_b_check(
    root: Path, state: engine_state.FlowState, agent: dict[str, Any], output_files: list[Path]
) -> dict[str, Any]:
    """Gate B — post-execution产出防伪校验.

    Checks:
    1. Output file matches configured schema (required fields present, non-empty)
    2. Output file format matches configured definition
    3. Register hash into registry, bound to current node
    """
    agent_name = agent["name"]
    deliverables = agent.get("deliverables") or []
    errors: list[str] = []

    if not deliverables:
        # No deliverables defined — check output files exist and are non-empty
        for fp in output_files:
            if not fp.exists() or fp.stat().st_size == 0:
                errors.append(f"产出文件为空或不存在: {fp.name}")
        passed = len(errors) == 0
        log_entry = {"gate": "B", "agent": agent_name, "passed": passed, "errors": errors, "jsonschema_available": _HAS_JSONSCHEMA}
        state.gate_logs.append(log_entry)
        engine_state.save_state(root, state)
        return {"passed": passed, "errors": errors, "agent": agent_name, "log": log_entry}

    # Map output files to deliverables by filename
    for d in deliverables:
        fname = d.get("filename", "")
        template = d.get("template", "")
        if not fname:
            errors.append("交付物定义缺少文件名")
            continue
        matching = [fp for fp in output_files if fp.name == fname]
        if not matching:
            errors.append(f"未找到产出文件: {fname}")
            continue
        fp = matching[0]
        if not fp.exists() or fp.stat().st_size == 0:
            errors.append(f"产出文件为空: {fname}")
            continue
        content = fp.read_text(encoding="utf-8")
        has_schema_errors = False
        if template:
            schema_errors, schema_applied = _validate_schema(content, template)
            if not schema_applied and template.strip():
                pass  # Template exists but isn't a JSON Schema — schema-less deliverable
            if schema_errors:
                has_schema_errors = True
                errors.extend(schema_errors)
        if not has_schema_errors:
            engine_state.register_deliverable(root, state, agent_name, fp)

    passed = len(errors) == 0
    log_entry = {"gate": "B", "agent": agent_name, "passed": passed, "errors": errors, "jsonschema_available": _HAS_JSONSCHEMA}
    state.gate_logs.append(log_entry)
    engine_state.save_state(root, state)
    return {"passed": passed, "errors": errors, "agent": agent_name, "log": log_entry}


def execute_agent(root: Path, state: engine_state.FlowState, agent: dict[str, Any], flow_data: dict[str, Any], input_files: list[Path] | None = None) -> dict[str, Any]:
    """Execute a single agent — produce output files from deliverables config."""
    name = agent["name"]
    output_dir = root / "output_delivery" / name
    output_dir.mkdir(parents=True, exist_ok=True)
    files = input_files if input_files is not None else [p for p in (root / "input_source").iterdir() if p.is_file()] if (root / "input_source").exists() else []
    output_files: list[Path] = []
    for d in agent.get("deliverables") or []:
        fname = d.get("filename") or f"{name}_output.txt"
        out_path = output_dir / fname
        out_path.write_text(content_generator.generate_content(agent, d, files, root), encoding="utf-8")
        output_files.append(out_path)
    return {"agent": name, "status": "completed", "outputs": output_files}


def start_engine(root: Path) -> dict[str, Any]:
    """Initialize engine and start from the first agent.

    Returns the result of processing the first node (up to Gate A).
    """
    flow_data = workflow.load_flow(root)
    agents = flow_data.get("agents", [])
    if not agents:
        return {"error": "工作流中没有定义任何Agent节点"}

    state = engine_state.init_state(root, agents)
    first_agent = agents[0]
    state.current_node = first_agent["name"]
    state.max_retry = first_agent.get("max_retry_count", 3)
    state.retry_count = 0
    engine_state.save_state(root, state)

    # Run Gate A for first node (should pass since no upstream)
    gate_a_result = gate_a_check(root, state, first_agent, agents)
    if not gate_a_result["passed"]:
        return {
            "status": "blocked",
            "current_node": first_agent["name"],
            "gate": "A",
            "errors": gate_a_result["errors"],
            "state": state.to_dict(),
        }

    return {
        "status": "ready",
        "current_node": first_agent["name"],
        "message": f"引擎已启动，当前节点: {first_agent['name']}，等待执行",
        "state": state.to_dict(),
    }


def run_current_node(root: Path) -> dict[str, Any]:
    """Execute the current node: Gate A → Agent Execution → Gate B → advance/retry.

    Must be called after start_engine().
    """
    flow_data = workflow.load_flow(root)
    agents = flow_data.get("agents", [])
    state = engine_state.load_state(root)
    agent_name = state.current_node
    agent = _find_agent_by_name(agents, agent_name)
    if not agent:
        return {"error": f"当前节点「{agent_name}」在flow.yml中不存在"}

    # Step 1: Gate A
    gate_a = gate_a_check(root, state, agent, agents)
    if not gate_a["passed"]:
        return {
            "status": "blocked",
            "current_node": agent_name,
            "gate": "A",
            "errors": gate_a["errors"],
            "state": state.to_dict(),
        }

    # Step 2: Execute agent (produces output files)
    exec_result = execute_agent(root, state, agent, flow_data)
    output_files = exec_result.get("outputs", [])

    # Step 3: Gate B
    gate_b = gate_b_check(root, state, agent, output_files)

    if gate_b["passed"]:
        # Mark node finished, advance to next
        state.finished_nodes.add(agent_name)
        state.retry_count = 0
        engine_state.save_state(root, state)

        next_agent = _determine_next(agent, agents, state)
        if next_agent:
            state.current_node = next_agent
            state.max_retry = (_find_agent_by_name(agents, next_agent) or {}).get("max_retry_count", 3)
            state.retry_count = 0
            engine_state.save_state(root, state)

            return {
                "status": "advanced",
                "current_node": next_agent,
                "finished_nodes": sorted(state.finished_nodes),
                "message": f"「{agent_name}」完成 → 进入「{next_agent}」",
                "deliverables": [d["path"] for d in state.deliverable_registry if d["node_id"] == agent_name],
                "state": state.to_dict(),
            }
        else:
            # No more nodes — workflow complete
            state.current_node = ""
            engine_state.save_state(root, state)
            return {
                "status": "completed",
                "finished_nodes": sorted(state.finished_nodes),
                "message": "工作流全部节点执行完成",
                "state": state.to_dict(),
            }
    else:
        # Gate B failed — handle retry
        state.retry_count += 1
        max_retry = state.max_retry
        engine_state.save_state(root, state)

        if state.retry_count < max_retry:
            return {
                "status": "retry",
                "current_node": agent_name,
                "retry_count": state.retry_count,
                "max_retry": max_retry,
                "gate": "B",
                "errors": gate_b["errors"],
                "message": f"门禁B校验失败（{state.retry_count}/{max_retry}），请修正后重新执行本节点",
                "state": state.to_dict(),
            }
        else:
            return {
                "status": "terminated",
                "current_node": agent_name,
                "retry_count": state.retry_count,
                "max_retry": max_retry,
                "gate": "B",
                "errors": gate_b["errors"],
                "message": f"门禁B校验达到最大重试次数（{state.retry_count}/{max_retry}），节点已终止，需人工修正后重启",
                "state": state.to_dict(),
            }


def retry_current_node(root: Path) -> dict[str, Any]:
    """Re-run Gate B for the current node after user fixes output.

    This does NOT re-execute Gate A — only re-checks deliverables.
    """
    flow_data = workflow.load_flow(root)
    agents = flow_data.get("agents", [])
    state = engine_state.load_state(root)
    agent_name = state.current_node
    agent = _find_agent_by_name(agents, agent_name)
    if not agent:
        return {"error": f"当前节点「{agent_name}」不存在"}

    if state.retry_count >= state.max_retry:
        return {
            "status": "terminated",
            "current_node": agent_name,
            "message": f"已达最大重试次数（{state.retry_count}/{state.max_retry}），无法继续重试，请重启节点",
            "state": state.to_dict(),
        }

    # Collect existing output files from disk (do NOT overwrite user fixes)
    output_dir = root / "output_delivery" / agent_name
    deliverables = agent.get("deliverables") or []
    output_files = [output_dir / d["filename"] for d in deliverables if d.get("filename") and (output_dir / d["filename"]).exists()]

    # Gate B again
    gate_b = gate_b_check(root, state, agent, output_files)

    if gate_b["passed"]:
        state.finished_nodes.add(agent_name)
        state.retry_count = 0
        engine_state.save_state(root, state)

        next_agent = _determine_next(agent, agents, state)
        if next_agent:
            state.current_node = next_agent
            state.max_retry = (_find_agent_by_name(agents, next_agent) or {}).get("max_retry_count", 3)
            engine_state.save_state(root, state)
            return {
                "status": "advanced",
                "current_node": next_agent,
                "finished_nodes": sorted(state.finished_nodes),
                "message": f"重试成功，「{agent_name}」完成 → 进入「{next_agent}」",
                "state": state.to_dict(),
            }
        return {
            "status": "completed",
            "finished_nodes": sorted(state.finished_nodes),
            "message": "工作流全部节点执行完成",
            "state": state.to_dict(),
        }
    else:
        state.retry_count += 1
        engine_state.save_state(root, state)
        if state.retry_count < state.max_retry:
            return {
                "status": "retry",
                "current_node": agent_name,
                "retry_count": state.retry_count,
                "max_retry": state.max_retry,
                "errors": gate_b["errors"],
                "message": f"门禁B再次校验失败（{state.retry_count}/{state.max_retry}）",
                "state": state.to_dict(),
            }
        return {
            "status": "terminated",
            "current_node": agent_name,
            "retry_count": state.retry_count,
            "max_retry": state.max_retry,
            "errors": gate_b["errors"],
            "message": "达到最大重试次数，节点终止",
            "state": state.to_dict(),
        }


def get_engine_status(root: Path) -> dict[str, Any]:
    """Get current engine state."""
    try:
        state = engine_state.load_state(root)
        return {"ok": True, "state": state.to_dict()}
    except FileNotFoundError:
        return {"ok": True, "state": None, "message": "引擎未启动"}


def _determine_next(agent: dict[str, Any], agents: list[dict[str, Any]], state: engine_state.FlowState) -> str | None:
    """Determine next agent based on branch_conditions (pre-configured flows only).

    Only supports pre-configured conditional loops — agents cannot decide jumps autonomously.
    """
    # Try branch_conditions first (pre-configured routing)
    branch = agent.get("branch_conditions", {})
    # Check each status-based branch condition
    for status_key in ("completed_pass", "completed_fail"):
        target = branch.get(status_key)
        if target and isinstance(target, str):
            target_agent = _find_agent_by_name(agents, target)
            if target_agent and target not in state.finished_nodes:
                return target

    # Fallback: next_agents in order
    next_names = agent.get("next_agents") or []
    for name in next_names:
        if name not in state.finished_nodes:
            return name
    # All next done — check if any branch condition returns to an earlier node (loop)
    for status_key in ("completed_pass", "completed_fail"):
        target = branch.get(status_key)
        if target and isinstance(target, str):
            return target

    # Strict linear: return the first unfinished agent in the ordered agents list
    for a in agents:
        if a["name"] not in state.finished_nodes:
            return a["name"]
    return None
