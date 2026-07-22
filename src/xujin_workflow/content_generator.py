"""Agent deliverable content generation for workflow execution.

Provides rule-based JSON generation keyed by agent name, using the user-provided
style parameter and upstream deliverables as context.
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

_ORGAN_CATALOGUE = [
    ("耳朵", "三角形", "头顶两侧"),
    ("眼睛", "圆形", "面部前方"),
    ("鼻子", "小巧三角形", "脸部中央"),
    ("胡须", "细长", "口鼻两侧"),
    ("尾巴", "修长", "臀部后端"),
    ("爪子", "肉垫型", "四肢末端"),
    ("毛发", "柔软被毛", "全身覆盖"),
    ("舌头", "细长带倒刺", "口腔内部"),
]


def _agent_index(name: str) -> int:
    for i, suffix in enumerate(["A", "B", "C", "D", "E"]):
        if name.endswith(f" {suffix}") or f" {suffix}" in name:
            return i
    return random.randint(0, len(_ORGAN_CATALOGUE) - 1)


def load_input_context(input_files: list[Path]) -> dict[str, Any]:
    context: dict[str, Any] = {"style": ""}
    for fp in input_files:
        if not fp.exists():
            continue
        text = fp.read_text(encoding="utf-8").strip()
        if fp.name == "input.txt":
            context["style"] = text
        else:
            try:
                context[fp.name] = json.loads(text)
            except (json.JSONDecodeError, TypeError):
                context[fp.name] = text
    return context


def generate_organ(style: str, index: int) -> dict[str, Any]:
    name, shape, position = _ORGAN_CATALOGUE[index % len(_ORGAN_CATALOGUE)]
    return {
        "organ_name": name,
        "base_size": f"{random.randint(3, 15)}cm",
        "position": position,
        "shape_desc": f"{style}风格的{name}，呈{shape}，带有该风格特有的纹理",
    }


def decorate_organ(base: dict[str, Any], style: str) -> dict[str, Any]:
    base["decorate_info"] = (
        f"{style}风格修饰：采用{random.choice(['柔和', '锐利', '蓬松', '光滑'])}质感，"
        f"{random.choice(['暖色调', '冷色调', '自然色', '金属色'])}涂装"
    )
    return base


def generate_content(agent: dict[str, Any], deliverable: dict[str, Any], input_files: list[Path], root: Path) -> str:
    name = agent.get("name", "")
    context = load_input_context(input_files)
    style = context.get("style") or "随机"

    if "猫咪器官生成器" in name:
        return json.dumps(generate_organ(style, _agent_index(name)), ensure_ascii=False, indent=2)

    if "完整猫生成检查器" in name:
        return json.dumps({"status": "complete", "total_organs": 5}, ensure_ascii=False, indent=2)

    if "器官修饰师" in name:
        idx = _agent_index(name)
        upstream_path = root / "output_delivery" / f"猫咪器官生成器 {chr(ord('A') + idx)}" / f"cat_organ_raw_{idx + 1}.json"
        data = json.loads(upstream_path.read_text(encoding="utf-8")) if upstream_path.exists() else generate_organ(style, idx)
        return json.dumps(decorate_organ(data, style), ensure_ascii=False, indent=2)

    if "猫咪成品汇总器" in name:
        organs: list[dict[str, Any]] = []
        for i in range(5):
            path = root / "output_delivery" / f"器官修饰师 {chr(ord('A') + i)}" / f"cat_organ_final_{i + 1}.json"
            if path.exists():
                organs.append(json.loads(path.read_text(encoding="utf-8")))
        return json.dumps({"cat_name": f"{style}猫咪", "complete_organ_set": organs}, ensure_ascii=False, indent=2)

    return deliverable.get("template", f"# Deliverable from {name}\n")
