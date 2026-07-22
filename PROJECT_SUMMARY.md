# Xujin Workflow MCP 项目说明书

> 生成日期：2026-07-20
> 项目路径：`/Users/xujin/Desktop/mcp_xujin_source/`
> 打包文件：`/Users/xujin/Desktop/mcp_xujin_source_20260720.zip`

---

## 1. 项目定位

Xujin Workflow MCP 是一个 Claude Code / Codex 插件，用于可视化编排多 Agent 工作流。

核心定位：
- 通过 MCP server 向编辑器暴露工作流操作工具。
- 通过 Web UI 提供可视化节点配置界面。
- 通过终端离线执行器 `/name` 在断开 MCP 后独立运行工作流。
- 每个工作流对应一个 Claude Code skill，存放在 `~/.claude/skills/{name}/`。

---

## 2. 核心能力

| 能力 | 说明 | 入口 |
|------|------|------|
| 工作流创建 | 输入工作流名称，自动生成 skill 目录、SKILL.md、flow.yml、运行时目录、终端函数 | Claude Code: `/name` → 说“创建” |
| 节点管理 | 增删改查 Agent 节点，配置身份、技能、规则、交付物、下游节点 | Web UI / MCP 工具 |
| 智能批量解析 | 粘贴 Agent 描述文本，自动解析并批量创建节点 | Web UI |
| 工作流删除 | 在 Web UI 头部一键删除整个工作流文件夹 | Web UI |
| 快照管理 | 创建 / 回滚版本快照 | MCP 工具 |
| 模板导入导出 | ZIP 格式导入导出工作流配置 | MCP 工具 |
| 离线执行 | 断开 MCP 后通过 `/name` 终端指令执行工作流 | 终端 |
| 双编辑器支持 | 同时配置 Claude Code 和 Codex 的 MCP server | `start.command` |

---

## 3. 交互逻辑

### 3.1 工作流与 Skill 的对应关系

```
~/.claude/skills/{name}/
├── SKILL.md          # Claude Code slash command /name 入口
├── flow.yml          # 工作流定义（节点、分支、交付物等）
├── templates/        # 交付物模板
├── validate_rules/   # 自定义校验规则
├── flow_fragments/   # 流程片段
├── input_source/     # 历史输入文件
├── output_delivery/  # 交付物输出
├── logs/             # 执行日志
├── state_store/      # 运行状态
└── versions/         # 版本快照
```

每个工作流是一个独立的 Claude Code skill。Claude Code 启动时扫描 `~/.claude/skills/{name}/SKILL.md`，生成 `/name` slash command。

### 3.2 创建新工作流

在 Claude Code 中：

```
创建一个 huayuan 工作流
```

后端自动完成：
1. 在 `~/.claude/skills/huayuan/` 创建目录结构。
2. 写入 `SKILL.md`（name=huayuan）。
3. 写入 `flow.yml`（name=huayuan）。
4. 在 `~/.zshrc` 追加 `/huayuan` 函数。
5. 提示用户重启 Claude Code 和 `source ~/.zshrc`。

### 3.3 Web UI 启动

```bash
# 启动最近修改的工作流
./start.command

# 启动指定工作流
./start.command suanshu
```

`start.command` 会：
1. 配置 Claude Code MCP server（`~/.claude/settings.json`）。
2. 配置 Codex MCP server（`~/.codex/config.toml`）。
3. 启动 Web UI。
4. 打开 Chrome。

### 3.4 Web UI 节点配置流程

1. 点击「+ 新建节点」或节点列表的「编辑」。
2. 填写名称、身份、技能、规则、交付物。
3. 点击「新增下个 Agent 节点」保存当前节点并继续创建子节点。
4. 点击左上角 ← 返回上一节点（当前节点参数会先保存）。
5. 点击「工作流设置完成」输入工作流名称并结束编排。

### 3.5 删除工作流

Web UI 头部卡片右侧有「删除工作流」按钮，点击二次确认后删除整个 skill 文件夹。

### 3.6 离线执行

```bash
source ~/.zshrc
/suanshu --start root --input data.json
```

---

## 4. 文件结构

```
mcp_xujin_source/
├── start.command              # Mac 一键启动脚本（配置 MCP + 启动 Web UI + 打开 Chrome）
├── start.sh                   # 通用启动脚本
├── start.common               # 共享启动逻辑
├── xujin                      # 离线执行入口脚本
├── pyproject.toml             # Python 包配置（name=mcp-xujin）
├── requirements.txt           # 依赖
├── global_config.json         # 全局配置
├── readme.md                  # 项目说明
├── docs/                      # 原始需求文档
│   ├── 需求说明书.md
│   ├── 开放使用文档.md
│   └── 存量工作流填充说明.md
└── src/mcp_xujin/
    ├── server.py              # MCP server（工具实现）
    ├── webui.py               # Flask Web UI 后端
    ├── executor.py            # 离线执行器
    ├── workflow.py            # 工作流数据模型
    ├── gate.py                # 防伪 ID / 状态门禁
    ├── validator.py           # 文件校验
    ├── logger.py              # 日志记录
    ├── utils.py               # 工具函数
    ├── templates/
    │   └── index.html         # Web UI 前端
    └── __main__.py            # python -m mcp_xujin 入口
```

