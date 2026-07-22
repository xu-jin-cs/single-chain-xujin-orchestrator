"""Auto-generate Claude Code SKILL.md from flow.yml.

Source of truth: <workflow_root>/flow.yml
Generated artifact: <workflow_root>/SKILL.md (read-only, overwritten on save)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, Template


_TEMPLATE_PATH = Path(__file__).resolve().parent / "templates"


def _get_template(engine_tier: int = 3) -> Template:
    """Load external Jinja2 template by engine_tier, else fall back to inline.

    engine_tier:
      3 -> full template with Fetch health probe and 3-level engine dispatch
      1 -> inline template, fixed session simulation mode
    """
    if engine_tier == 1:
        external = _TEMPLATE_PATH / "skill_template_inline.j2"
        if external.exists():
            env = Environment(loader=FileSystemLoader(str(_TEMPLATE_PATH)), autoescape=False)
            return env.get_template("skill_template_inline.j2")
        return Template(_INLINE_TEMPLATE_INLINE)

    external = _TEMPLATE_PATH / "skill_template_full.j2"
    if external.exists():
        env = Environment(loader=FileSystemLoader(str(_TEMPLATE_PATH)), autoescape=False)
        return env.get_template("skill_template_full.j2")
    return Template(_INLINE_TEMPLATE_FULL)


def derive_exec_chain(agents: list[dict[str, Any]]) -> list[str]:
    """Derive a linear execution chain from agents[*].next_agents.

    Falls back to agents order when next_agents does not form a single chain.
    """
    if not agents:
        return []
    node_map = {a["name"]: a for a in agents if a.get("name")}
    current = agents[0]["name"]
    chain: list[str] = []
    visited: set[str] = set()

    while current and current not in visited:
        visited.add(current)
        chain.append(current)
        node = node_map.get(current)
        if not node:
            break
        next_agents = node.get("next_agents") or []
        current = next((n for n in next_agents if n not in visited), None)
        if not current and next_agents:
            current = next_agents[0]

    # Append any orphaned agents that were not reached
    for a in agents:
        name = a.get("name")
        if name and name not in visited:
            chain.append(name)
    return chain


def _default_input_schema(name: str) -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["input"],
        "properties": {
            "input": {
                "type": "string",
                "description": f"输入给 {name} 工作流的首节点上下文或文件路径",
            }
        },
    }


def build_skill_markdown(root: Path, flow_data: dict[str, Any] | None = None) -> str | None:
    """Generate SKILL.md from flow.yml. Returns path to written file or None if no flow.yml."""
    root = Path(root)
    flow_path = root / "flow.yml"
    if not flow_path.exists():
        return None

    if flow_data is None:
        flow_data = yaml.safe_load(flow_path.read_text(encoding="utf-8")) or {}

    skill_id = (flow_data.get("name") or root.name).strip()
    if not skill_id:
        return None

    engine_tier = int(flow_data.get("engine_tier") or 3)

    meta = {
        "skill_id": skill_id,
        "description": flow_data.get("description") or f"{skill_id} 本地离线工作流",
        "aliases": flow_data.get("aliases") or [f"/{skill_id}"],
        "input_schema": flow_data.get("input_schema") or _default_input_schema(skill_id),
        "rules": flow_data.get("rules") or [],
        "exec_chain": derive_exec_chain(flow_data.get("agents") or []),
        "offline_command": flow_data.get("offline_command") or "/xujin",
        "root": str(root),
    }

    template = _get_template(engine_tier=engine_tier)
    content = template.render(meta=meta)
    skill_path = root / "SKILL.md"
    skill_path.write_text(content, encoding="utf-8")
    return str(skill_path)


def scan_and_rebuild_all(parent: Path) -> list[str]:
    """Rebuild SKILL.md for every workflow directory under parent."""
    parent = Path(parent)
    logs: list[str] = []
    if not parent.exists():
        return logs
    for child in parent.iterdir():
        if not child.is_dir() or not (child / "flow.yml").exists():
            continue
        try:
            path = build_skill_markdown(child)
            logs.append(f"[OK] {child.name} -> {path}" if path else f"[SKIP] {child.name}")
        except Exception as err:
            logs.append(f"[FAIL] {child.name}: {err}")
    return logs


_INLINE_TEMPLATE_FULL = """<!-- AUTO-GENERATED from {{ meta.skill_id }}/flow.yml. DO NOT EDIT. -->
---
name: {{ meta.skill_id }}
description: {{ meta.description }}
aliases: {{ meta.aliases | tojson }}
disallow-tools: ["Bash"]
allowed-tools: ["Read","Write","Fetch"]
---

