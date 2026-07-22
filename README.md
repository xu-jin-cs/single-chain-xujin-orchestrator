# single-chain-xujin-orchestrator

> Author: xu-jin-cs
> Source Repository: https://github.com/xu-jin-cs/single-chain-xujin-orchestrator

## Project Introduction

All-in-one multi-agent workflow tool.
Generate single-chain multi-agent workflow configuration from natural language prompts.
Built-in lightweight self-developed scheduling engine, offline operation supported.
Engine provides multi-layer deliverable gate verification, adopts **retry / process-fail binary exception strategy, no freeze lock mechanism**.

一体化多 Agent 工作流工具。
支持通过自然语言提示词生成单链多 Agent 结构化工作流配置；内置轻量化自研调度引擎，可离线独立运行。
引擎搭载多层交付物门禁校验，异常处理仅支持「节点重试」或「流程终止」，无流程冻结锁定机制。

## Architecture History

V4.0 Architecture Origin: July 2026
Targeted common pain points of multi-agent collaboration: arbitrary workflow jump, Agent tampering with running state, crude freeze mechanism for all exceptions.
Design adjustments are anchored in the following principles:

1. **Single-chain topology**: Workflows are strictly single-chain directed graphs. Each Agent node has at most one set of next agents, eliminating arbitrary jumps and cyclic tampering.
2. **State immutability**: The running engine state is isolated in `state_store/` and is append-only during execution. Running state cannot be modified by any Agent.
3. **Binary exception strategy**: When a node fails gate verification, the engine only supports retrying the current node or terminating the entire flow. There is no pause/resume/freeze mechanism.
4. **Deliverable gating**: Each node output must pass three layers of verification — basic existence, content lightweight check, and optional custom script hook — before advancing to the next node.
5. **Offline-first**: Once a workflow is generated, all configuration, templates, validation rules, and the executor are self-contained in the workflow directory. Deleting the source repository does not affect offline execution.

## Core Features

- **Natural language to workflow**: Paste structured Agent descriptions to auto-generate or replace node configurations, including identity, skills, rules, deliverables, and downstream links.
- **Web UI node editor**: Flask-based local Web UI at `http://127.0.0.1:8080/`. Supports create / edit / delete workflow nodes and visualize the flow chain.
- **Smart node replacement**: When editing an existing node, paste an Agent description to automatically replace the current node's data without affecting other nodes.
- **Single-chain scheduling engine**: Lightweight engine with deterministic execution order, gate-based verification, and retry/terminate-only error handling.
- **Multi-layer deliverable gate verification**:
  - Gate A: Basic validation (file existence, extension whitelist/blacklist, size limit)
  - Gate B: Content lightweight validation (anti-tamper hash, template fingerprint)
  - Gate C: Custom script hook validation
- **Offline executor**: After workflow creation, run entirely offline via the `/xujin` shell function or `python -m xujin_workflow.executor`.
- **Snapshot / rollback / export / import**: Version snapshots, template exports, and external workflow conversion.
- **Local-only security**: HTTP binds to `127.0.0.1`, no cloud API, no telemetry, no remote calls.

## Quick Start

### 1. Install dependencies

```bash
cd single-chain-xujin-orchestrator
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Start the Web UI

```bash
./start.sh
```

Open http://127.0.0.1:8080/ in your browser.

### 3. Create a workflow and add nodes

- Click **新建工作流** and enter a workflow name.
- Click **新建节点** or use **智能批量解析** to paste Agent descriptions.
- The drawer on the top right provides the fixed prompt template format.

### 4. Edit / replace a node

- In the node list, click **编辑** on the target node.
- In the editor panel, use the **智能分析替换当前节点** section.
- Paste the Agent description and click **解析并替换当前节点**.
- Only the current node is replaced; other nodes remain unchanged.

### 5. Finish and run offline

- Click **工作流设置完成** to name the workflow.
- The workflow directory is created under `~/.claude/skills/<workflow-name>/`.
- Run offline:

```bash
cd ~/.claude/skills/<workflow-name>
/xujin --start root --input data.json
```

Or use the project executor directly:

```bash
./xujin --start root --input data.json
```

## Directory Structure

```
single-chain-xujin-orchestrator/
├── start.sh                  # macOS / Linux one-click launcher
├── start.common              # Windows one-click launcher
├── xujin                     # Offline executor wrapper script
├── global_config.json        # MCP editing phase global config
├── requirements.txt          # Python dependencies
├── pyproject.toml            # Package config and console scripts
├── README.md                 # This file
├── src/xujin_workflow/       # Core source code
│   ├── webui.py              # Flask Web UI (HTTP 127.0.0.1:8080)
│   ├── engine.py             # Scheduling engine
│   ├── engine_state.py       # Engine state persistence
│   ├── executor.py           # Offline executor CLI
│   ├── workflow.py           # Workflow data model and directory ops
│   ├── validator.py          # Deliverable three-layer validation
│   ├── gate.py               # Gate hash anti-tamper ID
│   ├── skill_builder.py      # SKILL.md generator from flow.yml
│   ├── content_generator.py  # Node output content generation
│   ├── logger.py             # Layered logging
│   ├── utils.py              # Common utilities
│   ├── static/               # Static assets (background image)
│   └── templates/            # Jinja2 / HTML templates
│       ├── index.html        # Main Web UI
│       ├── skill_template_full.j2
│       └── skill_template_inline.j2
├── docs/                     # Requirement docs and usage guides
│   ├── 需求说明书.md
│   ├── 开放使用文档.md
│   └── 存量工作流填充说明.md
└── logs/                     # Runtime logs
```

A generated workflow directory contains:

```
<workflow-name>/
├── flow.yml                  # Workflow definition
├── templates/                # Output templates
├── validate_rules/           # Custom validation scripts
├── flow_fragments/           # Reusable fragments
├── input_source/             # Input files
├── output_delivery/          # Generated deliverables
├── state_store/              # Engine runtime state
├── versions/                 # Version snapshots
└── logs/                     # Execution logs
```

## License and Constraints

This is an internal project. Use is governed by the requirements and usage agreements documented in `docs/需求说明书.md` and `docs/开放使用文档.md`.

Key constraints:

- **Local use only**: Web UI binds to `127.0.0.1` and does not expose services externally.
- **No cloud dependency**: After workflow generation, offline execution does not rely on the source repository or `global_config.json`.
- **No freeze mechanism**: The engine intentionally does not support pause/resume/freeze. Failed nodes can only be retried or cause flow termination.
- **State immutability**: Running engine state must not be modified by Agents; only the engine may append state transitions.
- **Binary exception strategy**: `retry` or `process-fail` are the only exception handling paths.

For contribution, extension, or redistribution, refer to the project governance documents and contact the author.