---

## 5. 今天调整的功能

| # | 功能 | 改动文件 | 说明 |
|---|------|---------|------|
| 1 | 项目重命名 cainiao → xujin | 全部源码、配置、脚本 | 包名、模块名、脚本名、MCP server 名统一替换 |
| 2 | 工作流存放到 skill 目录 | `server.py`, `settings.json`, `start.command`, `SKILL.md` | 从 `/Users/xujin/Desktop/{name}` 改为 `~/.claude/skills/{name}/` |
| 3 | 通用化工作流创建 | `server.py` | `mscp_workflow_create` 只传 name 即可自动创建 skill、flow.yml、SKILL.md、~/.zshrc 函数 |
| 4 | start.command 支持工作流选择 | `start.command` | 无参数打开最近工作流，有参数打开指定工作流；MCP cwd 指向 `~/.claude/skills/` |
| 5 | 删除工作流 | `webui.py`, `index.html` | Web UI 头部增加删除按钮，删除整个 skill 文件夹 |
| 6 | 返回上一 Agent 缓存当前参数 | `index.html` | 点击 ← 先保存当前节点，再返回上一节点，数据不丢失 |
| 7 | 批量解析后打开最后节点 | `index.html` | 解析完成后自动打开最后一个创建的节点 |
| 8 | 工作流名称重复校验 | `webui.py` | 保存工作流名称时检查同级目录是否已存在 |
| 9 | Codex MCP 配置 | `start.command`, `~/.codex/config.toml` | 启动脚本自动追加 Codex MCP server 配置 |
| 10 | 创建示例工作流 | `~/.claude/skills/` | 已创建 fengmian、cainiao、suanshu 三个 skill |

---

## 6. 快速入手指南

### 6.1 环境恢复

解压 ZIP 后：

```bash
cd /Users/xujin/Desktop/mcp_xujin_source
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

### 6.2 启动开发

```bash
# 启动 Web UI（最近工作流）
./start.command

# 或启动指定工作流
./start.command suanshu
```

### 6.3 新增工作流

在 Claude Code 中：

```
创建一个 yingjun 工作流
```

然后：

```bash
source ~/.zshrc
```

### 6.4 新增 MCP 工具

编辑 `src/mcp_xujin/server.py`：
1. 在 `TOOLS` 字典中新增工具元数据和处理函数。
2. 工具函数接收 `args` 字典，返回 `_tool_result(message, is_error)`。
3. 如需操作工作流文件，使用 `workflow.load_flow(root)` / `workflow.save_flow(root, data)`。

### 6.5 新增 Web UI 功能

编辑 `src/mcp_xujin/webui.py` 和 `src/mcp_xujin/templates/index.html`：
1. 后端新增 `@app.route("/api/xxx")` 端点。
2. 前端新增 HTML + JS 调用。

---

## 7. 注意事项

1. **重启 Claude Code**：修改 `SKILL.md`、新增工作流、修改 MCP server 代码后，必须完全退出并重启 Claude Code 才能生效。
2. **`source ~/.zshrc`**：新增终端函数后需要执行。
3. **不要删除 `~/.claude/skills/` 下其他 skill**：只能删除由本工具生成的工作流 skill。
4. **工作流名称限制**：不能包含 `/ \ : * ? " < > |` 等字符，会被替换为下划线。
5. **MCP server cwd**：Claude Code 的 `settings.json` 中 `cwd` 指向 `~/.claude/skills/`，工具调用时必须显式传 `root` 参数。

---

## 8. 关键配置位置

| 配置 | 路径 |
|------|------|
| Claude Code 设置 | `~/.claude/settings.json` |
| Claude Code skills | `~/.claude/skills/{name}/SKILL.md` |
| Codex 配置 | `~/.codex/config.toml` |
| 终端函数 | `~/.zshrc` |
| 工作流数据 | `~/.claude/skills/{name}/flow.yml` |

---

## 9. 原始文档索引

如需查看完整原始需求，见项目内：

- `docs/需求说明书.md`
- `docs/开放使用文档.md`
- `docs/存量工作流填充说明.md`

本说明书已覆盖日常开发和恢复上下文所需信息，后续开发可优先以本文档为准。
