"""Offline workflow executor (`/xujin`)."""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Any

from . import content_generator, gate, logger, validator, workflow
from .utils import resolve_path


class ExecutorError(Exception):
    pass


def _prompt_select_input_files(input_dir: Path) -> list[Path]:
    files = sorted([p for p in input_dir.iterdir() if p.is_file()])
    if not files:
        raise ExecutorError("No historical input files in input_source/")
    print("Select input files (comma-separated numbers):")
    for i, f in enumerate(files, 1):
        print(f"  {i}. {f.name}")
    choice = input("> ").strip()
    indices = [int(x.strip()) for x in choice.split(",") if x.strip().isdigit()]
    selected = [files[idx - 1] for idx in indices if 1 <= idx <= len(files)]
    if not selected:
        raise ExecutorError("No valid files selected")
    return selected


def _persist_inputs(root: Path, files: list[Path]) -> list[Path]:
    input_dir = root / "input_source"
    return [(shutil.copy2(src, input_dir / src.name) if src.resolve() != (input_dir / src.name).resolve() else src) for src in files]


def _collect_input_files(root: Path, inputs: list[str]) -> list[Path]:
    files: list[Path] = []
    for item in inputs:
        for part in item.split(","):
            part = part.strip()
            if not part:
                continue
            p = Path(part)
            if not p.is_absolute():
                p = root / p
            p = p.resolve()
            if not p.exists():
                raise ExecutorError(f"Input file not found: {p}")
            files.append(p)
    return files


def _determine_next_agents(agent: dict[str, Any], status: str) -> list[str]:
    targets = agent.get("branch_conditions", {}).get(status)
    return ([targets] if isinstance(targets, str) else list(targets)) if targets is not None else agent.get("next_agents", [])


def _execute_agent(
    root: Path,
    agent: dict[str, Any],
    input_files: list[Path],
    log: logger.WorkflowLogger,
    state: dict[str, Any],
    flow_data: dict[str, Any],
    verify_upstream: bool = True,
) -> tuple[str, list[Path]]:
    name = agent["name"]
    output_dir = root / "output_delivery" / name
    output_dir.mkdir(parents=True, exist_ok=True)

    for fp in input_files:
        if not validator.validate_file(fp, flow_data)["passed"]:
            log.log(name, "error", f"Input validation failed: {fp}")
            return "error", []

    if verify_upstream and input_files and not gate.verify_upstream_ids(root, input_files, state)["passed"]:
        log.log(name, "error", "Missing upstream anti-counterfeit IDs")
        return "error", []

    output_files: list[Path] = []
    for d in agent.get("deliverables", []) or [{}]:
        fname = d.get("filename") or f"{name}_output.txt"
        out_path = output_dir / fname
        out_path.write_text(content_generator.generate_content(agent, d, input_files, root), encoding="utf-8")
        output_files.append(out_path)

    for fp in output_files:
        if not validator.validate_file(fp, flow_data)["passed"]:
            log.log(name, "error", f"Output validation failed: {fp}")
            return "error", []

    registered = [gate.register_deliverable(root, name, fp, state) for fp in output_files]
    for fp in output_files:
        log.log_gate(name, fp, True, "ID issued", evidence_path=fp)

    status = agent.get("simulate_status", "completed_pass")
    gate.set_agent_state(root, name, status, state)
    log.log(name, status, f"Agent {name} finished", {"deliverables": registered})
    return status, output_files


def run(
    root: Path,
    start_agent: str,
    input_paths: list[str],
    interactive: bool = False,
) -> int:
    root = Path(root).resolve()
    flow_path = root / "flow.yml"
    if not flow_path.exists():
        print(f"Error: flow.yml not found in {root}\nPlease cd into the workflow root directory.", file=sys.stderr)
        return 1

    flow_data = workflow.load_flow(root)
    agents = flow_data.get("agents", [])
    agent_names = [a["name"] for a in agents]

    if start_agent != "root" and start_agent not in agent_names:
        print(f"Error: Agent '{start_agent}' not found. Valid agents: {agent_names}", file=sys.stderr)
        return 1
    if not agents:
        print("Error: No agents defined in flow.yml", file=sys.stderr)
        return 1

    start_idx = 0 if start_agent == "root" else agent_names.index(start_agent)

    if input_paths:
        files = _collect_input_files(root, input_paths)
    elif interactive:
        files = _prompt_select_input_files(root / "input_source")
    else:
        print("Error: No input files provided. Use --input or run interactively.", file=sys.stderr)
        return 1

    files = _persist_inputs(root, files)
    state = gate.clear_run_state(root)
    run_id = state["run_id"]
    log = logger.WorkflowLogger(root, level=flow_data.get("log_level", 2))

    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n  Workflow run started\n  Root: {root}\n  Run ID: {run_id}\n  Start agent: {start_agent}\n  Inputs: {[f.name for f in files]}\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    current_inputs = files
    executed: list[dict[str, Any]] = []
    failed = False

    for idx in range(start_idx, len(agents)):
        agent = agents[idx]
        status, outputs = _execute_agent(root, agent, current_inputs, log, state, flow_data, verify_upstream=idx != start_idx)
        executed.append({"agent": agent["name"], "status": status, "outputs": outputs})
        if status == "error":
            failed = True
            break
        current_inputs = outputs

    id_pool = state.get("id_pool", {})
    path_to_id = {v: k for k, v in id_pool.items()}
    deliverables = [
        {"agent": item["agent"], "name": out.name, "path": str(out), "id": path_to_id.get(str(out.relative_to(root)))}
        for item in executed for out in item["outputs"]
    ]

    log.summary(run_id, deliverables)

    print(f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n  Run summary ({'FAILED' if failed else 'SUCCESS'})\n  Run ID: {run_id}")
    for item in executed:
        print(f"  [{item['status']}] {item['agent']}")
    print("\n  Deliverables:")
    for d in deliverables:
        print(f"    [{d['agent']}] {d['name']}\n      Path: {d['path']}\n      ID:   {d['id']}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    gate.save_run_state(root, state)
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if "-help" in argv or "--help" in argv:
        print("""
=== Offline Workflow Executor Help ===
1. /xujin --start root --input file1.json,report.pdf
   Run the full workflow from the first agent with multiple inputs.
2. /xujin --start AgentName --input xxx.file
   Resume / run partially from the specified agent.
3. /xujin
   Interactive mode: select historical files from input_source/.
4. /xujin -help
   Show this help.

Notes:
- Inputs, deliverables, logs, and temporary state are persisted locally.
- No automatic cleanup. Manage disk space manually.
- Cross-agent transfer requires valid anti-counterfeit IDs from the current run.
""")
        return 0

    parser = argparse.ArgumentParser(prog="xujin", description="Offline workflow executor", add_help=False)
    parser.add_argument("--start", default="root", help="Start agent name (default: root)")
    parser.add_argument("--input", dest="input_files", help="Comma-separated input file paths")
    args = parser.parse_args(argv)

    inputs = [args.input_files] if args.input_files else []
    return run(Path.cwd(), args.start, inputs, interactive=not inputs)


if __name__ == "__main__":
    sys.exit(main())
