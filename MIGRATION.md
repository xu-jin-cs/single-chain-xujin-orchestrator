# 迁移说明

`mcp-xujin-workflow` 已迁移到新的离线工作流引擎。

## 旧方式（已弃用）

- 通过 MCP server 编辑工作流
- Claude Code 内调用 `mcp-xujin-workflow` 工具
- `flow.yml` 中的 agent 只是数据节点

## 新方式

- 工作流 = 普通 Claude skill，位于 `~/.claude/skills/user/<workflow-name>/`
- 每个 agent 是独立 subagent，通过 `claude -p` 调用
- 工作流定义在 `workflow.yml`，agent 定义在 `agents/<name>.md`
- 通用引擎：`~/.claude/skills/user/workflow-engine/`

## shici 示例

```bash
python3 ~/.claude/skills/user/workflow-engine/bin/workflow-run.py \
  --workflow ~/.claude/skills/shici \
  --input '{"topic": "秋夜"}'
```

## 保留文件

本目录源码继续保留作为参考，但不再作为 Claude Code 的入口。