# {{ meta.skill_id }}
## 入参
{%- set schema = meta.input_schema %}
{%- for param_name, param_info in schema.properties.items() %}
- `{{ param_name }}`: {{ param_info.type }}，{{ param_info.description }}
{%- endfor %}

## 静态执行链路（flow.yml原始拓扑顺序，仅供兜底模式参考）
{{ meta.exec_chain | join(' → ') }}

## 业务约束规则
{%- for rule in meta.rules %}
{{ loop.index }}. {{ rule }}
{%- endfor %}

## 数据生成强制约束
1. 首节点必须接收用户传入参数，基于参数生成真实实例数据；
2. **所有节点禁止仅输出空白 JSON Schema，必须产出填充完成的业务实体数据；**
3. 后续节点严格读取约定路径下前序节点输出文件作为上下文，禁止跨节点读取无关文件；
4. 交付物文件名与路径必须和 flow.yml 中定义的 deliverables 完全一致。

## 执行分流逻辑
1. 使用Read工具读取 `{{ meta.skill_id }}/flow.yml` 获取完整工作流拓扑、节点定义与交付物定义。
2. 通过Fetch工具访问预设健康接口 http://127.0.0.1:8001/api/health，请求超时限制3秒；
   - 规则：仅执行一次探测，禁止循环重试；禁止模型修改接口地址、自定义探测目标。
3. 分流策略：
   ✅ 探测正常返回：优先启用LangGraph+Harness外部链路执行；节点调度、条件分支、跨层级回退、迭代循环全部由外部引擎负责；技能仅转发入参，不干预流程走向。
   ❌ 超时/连接失败/异常返回：切换至自研内置引擎执行；完整流程调度由内置引擎管控。
   ⚠️ 仅当外部引擎、自研内置引擎均不可用时，自动降级至本地会话推演模式。

## 会话推演模式规范（仅终极兜底分支生效）
在当前会话内按照flow.yml定义顺序串行执行全部Agent；依靠Read读取上游交付文件、Write持久化节点输出；
1. 默认按链条顺序向后推进；
2. 校验失败禁止继续向后执行；支持跨层级回退至任意前置节点重新迭代；
3. 所有节点严格遵守上方【数据生成强制约束】。

## 硬性全局约束
1. 全程禁止调用Bash工具，禁止搜寻、启动外部可执行程序；
2. 禁止启用MCP协议，所有交互依托当前技能体系；
3. 不允许自主新增探测地址、不允许构造任意未知外部调用指令；
4. 只要使用外置引擎 / 自研内置引擎，模型禁止私自篡改引擎下发的执行顺序与节点跳转逻辑。
"""

_INLINE_TEMPLATE_INLINE = """<!-- AUTO-GENERATED from {{ meta.skill_id }}/flow.yml. DO NOT EDIT. -->
---
name: {{ meta.skill_id }}
description: {{ meta.description }}
aliases: {{ meta.aliases | tojson }}
disallow-tools: ["Bash"]
allowed-tools: ["Read", "Write"]
---

# {{ meta.skill_id }}
## 入参
{%- set schema = meta.input_schema %}
{%- for param_name, param_info in schema.properties.items() %}
- `{{ param_name }}`: {{ param_info.type }}，{{ param_info.description }}
{%- endfor %}

## 静态执行链路（flow.yml原始拓扑顺序）
{{ meta.exec_chain | join(' → ') }}

## 业务约束规则
{%- for rule in meta.rules %}
{{ loop.index }}. {{ rule }}
{%- endfor %}

## 数据生成强制约束
1. 首节点必须接收用户传入参数，基于参数生成真实实例数据；
2. **所有节点禁止仅输出空白 JSON Schema，必须产出填充完成的业务实体数据；**
3. 后续节点严格读取约定路径下前序节点输出文件作为上下文，禁止跨节点读取无关文件；
4. 交付物文件名与路径必须和 flow.yml 中定义的 deliverables 完全一致。

## 执行方式（固定会话推演模式）
1. 使用 `Read` 工具读取 `{{ meta.skill_id }}/flow.yml` 获取完整工作流拓扑、节点定义与交付物定义；
2. 将用户输入参数作为首节点上下文注入；
3. **在当前会话内按照 flow.yml 定义顺序串行执行全部 Agent**；依靠 Read 读取上游交付文件、Write 持久化节点输出；
4. 默认按链条顺序向后推进；校验失败禁止继续向后执行，支持跨层级回退至任意前置节点重新迭代；
5. 全部节点执行完毕后输出最终成品数据。

## 硬性全局约束
1. 全程禁止调用 Bash 工具，禁止搜寻、启动外部可执行程序；
2. 禁止启用 MCP 协议，所有交互依托当前技能体系；
3. 不允许自主新增探测地址、不允许构造任意未知外部调用指令。
"""
