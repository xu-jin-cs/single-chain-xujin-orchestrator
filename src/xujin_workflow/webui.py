"""Web UI for editing Xujin workflow agents."""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, Response, render_template

from . import engine, engine_state, workflow
from . import skill_builder


app = Flask(__name__)
WORKFLOWS_PARENT: Path | None = None
CURRENT_WORKFLOW: Path | None = None


def _root() -> Path:
    if CURRENT_WORKFLOW is None:
        raise RuntimeError("未选择工作流")
    return CURRENT_WORKFLOW


def _zshrc_path() -> Path:
    return Path.home() / ".zshrc"


def _read_zshrc() -> tuple[list[str], str]:
    path = _zshrc_path()
    return (path.read_text(encoding="utf-8").splitlines(keepends=True), "") if path.exists() else ([], "")


def _write_zshrc(lines: list[str]) -> None:
    _zshrc_path().write_text("".join(lines), encoding="utf-8")


def _remove_zshrc_function(name: str) -> None:
    lines, _ = _read_zshrc()
    marker = f"# Type /{name} to run"
    start = next((i for i, line in enumerate(lines) if line.startswith(marker)), None)
    if start is None:
        return
    end = next((i for i in range(start, len(lines)) if lines[i].rstrip() == "}"), None)
    if end is None:
        return
    _write_zshrc(lines[:start] + lines[end + 1:])


def _update_zshrc_function(name: str, root: Path, old_name: str | None = None) -> None:
    """Add or rename the offline executor function in ~/.zshrc."""
    lines, _ = _read_zshrc()
    if old_name:
        _remove_zshrc_function(old_name)
        lines, _ = _read_zshrc()
    func_marker = f"function /{name}()"
    if any(line.startswith(func_marker) for line in lines):
        return
    project_root = Path(__file__).resolve().parents[2]
    xujin_bin = project_root / "xujin"
    block = (
        f"\n# Type /{name} to run the {name} workflow offline executor.\n"
        f"function /{name}() {{\n"
        f"    cd {root} && {xujin_bin} \"$@\"\n"
        f"}}\n"
    )
    lines.append(block)
    _write_zshrc(lines)


def _write_skill_md(root: Path) -> str | None:
    """Generate or refresh SKILL.md from flow.yml."""
    return skill_builder.build_skill_markdown(root)


def _list_workflows(parent: Path) -> list[dict[str, Any]]:
    if not parent.exists():
        return []
    items = [
        {
            "dir": child.name,
            "name": (data.get("name") or child.name),
            "mode": (data.get("mode") or "beginner"),
            "path": str(child),
            "mtime": child.stat().st_mtime,
        }
        for child in parent.iterdir()
        if child.is_dir() and (child / "flow.yml").exists()
        for data in [workflow.load_flow(child)]
    ]
    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items


@app.route("/")
def index() -> str:
    return render_template("index.html")


@app.route("/api/workflows", methods=["GET"])
def list_workflows() -> Response:
    try:
        return jsonify(_list_workflows(WORKFLOWS_PARENT)) if WORKFLOWS_PARENT else (jsonify({"error": "工作流父目录未设置"}), 500)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/workflow/select", methods=["POST"])
def select_workflow() -> Response:
    global CURRENT_WORKFLOW
    try:
        if WORKFLOWS_PARENT is None:
            return jsonify({"error": "工作流父目录未设置"}), 500
        data = request.get_json(force=True) or {}
        dir_name = (data.get("dir") or "").strip()
        if not dir_name:
            return jsonify({"error": "未指定工作流目录"}), 400
        target = WORKFLOWS_PARENT / dir_name
        if not target.exists() or not (target / "flow.yml").exists():
            return jsonify({"error": "工作流不存在"}), 404
        CURRENT_WORKFLOW = target
        return jsonify({"ok": True, "path": str(target)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/workflow", methods=["POST"])
def create_workflow_endpoint() -> Response:
    global CURRENT_WORKFLOW
    try:
        if WORKFLOWS_PARENT is None:
            return jsonify({"error": "工作流父目录未设置"}), 500
        data = request.get_json(force=True) or {}
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "工作流名称不能为空"}), 400
        dir_name = workflow.sanitize_name(name)
        root = WORKFLOWS_PARENT / dir_name
        if root.exists():
            return jsonify({"error": f"工作流目录 '{dir_name}' 已存在"}), 409
        duplicate = _find_duplicate_workflow(root, name)
        if duplicate:
            return jsonify({"error": f"工作流名称 '{name}' 已被 '{duplicate.name}' 使用，请更换名称"}), 409
        root.mkdir(parents=True, exist_ok=True)
        workflow.create_workflow(root, name)
        _update_zshrc_function(dir_name, root)
        _write_skill_md(root)
        CURRENT_WORKFLOW = root
        return jsonify({"ok": True, "created": str(root), "name": name})
    except Exception as e:
        return jsonify({"error": f"创建失败: {e}"}), 500


@app.route("/api/flow", methods=["GET"])
def get_flow() -> Response:
    try:
        return jsonify(workflow.load_flow(_root()))
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/flow", methods=["POST"])
def save_flow() -> Response:
    global CURRENT_WORKFLOW
    try:
        data = request.get_json(force=True)
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "工作流名称不能为空"}), 400
        root = _root()
        duplicate = _find_duplicate_workflow(root, name)
        if duplicate:
            return jsonify({"error": f"工作流名称 '{name}' 已被 '{duplicate.name}' 使用，请更换名称"}), 409
        old_name = root.name
        sanitized = workflow.sanitize_name(name)
        if name != "未命名" and sanitized and sanitized != old_name:
            new_root = root.parent / sanitized
            if new_root.exists():
                return jsonify({"error": f"工作流目录 '{sanitized}' 已存在，请更换名称"}), 409
            shutil.move(root, new_root)
            CURRENT_WORKFLOW = new_root
            root = new_root
            _update_zshrc_function(sanitized, root, old_name=old_name)
        workflow.save_flow(root, _normalize_flow_agents(data))
        _write_skill_md(root)
        return jsonify({"ok": True, "root": str(root), "name": name})
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": f"保存失败: {e}"}), 500


def _find_duplicate_workflow(root: Path, name: str) -> Path | None:
    parent = root.parent
    return next(
        (
            sibling for sibling in (parent.iterdir() if parent.exists() else [])
            if sibling != root and sibling.is_dir() and (sibling / "flow.yml").exists()
            and (workflow.load_flow(sibling).get("name") or "").strip() == name
        ),
        None,
    )


@app.route("/api/workflow", methods=["DELETE"])
def delete_workflow() -> Response:
    global CURRENT_WORKFLOW
    try:
        root = _root()
        if not root.exists():
            return jsonify({"error": "工作流目录不存在"}), 404
        if not (root / "flow.yml").exists():
            return jsonify({"error": "该目录不是有效工作流，缺少 flow.yml"}), 400
        shutil.rmtree(root)
        _remove_zshrc_function(root.name)
        CURRENT_WORKFLOW = None
        return jsonify({"ok": True, "deleted": str(root)})
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": f"删除失败: {e}"}), 500


@app.route("/api/agents", methods=["GET"])
def list_agents() -> Response:
    try:
        return jsonify(workflow.list_agents(_root()))
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/agents", methods=["POST"])
def add_agent() -> Response:
    try:
        payload = request.get_json(force=True)
        workflow.add_agent(
            _root(),
            agent_name=payload["name"],
            identity=payload.get("identity", ""),
            skills=_lines(payload.get("skills", "")),
            rules=_lines(payload.get("rules", "")),
            deliverables=payload.get("deliverables", []),
            next_agents=_string_list(payload.get("next_agents", "")),
            branch_conditions=payload.get("branch_conditions", {}),
            max_retry_count=payload.get("max_retry_count", 3),
        )
        return jsonify({"ok": True})
    except KeyError as e:
        return jsonify({"error": f"缺少必填字段: {e}"}), 400
    except ValueError as e:
        return jsonify({"error": str(e)}), 409
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": f"保存失败: {e}"}), 500


@app.route("/api/agents/<name>", methods=["GET"])
def get_agent(name: str) -> Response:
    try:
        agent = workflow.get_agent(_root(), name)
        return (jsonify(agent), 200) if agent else (jsonify({"error": "节点不存在"}), 404)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": f"查询失败: {e}"}), 500


@app.route("/api/agents/<name>", methods=["PUT"])
def update_agent(name: str) -> Response:
    try:
        payload = request.get_json(force=True)
        workflow.update_agent(
            _root(),
            name,
            identity=payload.get("identity", ""),
            skills=_lines(payload.get("skills", "")),
            rules=_lines(payload.get("rules", "")),
            deliverables=payload.get("deliverables", []),
            next_agents=_string_list(payload.get("next_agents", "")),
            branch_conditions=payload.get("branch_conditions", {}),
            max_retry_count=payload.get("max_retry_count", 3),
        )
        return jsonify({"ok": True})
    except (ValueError, RuntimeError) as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": f"更新失败: {e}"}), 500


@app.route("/api/agents/<name>", methods=["DELETE"])
def delete_agent(name: str) -> Response:
    try:
        workflow.delete_agent(_root(), name)
        return jsonify({"ok": True})
    except (ValueError, RuntimeError) as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": f"删除失败: {e}"}), 500


def _normalize_flow_agents(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize all agent deliverables in flow data before saving."""
    for a in data.get("agents", []):
        a["deliverables"] = workflow._normalize_deliverables(a.get("deliverables", []))
    return data


def _lines(text: str) -> list[str]:
    return ([str(line).strip() for line in text if str(line).strip()] if isinstance(text, list) else [line.strip() for line in text.splitlines() if line.strip()])


def _string_list(value: Any) -> list[str]:
    return [str(item).strip() for item in value if str(item).strip()] if isinstance(value, list) else _lines(value)


# ── Engine API ──────────────────────────────────────────────

@app.route("/api/engine/start", methods=["POST"])
def engine_start() -> Response:
    try:
        result = engine.start_engine(_root())
        return jsonify(result)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": f"引擎启动失败: {e}"}), 500


@app.route("/api/engine/status", methods=["GET"])
def engine_status() -> Response:
    try:
        return jsonify(engine.get_engine_status(_root()))
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/engine/run", methods=["POST"])
def engine_run() -> Response:
    try:
        result = engine.run_current_node(_root())
        return jsonify(result)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 404
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": f"节点执行失败: {e}"}), 500


@app.route("/api/engine/retry", methods=["POST"])
def engine_retry() -> Response:
    try:
        result = engine.retry_current_node(_root())
        return jsonify(result)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 404
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": f"重试失败: {e}"}), 500


def main() -> int:
    parser = argparse.ArgumentParser(description="Xujin Workflow Web UI")
    parser.add_argument("--root", required=True, help="Workflow root directory or parent directory")
    parser.add_argument("--port", type=int, default=8080, help="Web UI port")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    args = parser.parse_args()

    global WORKFLOWS_PARENT, CURRENT_WORKFLOW
    root_arg = Path(args.root).expanduser().resolve()
    if (root_arg / "flow.yml").exists():
        WORKFLOWS_PARENT = root_arg.parent
        CURRENT_WORKFLOW = root_arg
    else:
        WORKFLOWS_PARENT = root_arg
        CURRENT_WORKFLOW = None

    if not WORKFLOWS_PARENT.exists():
        WORKFLOWS_PARENT.mkdir(parents=True, exist_ok=True)

    flow_path = CURRENT_WORKFLOW / "flow.yml" if CURRENT_WORKFLOW else None
    if flow_path and not flow_path.exists():
        print(f"Error: flow.yml not found in {CURRENT_WORKFLOW}", file=sys.stderr)
        return 1

    target = CURRENT_WORKFLOW or WORKFLOWS_PARENT
    print(f"Starting web UI for {target}")
    print(f"Open http://{args.host}:{args.port}/")
    app.run(host=args.host, port=args.port, debug=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
