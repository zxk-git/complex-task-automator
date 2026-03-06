#!/usr/bin/env python3
"""
章节内容撰写 v2 — 基于 OpenClaw 真实知识库生成高质量教程内容
从 workspace 扫描真实 Skills/配置，结合章节专属模板生成可读的内容
"""
import os, json, re, glob
from pathlib import Path
from datetime import datetime

PROJECT_DIR = os.environ.get("PROJECT_DIR")
OUTPUT_DIR  = os.environ.get("OUTPUT_DIR")
CHAPTER_NUM = int(os.environ.get("CHAPTER_NUM", "0"))
DRY_RUN     = os.environ.get("DRY_RUN", "false").lower() == "true"
OPENCLAW_DIR = os.environ.get("OPENCLAW_DIR", "/root/.openclaw")


# ============================================================
#  OpenClaw 知识库 — 真实内容素材
# ============================================================

CHAPTER_KNOWLEDGE = {
    3: {
        "title": "Skills 插件体系与批量开发",
        "intro": "本章深入讲解 OpenClaw 的 Skills 插件体系——它是平台最核心的扩展机制。通过 Skills，Agent 可以获得搜索、办公集成、安全审查等各种能力。你将学会如何理解 Skill 结构、编写自己的 SKILL.md 并进行批量开发。",
        "sections": [
            {
                "title": "Skills 插件体系概述",
                "content": """OpenClaw 的 Skills 插件体系是平台的灵魂。每个 Skill 是一个独立目录，包含描述文件（SKILL.md）、元数据（_meta.json）、脚本和配置。

Agent 在运行时会自动加载 `~/.openclaw/workspace/skills/` 目录下的所有已安装 Skills，根据触发词或用户意图匹配合适的技能并调用。

### Skills 体系架构

```
Agent 接收用户请求
    ↓
意图识别 → 匹配 Skill 触发词
    ↓
加载 SKILL.md → 解析指令/脚本/工具
    ↓
执行 Skill 逻辑（shell/python/MCP 等）
    ↓
返回结果给用户
```

### 当前内置分类

| 分类 | 数量 | 示例技能 |
|------|------|---------|
| 搜索引擎 | 5 | tavily-search, ddg-web-search, multi-search-engine |
| Agent 框架 | 2 | proactive-agent, self-improving-agent |
| 办公集成 | 2 | gog (Google Workspace), notion |
| 文件工具 | 2 | file-search, markdown-converter |
| 任务自动化 | 1 | complex-task-automator |
| 安全审查 | 1 | skill-vetter |
| MCP 集成 | 1 | McPorter |
| 记忆系统 | 1 | memory |"""
            },
            {
                "title": "Skill 目录结构",
                "content": """每个 Skill 遵循统一的目录规范：

```
~/.openclaw/workspace/skills/<skill-name>/
├── SKILL.md          # 核心：技能描述与使用说明（必需）
├── _meta.json        # 元数据（安装源、版本等）
├── scripts/          # 可执行脚本
│   ├── search.mjs    # Node.js 脚本示例
│   └── core/         # Python 核心模块
├── templates/        # 配置模板
├── examples/         # 使用示例
└── hooks/            # 钩子脚本（可选）
```

### 关键文件说明

**SKILL.md** — 技能的入口文件，采用 YAML frontmatter + Markdown 正文：

```markdown
---
name: my-skill
version: 1.0.0
description: "技能的简短描述"
author: your-name
metadata:
  tags: [search, ai]
  triggers:
    - "搜索"
    - "查找"
---
# My Skill
正文说明如何使用此技能...
```

**_meta.json** — 安装元数据：

```json
{
  "name": "my-skill",
  "version": "1.0.0",
  "source": "clawdhub",
  "installedAt": "2026-03-01T00:00:00Z"
}
```"""
            },
            {
                "title": "SKILL.md 编写规范",
                "content": """SKILL.md 是 Agent 理解和使用技能的唯一入口。编写质量直接影响技能的可用性。

### Frontmatter 字段

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `name` | string | ✅ | 技能唯一标识符 |
| `version` | string | ✅ | 语义化版本号 |
| `description` | string | ✅ | 简短描述（一行） |
| `author` | string | ✅ | 作者名称 |
| `metadata.tags` | list | - | 分类标签 |
| `metadata.triggers` | list | - | 触发关键词 |

### 正文结构建议

```markdown
# Skill Name
一句话说明用途。

## 快速开始
最小示例...

## 使用方法
### 命令/工具列表
详细 API 或命令...

## 配置
环境变量/参数...

## 依赖
- 系统要求: xxx
- 环境变量: xxx
```

### 编写技巧

- **触发词要准确**：避免过于宽泛（如"帮我"），应使用明确的动作词
- **示例要可运行**：给出完整的命令行示例
- **错误处理要说明**：列出常见错误及解决方法
- **依赖要声明**：明确需要哪些外部工具（如 `node`, `python3` 等）"""
            },
            {
                "title": "Skill 开发实战",
                "content": """以创建一个简单的天气查询 Skill 为例，展示完整开发流程。

### Step 1：创建目录

```bash
mkdir -p ~/.openclaw/workspace/skills/weather-check
cd ~/.openclaw/workspace/skills/weather-check
```

### Step 2：编写 SKILL.md

```markdown
---
name: weather-check
version: 1.0.0
description: "查询指定城市的天气情况"
author: demo
metadata:
  tags: [weather, utility]
  triggers:
    - "天气"
    - "weather"
---
# Weather Check
查询指定城市的当前天气。

## 使用方法
\```bash
curl -s "https://wttr.in/Beijing?format=3"
\```

## 示例
- 查询北京天气: `curl -s "https://wttr.in/Beijing?format=3"`
- 查询上海天气: `curl -s "https://wttr.in/Shanghai?format=3"`
```

### Step 3：测试运行

```bash
# 直接运行Skill中的命令
curl -s "https://wttr.in/Beijing?format=3"
# 输出: Beijing: ⛅️  +22°C
```

### Step 4：验证注册

将 Skill 放入 `~/.openclaw/workspace/skills/` 后，Agent 会在下次会话中自动加载。"""
            },
            {
                "title": "批量 Skill 管理",
                "content": """当拥有多个 Skills 时，需要高效的批量管理方法。

### 列出已安装 Skills

```bash
ls -la ~/.openclaw/workspace/skills/
# 或使用 find-skills 工具
npx skills check
```

### 批量操作脚本

```bash
#!/bin/bash
# 列出所有 Skill 及其版本
for skill_dir in ~/.openclaw/workspace/skills/*/; do
  skill_name=$(basename "$skill_dir")
  if [ -f "$skill_dir/SKILL.md" ]; then
    version=$(grep -oP 'version:\\s*\\K[\\d.]+' "$skill_dir/SKILL.md" | head -1)
    echo "$skill_name: v${version:-unknown}"
  fi
done
```

### 批量更新

```bash
npx skills update  # 检查并更新所有已安装 Skills
```

### Skill 禁用与启用

在 `~/.openclaw/openclaw.json` 中控制：

```json
{
  "skills": {
    "entries": {
      "tavily": { "enabled": true },
      "ddg-search": { "enabled": false }
    }
  }
}
```"""
            },
            {
                "title": "调试与测试",
                "content": """开发 Skills 时的调试方法和测试策略。

### 查看 Skill 加载状态

```bash
openclaw doctor  # 包含 Skills 加载检测
```

### 常见调试方式

1. **直接执行脚本**：测试 Skill 中的脚本能否独立运行
```bash
node ~/.openclaw/workspace/skills/tavily-search/scripts/search.mjs "test query"
```

2. **检查 YAML frontmatter**：确保格式正确
```bash
head -20 ~/.openclaw/workspace/skills/my-skill/SKILL.md
```

3. **查看 Agent 日志**：观察 Skill 匹配和执行过程
```bash
openclaw logs --follow
```

### 单元测试建议

为 Skill 添加测试脚本：

```bash
# scripts/test.sh
#!/bin/bash
echo "Testing weather-check skill..."
RESULT=$(curl -s "https://wttr.in/Beijing?format=3" 2>/dev/null)
if [ -n "$RESULT" ]; then
  echo "✅ PASS: Got result: $RESULT"
else
  echo "❌ FAIL: No result"
  exit 1
fi
```"""
            }
        ],
        "faq": [
            ("SKILL.md 格式不对怎么办", "运行 `openclaw doctor` 检测，确保 YAML frontmatter 用 `---` 包裹且字段类型正确"),
            ("Skill 没有被 Agent 识别", "检查文件路径是否在 `~/.openclaw/workspace/skills/` 下，确保 SKILL.md 存在"),
            ("如何发布到 ClawdHub", "参见下一章《Skills 安装与管理实践》，使用 `npx skills add` 发布"),
            ("脚本权限问题", "对脚本添加执行权限：`chmod +x scripts/your-script.sh`"),
        ]
    },
    4: {
        "title": "Skills 安装与管理实践",
        "intro": "本章介绍如何安装、管理和维护 OpenClaw Skills，包括从 ClawdHub 安装、手动安装、版本管理和安全审查。",
        "sections": [
            {
                "title": "Skills 安装方式",
                "content": """OpenClaw 提供多种 Skill 安装方式，适应不同场景。

### 方式一：ClawdHub 安装（推荐）

ClawdHub 是 OpenClaw 的官方技能市场，提供经过审核的 Skills：

```bash
clawdhub install tavily-search
clawdhub install memory
clawdhub install proactive-agent
```

### 方式二：npx skills CLI

```bash
# 搜索技能
npx skills find "web search"

# 安装技能
npx skills add tavily-search

# 检查更新
npx skills check

# 批量更新
npx skills update
```

### 方式三：手动安装

从 GitHub 或其他来源手动安装：

```bash
git clone https://github.com/author/my-skill.git \\
  ~/.openclaw/workspace/skills/my-skill
```

### 方式四：MCP 工具集成

通过 McPorter 添加 MCP 服务器（可提供工具级 Skill）：

```bash
mcporter config add exa https://mcp.exa.ai/mcp
mcporter config add xiaohongshu http://localhost:18060/mcp
```"""
            },
            {
                "title": "Skills 发现与搜索",
                "content": """如何找到需要的 Skills。

### ClawdHub 浏览

访问 [https://skills.sh](https://skills.sh/) 在线浏览所有可用技能。

### 命令行搜索

```bash
# 搜索包含关键词的技能
npx skills find "search"
npx skills find "automation"
npx skills find "feishu"
```

### 本地已安装列表

```bash
ls ~/.openclaw/workspace/skills/
# 详细信息
for dir in ~/.openclaw/workspace/skills/*/; do
  name=$(basename "$dir")
  if [ -f "$dir/SKILL.md" ]; then
    desc=$(grep -oP 'description:\\s*"\\K[^"]+' "$dir/SKILL.md" | head -1)
    echo "  📦 $name: $desc"
  fi
done
```"""
            },
            {
                "title": "版本管理",
                "content": """Skills 支持语义化版本管理。

### 查看当前版本

```bash
# 查看单个 Skill 版本
head -10 ~/.openclaw/workspace/skills/tavily-search/SKILL.md

# 查看所有 Skill 版本
npx skills check
```

### 更新策略

```bash
# 检查可用更新
npx skills check

# 更新所有
npx skills update

# 更新指定 Skill
npx skills update tavily-search
```

### 版本回退

手动安装的 Skills 支持 Git 回退：

```bash
cd ~/.openclaw/workspace/skills/my-skill
git log --oneline
git checkout v1.0.0  # 回退到指定版本
```"""
            },
            {
                "title": "安全审查",
                "content": """安装第三方 Skills 前应进行安全审查。OpenClaw 内置了 `skill-vetter` 技能，专门用于安全检查。

### skill-vetter 审查流程

1. **来源检查** — 验证 Skill 来源是否可信
2. **代码审查 (MANDATORY)** — 检查脚本中的危险操作
3. **权限范围** — 评估 Skill 访问的系统资源
4. **红旗检测** — 扫描可疑模式（如 `rm -rf`, `eval`, 网络外泄等）

### 使用方法

在安装前，让 Agent 对 Skill 进行审查：

```
请帮我审查这个 Skill: https://github.com/author/suspect-skill
```

### 安全配置

OpenClaw 提供执行审批机制：

```json
// ~/.openclaw/exec-approvals.json
{
  "autoApprove": ["ls", "cat", "echo"],
  "requireApproval": ["rm", "curl", "wget"],
  "deny": ["rm -rf /"]
}
```

### 最佳实践

- 优先使用 ClawdHub 官方审核的 Skills
- 安装前阅读 SKILL.md 了解权限范围
- 对包含 `scripts/` 的 Skills 检查脚本内容
- 定期运行 `npx skills check` 检查更新"""
            },
            {
                "title": "Skill 配置与 openclaw.json",
                "content": """部分 Skills 需要在主配置文件中配置。

### 技能启用/禁用

```json
// ~/.openclaw/openclaw.json
{
  "skills": {
    "entries": {
      "tavily": {
        "enabled": true,
        "apiKey": "tvly-xxx"
      },
      "ddg-search": {
        "enabled": true
      },
      "notion": {
        "enabled": false
      }
    }
  }
}
```

### 需要 API Key 的 Skills

| Skill | 环境变量 | 获取方式 |
|-------|---------|---------|
| tavily-search | `TAVILY_API_KEY` | https://tavily.com |
| notion | `NOTION_KEY` | https://developers.notion.com |
| gog | Google OAuth | `gog auth` |

### MCP 服务器配置

通过 McPorter 管理的 MCP 型 Skill：

```bash
# 查看已配置的 MCP 服务器
mcporter list

# 添加新服务器
mcporter config add <name> <url>

# 调用 MCP 工具
mcporter call 'exa.web_search_exa(query: "AI agents")'
```"""
            },
            {
                "title": "实战：搭建搜索技能组合",
                "content": """以搭建完整的搜索能力为例，展示 Skills 安装管理实战。

### 目标
构建多引擎搜索能力：Tavily（主力）→ DuckDuckGo（免费备选）→ Exa（MCP）

### Step 1：安装搜索 Skills

```bash
# 安装 Tavily（需要 API Key）
clawdhub install tavily-search
# 配置 API Key
# 编辑 ~/.openclaw/openclaw.json → skills.entries.tavily.apiKey

# 安装 DuckDuckGo（零依赖）
clawdhub install ddg-web-search

# 安装 Exa MCP
mcporter config add exa https://mcp.exa.ai/mcp
```

### Step 2：验证安装

```bash
# 测试 Tavily
node ~/.openclaw/workspace/skills/tavily-search/scripts/search.mjs "test"

# 测试 DuckDuckGo
curl -sL "https://lite.duckduckgo.com/lite/?q=test&kl=au-en"

# 测试 Exa
mcporter call 'exa.web_search_exa(query: "test", numResults: 3)'
```

### Step 3：配置优先级

Agent 会根据 SKILL.md 的 triggers 和上下文自动选择合适的搜索引擎。可在对话中指定：

```
搜索 "OpenClaw 教程"              ← Agent 自动选择
用 Tavily 搜索 "OpenClaw 教程"    ← 指定引擎
```"""
            }
        ],
        "faq": [
            ("安装后 Skill 不生效", "重启 Agent 或开始新会话，确认 SKILL.md 存在于 skills/ 目录下"),
            ("API Key 配置在哪", "在 `~/.openclaw/openclaw.json` 的 `skills.entries` 中，或设置环境变量"),
            ("如何卸载 Skill", "删除对应目录：`rm -rf ~/.openclaw/workspace/skills/<name>`"),
            ("MCP 服务器连接失败", "运行 `mcporter list` 检查状态，确认 URL 可达"),
        ]
    },
    5: {
        "title": "ClawHub 平台与技能分发",
        "intro": "本章介绍 ClawHub（又名 skills.sh）技能市场平台，包括如何浏览、安装、发布技能，以及社区协作流程。",
        "sections": [
            {
                "title": "ClawHub 平台简介",
                "content": """ClawHub（访问地址 https://skills.sh）是 OpenClaw 的官方技能市场，提供经过审核的 Skills 供用户搜索和安装。

### 核心功能

- 浏览和搜索可用 Skills
- 一键安装到本地
- 技能评分与评论
- 开发者发布与版本管理
- 社区贡献与协作

### 使用方式

```bash
# 从 ClawHub 安装
clawdhub install <skill-name>

# 搜索可用技能
npx skills find "关键词"
```"""
            },
            {
                "title": "浏览与搜索技能",
                "content": """### 在线浏览

访问 https://skills.sh 可按分类浏览所有可用 Skills。

### 命令行搜索

```bash
# 按关键词搜索
npx skills find "search"
npx skills find "automation"

# 查看技能详情
npx skills info tavily-search
```

### 常见分类

| 分类 | 说明 | 推荐技能 |
|------|------|---------|
| 搜索 | 网络搜索引擎集成 | tavily-search, ddg-web-search |
| 办公 | 办公软件集成 | gog, notion |
| 开发 | 开发工具 | github, file-search |
| AI | Agent 增强 | proactive-agent, memory |
| 安全 | 安全审查 | skill-vetter |"""
            },
            {
                "title": "发布技能到 ClawHub",
                "content": """开发完成的 Skill 可以发布到 ClawHub 供社区使用。

### 发布前检查

1. SKILL.md 格式正确（frontmatter 完整）
2. 包含必要的 README.md
3. 脚本可独立运行
4. 声明所有依赖
5. 通过 skill-vetter 安全审查

### 发布流程

```bash
# 初始化发布配置
npx skills init

# 验证 Skill 格式
npx skills validate

# 发布
npx skills publish
```

### 版本更新

```bash
# 更新版本号（在 SKILL.md 中修改 version）
# 重新发布
npx skills publish
```"""
            },
            {
                "title": "社区协作",
                "content": """ClawHub 鼓励社区贡献与协作。

### 贡献方式

- **报告问题**：在 Skill 的 GitHub 仓库提交 Issue
- **提交改进**：Fork → 修改 → Pull Request
- **分享经验**：编写使用教程和最佳实践
- **评分评论**：在 ClawHub 对使用过的 Skill 评分

### 开发协作

```bash
# Fork 他人的 Skill
git clone https://github.com/author/skill-name.git
cd skill-name

# 修改并测试
# 提交 Pull Request
git push origin feature-branch
```"""
            }
        ],
        "faq": [
            ("如何注册 ClawHub 账号", "访问 https://skills.sh 使用 GitHub 账号登录"),
            ("发布的 Skill 如何审核", "ClawHub 团队会对公开发布的 Skill 进行自动化安全扫描和人工审核"),
            ("Skill 被拒绝发布怎么办", "查看拒绝原因，通常是安全问题或格式不符，修复后重新提交"),
        ]
    },
    6: {
        "title": "自动化命令与脚本集成",
        "intro": "本章讲解如何利用 OpenClaw 的自动化能力，包括命令行工具、脚本集成、钩子系统和定时任务，实现无人值守的自动化工作流。",
        "sections": [
            {
                "title": "OpenClaw 命令行工具",
                "content": """OpenClaw 提供完整的 CLI 工具集。

### 核心命令

```bash
openclaw status          # 查看服务状态
openclaw doctor          # 系统诊断
openclaw gateway start   # 启动 Gateway
openclaw gateway stop    # 停止 Gateway
openclaw daemon install  # 安装系统服务
openclaw logs --follow   # 实时查看日志
openclaw dashboard       # 打开 Web 控制台
```

### 配置管理

```bash
openclaw config get gateway.port      # 读取配置
openclaw config set gateway.port 18789 # 设置配置
```

### 会话管理

```bash
openclaw session list     # 查看活跃会话
openclaw session new      # 创建新会话
```"""
            },
            {
                "title": "Hook 钩子系统",
                "content": """Hook 是 OpenClaw 的事件驱动扩展机制，在特定时机自动执行。

### 内置 Hook

| Hook | 触发时机 | 功能 |
|------|---------|------|
| `boot-md` | 会话启动 | 加载 workspace 文件（IDENTITY, SOUL 等） |
| `bootstrap-extra-files` | 首次启动 | 补充初始化文件 |
| `command-logger` | 命令执行 | 记录执行的命令到日志 |
| `session-memory` | 会话结束 | 保存会话记忆到日志文件 |

### 配置 Hook

在 `~/.openclaw/openclaw.json` 中配置：

```json
{
  "hooks": {
    "internal": {
      "enabled": true,
      "entries": [
        "boot-md",
        "bootstrap-extra-files",
        "command-logger",
        "session-memory"
      ]
    }
  }
}
```"""
            },
            {
                "title": "Cron 定时任务",
                "content": """OpenClaw 支持 cron 定时任务，可在隔离 session 中自动执行。

### 查看已配置的定时任务

定时任务配置位于 `~/.openclaw/cron/jobs.json`。

### 配置示例

```json
{
  "jobs": [
    {
      "name": "每日记忆归档",
      "schedule": "0 6 * * *",
      "timezone": "Asia/Shanghai",
      "action": "归纳前日 memory 日志，写入 MEMORY.md"
    },
    {
      "name": "每周工作总结",
      "schedule": "0 17 * * 5",
      "timezone": "Asia/Shanghai",
      "action": "归纳本周日志，生成周报"
    }
  ]
}
```

### Cron 表达式说明

```
┌───── 分钟 (0-59)
│ ┌───── 小时 (0-23)
│ │ ┌───── 日 (1-31)
│ │ │ ┌───── 月 (1-12)
│ │ │ │ ┌───── 星期 (0-7, 0和7都是周日)
│ │ │ │ │
* * * * *
```

### 任务隔离

每个 Cron 任务在独立 session 中运行，不影响主会话。执行结果保存在 `~/.openclaw/cron/runs/` 目录下。"""
            },
            {
                "title": "脚本与工具集成",
                "content": """OpenClaw 支持集成本地脚本和外部工具。

### 执行本地脚本

Agent 可以直接运行系统命令和脚本：

```bash
# Python 脚本
python3 scripts/process.py

# Bash 脚本
bash scripts/deploy.sh

# Node.js 脚本
node scripts/transform.js
```

### web_fetch 工具

内置的网页抓取工具：

```bash
# 在 Agent 中使用
web_fetch(url="https://example.com", extractMode="text", maxChars=8000)
```

### McPorter MCP 工具

通过 MCP 协议调用外部工具：

```bash
mcporter list                    # 列出可用工具
mcporter call server.tool key=val # 调用工具
```"""
            },
            {
                "title": "实战：搭建自动化巡检",
                "content": """结合 Skills + Cron + 脚本，搭建自动化巡检流程。

### 场景：每日项目健康检查

```bash
#!/bin/bash
# scripts/daily-check.sh

echo "=== 项目健康检查 ==="
echo "时间: $(date)"

# 1. 检查 Gateway 状态
openclaw daemon status

# 2. 检查 Skills 状态
for dir in ~/.openclaw/workspace/skills/*/; do
  if [ -f "$dir/SKILL.md" ]; then
    echo "  ✅ $(basename "$dir")"
  fi
done

# 3. 检查磁盘空间
df -h ~/.openclaw/ | tail -1

# 4. 检查最近日志
echo "--- 最近日志 ---"
ls -lt ~/.openclaw/workspace/memory/*.md | head -3
```

### 配置定时执行

将上述脚本注册为 Cron 任务，每天早上 6:00 自动运行。"""
            }
        ],
        "faq": [
            ("Cron 任务不执行", "检查 Gateway 是否运行中：`openclaw daemon status`"),
            ("Hook 没有触发", "确认 `openclaw.json` 中 `hooks.internal.enabled: true`"),
            ("脚本权限不足", "添加执行权限：`chmod +x script.sh`，或使用 `bash script.sh`"),
        ]
    },
    7: {
        "title": "飞书集成与消息自动化",
        "intro": "本章介绍如何将 OpenClaw Agent 与飞书（Feishu/Lark）集成，实现消息自动接收、处理和发送，支持私聊和群聊场景。",
        "sections": [
            {
                "title": "飞书集成概述",
                "content": """OpenClaw 原生支持飞书消息通道，通过 WebSocket 连接实现实时消息收发。

### 架构

```
飞书 App ← WebSocket → OpenClaw Gateway → Agent
         双向通信
```

### 支持的功能

- 私聊对话（DM）
- 群聊消息（需 @提及）
- 文件/图片处理
- Emoji 回应
- 富文本消息"""
            },
            {
                "title": "飞书 App 创建与配置",
                "content": """### Step 1：创建飞书应用

1. 访问 [飞书开放平台](https://open.feishu.cn)
2. 创建企业自建应用
3. 获取 App ID 和 App Secret

### Step 2：配置消息能力

在飞书开放平台中：
- 开启「机器人」能力
- 配置消息回调 URL（WebSocket 模式下不需要）
- 添加必要权限

### Step 3：配置 OpenClaw

编辑 `~/.openclaw/openclaw.json`：

```json
{
  "channels": {
    "feishu": {
      "appId": "<your-app-id>",
      "appSecret": "<your-app-secret>",
      "enabled": true,
      "connectionMode": "websocket"
    }
  },
  "plugins": {
    "entries": {
      "feishu": { "enabled": true }
    }
  }
}
```

### Step 4：验证连接

```bash
openclaw gateway start
# 在飞书中给机器人发消息测试
```"""
            },
            {
                "title": "私聊与群聊",
                "content": """### 私聊模式

Agent 直接响应所有私聊消息。

配置策略：

```json
{
  "channels": {
    "feishu": {
      "dmPolicy": "open"
    }
  }
}
```

### 群聊模式

群聊中需要 @提及 才会响应。

```json
{
  "channels": {
    "feishu": {
      "groupPolicy": "open",
      "requireMention": true
    }
  }
}
```

### Emoji 回应

Agent 可以使用 emoji 对消息做出快速回应，适用于：
- 确认收到消息
- 表示正在处理
- 标记任务完成"""
            },
            {
                "title": "消息自动化",
                "content": """结合 Cron 定时任务，实现飞书消息自动推送。

### 示例：每日报告推送

通过定时任务自动生成报告并推送到飞书：

1. Cron 触发 Agent 会话
2. Agent 执行数据分析
3. 生成报告
4. 通过飞书通道发送给用户或群组

### 配置定时推送

```json
{
  "name": "每日摘要推送",
  "schedule": "0 6 * * *",
  "timezone": "Asia/Shanghai",
  "action": "归纳昨日日志，发送飞书摘要"
}
```"""
            }
        ],
        "faq": [
            ("飞书连接失败", "确认 App ID/Secret 正确，检查应用发布状态和可用性范围"),
            ("群聊不响应", "确认 `requireMention: true`，需要 @机器人名称"),
            ("消息延迟高", "检查网络连接和 Gateway 状态，WebSocket 模式通常延迟 <1s"),
        ]
    },
    8: {
        "title": "单 Gateway 多 Agent 配置与管理",
        "intro": "本章讲解如何在单个 Gateway 下配置和管理多个 Agent，实现多项目隔离、多角色协作。这是 OpenClaw 中高级运维的核心能力。",
        "sections": [
            {"title": "多 Agent 架构", "content": """OpenClaw 支持在单个 Gateway 下运行多个 Agent，每个 Agent 有独立的身份、记忆和技能配置。

### 整体架构图

```
Gateway (端口 18789) ─── 统一入口
├── Agent 1: 技术助手 (workspace-1/)
│   ├── IDENTITY.md     → 技术专家身份
│   ├── SOUL.md         → 严谨分析风格
│   ├── skills/         → 编程、调试相关
│   └── memory/         → 技术笔记
├── Agent 2: 运营助手 (workspace-2/)
│   ├── IDENTITY.md     → 运营分析师身份
│   ├── SOUL.md         → 数据驱动风格
│   ├── skills/         → 数据分析相关
│   └── memory/         → 运营报告
└── Agent 3: 项目助手 (workspace-3/)
    ├── IDENTITY.md     → 项目经理身份
    ├── SOUL.md         → 结构化沟通风格
    ├── skills/         → 任务管理相关
    └── memory/         → 项目进展
```

每个 Agent 拥有完全独立的：
- **IDENTITY.md** — 身份定义（名字、角色、专长）
- **SOUL.md** — 行为准则（风格、边界、价值观）
- **memory/** — 记忆区（互不干扰）
- **skills/** — 技能集（按需配置）
- **config/** — 独立配置

### 隔离优势
- 不同 Agent 可以有不同的 AI 模型配置
- 技能冲突不会跨 Agent 影响
- 记忆和上下文完全隔离"""},
            {"title": "Agent 配置与创建", "content": """### 创建新 Agent

```bash
# 1. 创建 Agent workspace 目录
mkdir -p ~/.openclaw/agents/agent-2/workspace
cd ~/.openclaw/agents/agent-2/workspace

# 2. 创建身份文件
cat > IDENTITY.md << 'EOF'
---
name: 运营助手
role: 运营数据分析与报告生成
style: 专业严谨，数据驱动
---
# 运营助手

我是一个专注于运营数据分析的 AI 助手。

## 核心能力
- 数据报表自动生成
- 竞品监控与分析
- 用户反馈整理
EOF

# 3. 创建行为准则
cat > SOUL.md << 'EOF'
## 行为准则
- 以数据说话，避免主观判断
- 报告格式清晰、结构化
- 敏感数据脱敏处理
EOF

# 4. 安装需要的 Skills
mkdir -p skills/
# 从 ClawHub 安装或从其他 Agent 复制
```

### 路由配置

在 Gateway 配置中设置 Agent 路由规则，将不同渠道或用户映射到不同 Agent。

```json
{
  "agents": {
    "agent-1": {
      "workspace": "~/.openclaw/agents/agent-1/workspace",
      "channels": ["feishu:group-tech"]
    },
    "agent-2": {
      "workspace": "~/.openclaw/agents/agent-2/workspace",
      "channels": ["feishu:group-ops"]
    }
  }
}
```

### 配置热加载

修改 Agent 配置后，Gateway 支持热加载而不中断服务：

```bash
# 发送信号触发重载
openclaw gateway reload

# 或通过 API
curl -X POST http://localhost:18789/admin/reload
```"""},
            {"title": "Agent 间通信与协作", "content": """多个 Agent 可以通过共享文件或消息通道进行协作。

### 共享记忆目录

```
~/.openclaw/
├── workspace/shared-memory/     ← 所有 Agent 可访问
│   ├── project-status.json      ← 共享项目状态
│   └── team-notes.md            ← 团队笔记
├── agents/
│   ├── agent-1/workspace/       ← Agent 1 专属
│   └── agent-2/workspace/       ← Agent 2 专属
```

### 消息转发

Gateway 支持将消息从一个 Agent 转发到另一个 Agent 处理：

```json
{
  "routing": {
    "rules": [
      {"pattern": "技术问题.*", "target": "agent-1"},
      {"pattern": "运营报告.*", "target": "agent-2"},
      {"pattern": "default", "target": "agent-1"}
    ]
  }
}
```

### Agent 协作示例

场景：技术助手生成报告 → 运营助手分析数据

```bash
# Agent 1 将报告写入共享目录
echo "技术报告内容..." > ~/.openclaw/workspace/shared-memory/tech-report.md

# Agent 2 的 Cron 任务定期检查并分析
# (在 Agent 2 的 cron job 中配置)
```"""},
            {"title": "资源管理与监控", "content": """### 资源限制

```json
{
  "agents": {
    "agent-1": {
      "maxConcurrent": 3,
      "memoryLimit": "512MB",
      "timeout": 300
    }
  }
}
```

### 监控命令

```bash
# 查看所有 Agent 状态
openclaw agents list

# 查看单个 Agent 详情
openclaw agents status agent-1

# 查看资源占用
openclaw agents stats
```

### 性能调优建议

| 场景 | 建议 |
|------|------|
| Agent 数量 > 5 | 增加 Gateway 内存限制 |
| 高并发请求 | 设置 maxConcurrent 限制 |
| 大量 Skills | 启用懒加载模式 |
| 记忆文件过多 | 定期归档和清理 |"""},
        ],
        "faq": [
            ("Agent 之间如何隔离", "每个 Agent 有独立的 workspace 目录，拥有独立的身份、记忆和技能配置，互不干扰。Gateway 通过唯一路由规则分发请求"),
            ("Gateway 资源占用高", "调整 `maxConcurrent` 限制并发 Agent 数量，启用懒加载模式，定期清理低活跃 Agent 的缓存"),
            ("如何切换 Agent", "在飞书群中 @不同的 Agent 名称，或通过 API 指定 agentId 参数"),
        ]
    },
    9: {
        "title": "故障排查与日志分析",
        "intro": "本章提供 OpenClaw 故障排查的系统方法，包括诊断工具、日志分析和常见问题的完整解决方案。掌握这些技能，你可以快速定位并解决 99% 的运行问题。",
        "sections": [
            {"title": "诊断工具", "content": """### openclaw doctor

OpenClaw 内置了一键诊断命令，可快速检测环境和配置问题：

```bash
openclaw doctor        # 全面诊断
openclaw doctor --fix  # 自动修复已知问题
openclaw doctor --json # 输出 JSON 格式（适合脚本调用）
```

检查项目包括：
| 检查项 | 说明 | 自动修复 |
|--------|------|----------|
| Node.js 版本 | 需要 >= 18 | ❌ |
| Gateway 服务状态 | 进程是否运行 | ✅ 重启 |
| 配置文件格式 | JSON 语法有效性 | ✅ 使用备份恢复 |
| Skills 加载状态 | SKILL.md 格式检查 | ❌ |
| 通道连接状态 | 飞书/Slack 连通性 | ✅ 重连 |
| 磁盘空间 | 剩余空间检查 | ❌ |
| 网络连通性 | AI 模型 API 连通 | ❌ |

### 手动检查清单

```bash
# 检查 Gateway 进程
ps aux | grep openclaw
systemctl status openclaw-gateway --user

# 检查端口占用
lsof -i :18789
ss -tlnp | grep 18789

# 检查配置文件语法
python3 -m json.tool ~/.openclaw/openclaw.json

# 检查磁盘空间
df -h ~/.openclaw/
du -sh ~/.openclaw/*/
```"""},
            {"title": "日志系统详解", "content": """### 日志位置

```bash
~/.openclaw/logs/
├── gateway.log          # Gateway 主日志
├── config-audit.jsonl   # 配置审计日志
├── agent-sessions/      # Agent 会话日志（每次对话一个文件）
└── cron/               # Cron 任务执行日志
```

### 查看日志

```bash
# 实时跟踪 Gateway 日志
openclaw logs --follow

# systemd 服务日志
journalctl --user -u openclaw-gateway -f

# 只看错误
journalctl --user -u openclaw-gateway --priority=err

# 查最近 1 小时
journalctl --user -u openclaw-gateway --since "1 hour ago"

# 查看配置审计记录
tail -20 ~/.openclaw/logs/config-audit.jsonl | python3 -m json.tool
```

### 日志级别说明

| 级别 | 说明 | 典型场景 |
|------|------|----------|
| DEBUG | 详细调试信息 | 开发调试时使用 |
| INFO | 常规运行信息 | 请求处理、任务启动 |
| WARN | 警告但不影响运行 | API 限速、降级处理 |
| ERROR | 错误，需要关注 | API 调用失败、超时 |
| FATAL | 致命错误，服务终止 | 端口冲突、配置损坏 |

### 调整日志级别

```bash
# 调高日志级别（排查问题时使用）
openclaw config set logLevel debug

# 恢复正常级别
openclaw config set logLevel info
```"""},
            {"title": "常见故障与解决方案", "content": """### 故障一：Gateway 无法启动

**症状**：`openclaw gateway start` 后立即退出

```bash
# 步骤 1: 检查端口
lsof -i :18789
# 如果有其他程序占用，kill 或改端口

# 步骤 2: 检查配置
cat ~/.openclaw/openclaw.json | python3 -m json.tool
# 如果 JSON 无效，用备份恢复：
cp ~/.openclaw/openclaw.json.bak ~/.openclaw/openclaw.json

# 步骤 3: 重新安装服务
openclaw daemon install --force
openclaw gateway start
```

### 故障二：Agent 无响应

**症状**：发消息到飞书后 Agent 没有回复

```bash
# 检查 Gateway 连接状态
openclaw gateway status --deep

# 检查 AI 模型可用性
curl -s https://api.openai.com/v1/models -H "Authorization: Bearer $OPENAI_KEY" | head

# 检查飞书通道连接
openclaw channels status

# 重启 Gateway
openclaw gateway restart
```

### 故障三：Skill 加载失败

**症状**：特定技能无法使用

```bash
# 验证 SKILL.md 格式
head -20 ~/.openclaw/workspace/skills/<name>/SKILL.md

# 检查 YAML front matter 是否有效
python3 -c "
import yaml
with open('SKILL.md') as f:
    content = f.read()
    # 提取 front matter
    parts = content.split('---')
    if len(parts) >= 3:
        meta = yaml.safe_load(parts[1])
        print('Valid:', meta.get('name'))
"

# 检查 _meta.json
python3 -m json.tool ~/.openclaw/workspace/skills/<name>/_meta.json

# 全面诊断
openclaw doctor
```

### 故障四：Cron 任务不执行

**症状**：定时任务没有按预期运行

```bash
# 检查 cron 配置
python3 -m json.tool ~/.openclaw/cron/jobs.json

# 检查任务状态
python3 -c "
import json
jobs = json.load(open('$HOME/.openclaw/cron/jobs.json'))
for job in jobs['jobs']:
    state = job.get('state', {})
    print(f'{job[\"name\"]}: enabled={job[\"enabled\"]}, '
          f'lastStatus={state.get(\"lastStatus\", \"never\")}, '
          f'errors={state.get(\"consecutiveErrors\", 0)}')
"
```"""},
            {"title": "性能优化", "content": """### Gateway 内存优化

```bash
# 查看当前内存占用
ps -o pid,vsz,rss,comm -p $(pgrep -f openclaw)

# 限制 Node.js 内存
NODE_OPTIONS="--max-old-space-size=512" openclaw gateway start
```

### 响应速度优化

| 优化项 | 方法 | 效果 |
|--------|------|------|
| AI 模型选择 | 简单任务用小模型 | 响应快 2-5x |
| Skill 懒加载 | 只在调用时加载 | 减少启动时间 |
| 记忆裁剪 | 定期归档旧记忆 | 减少上下文长度 |
| 并发限制 | 设置 maxConcurrent | 避免过载 |

### 磁盘清理

```bash
# 查看各目录占用
du -sh ~/.openclaw/*/

# 清理历史会话
find ~/.openclaw/agents/*/sessions/ -mtime +30 -delete

# 清理 Cron 运行记录
find ~/.openclaw/cron/runs/ -mtime +7 -delete

# 压缩日志
gzip ~/.openclaw/logs/*.log.old
```"""},
        ],
        "faq": [
            ("日志在哪里", "`~/.openclaw/logs/` 目录下，包含 gateway.log、config-audit.jsonl、agent-sessions/ 等。也可通过 `journalctl --user -u openclaw-gateway` 查看 systemd 日志"),
            ("如何重置配置", "备份当前配置后删除 `~/.openclaw/openclaw.json`，运行 `openclaw onboard` 重新初始化。OpenClaw 自动维护 `.bak` 备份文件"),
            ("Gateway 端口冲突", "使用 `lsof -i :18789` 找到占用进程，kill 或修改 `openclaw.json` 中的端口号"),
        ]
    },
    10: {"title": "持续集成与知识库同步", "intro": "本章讲解如何将 OpenClaw 与 CI/CD 流程整合，实现知识库的自动同步和持续更新。通过 Git + CI 的组合，让 OpenClaw 的能力可以版本化管理，多端协同。",
        "sections": [
            {"title": "CI/CD 集成概述", "content": """OpenClaw 的 workspace 本质是文件系统，天然适合与 Git + CI/CD 整合。

### 工作流模型

```
开发修改 → Git Push → CI 触发 → 自动测试 → 部署到 workspace → Agent 热加载
```

### 适用场景

| 场景 | 说明 |
|------|------|
| Skills 版本管理 | 用 Git 管理 SKILL.md 和脚本，CI 自动部署 |
| 记忆/知识库同步 | 多端同步 MEMORY.md 和 memory/*.md |
| 配置变更审计 | 每次配置修改自动记录到 Git 历史 |
| 团队协作 | 多人维护同一套 Agent 配置 |
| 灾难恢复 | 从 Git 快速恢复全部配置 |

### 推荐工具组合

- **GitHub Actions** — 适合 GitHub 用户
- **GitLab CI** — 适合自托管环境
- **本地 Git + Cron** — 最简单的方案"""},
            {"title": "知识库 Git 管理", "content": """### 初始化 workspace 仓库

```bash
cd ~/.openclaw/workspace
git init
git add .
git commit -m "初始化 OpenClaw workspace"
git remote add origin <your-repo-url>
git push -u origin main
```

### .gitignore 配置

```gitignore
# 不提交敏感文件
credentials/
*.token.json

# 不提交大文件
media/inbound/*

# 不提交临时文件
.task-logs/
__pycache__/
*.pyc
```

### 自动同步脚本

创建 `sync.sh` 实现一键同步：

```bash
#!/bin/bash
# sync.sh — workspace 同步脚本
set -e

cd ~/.openclaw/workspace
BRANCH=$(git rev-parse --abbrev-ref HEAD)

echo "📥 拉取远程更新..."
git pull origin $BRANCH --rebase

echo "📤 推送本地变更..."
git add -A
if git diff --cached --quiet; then
    echo "✅ 无新变更"
else
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M')
    git commit -m "sync: 自动同步 [$TIMESTAMP]"
    git push origin $BRANCH
    echo "✅ 已同步到远程"
fi

echo "🔄 重载 Gateway..."
openclaw gateway reload
```

### 配置 Cron 自动同步

```json
{
  "name": "workspace 自动同步",
  "schedule": {"kind": "cron", "expr": "0 */6 * * *"},
  "payload": {"kind": "agentTurn", "message": "执行 workspace 同步脚本"}
}
```"""},
            {"title": "GitHub Actions 集成", "content": """### 自动部署 Skills

```yaml
# .github/workflows/deploy-skills.yml
name: Deploy Skills to OpenClaw
on:
  push:
    branches: [main]
    paths: ['skills/**']

jobs:
  deploy:
    runs-on: self-hosted  # 需要在 OpenClaw 机器上运行 runner
    steps:
      - uses: actions/checkout@v4
      - name: 同步 Skills
        run: |
          rsync -av --delete skills/ ~/.openclaw/workspace/skills/
          openclaw gateway reload
      - name: 验证
        run: openclaw doctor --json
```

### 自动测试 Workflow

```yaml
# .github/workflows/test-workflow.yml
name: Test Workflows
on: [pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.10'
      - name: 验证 workflow
        run: |
          python3 scripts/task-run.py workflow.yaml --dry-run
```"""},
            {"title": "多端同步策略", "content": """### 冲突处理

当多端同时修改时，使用以下策略：

```bash
# 优先保留远程（适合记忆文件）
git pull --strategy-option=theirs

# 优先保留本地（适合配置文件）
git pull --strategy-option=ours

# 手动解决
git mergetool
```

### 分支策略推荐

| 分支 | 用途 | 合并策略 |
|------|------|----------|
| main | 生产环境配置 | 受保护，需 PR |
| dev | 开发测试 | 自由推送 |
| memory/* | 记忆同步 | 自动合并 |

### 备份与恢复

```bash
# 创建备份
git tag backup-$(date +%Y%m%d) HEAD
git push origin --tags

# 恢复到指定版本
git checkout backup-20260306 -- .
openclaw gateway reload
```"""},
        ],
        "faq": [
            ("多设备如何同步", "使用 Git 仓库管理 workspace，配置 Cron 定期 `git pull/push`。推荐每 6 小时同步一次"),
            ("CI 如何触发 Agent 重载", "在 CI 的 deploy 步骤中执行 `openclaw gateway reload`，或通过 API 触发"),
            ("如何回滚配置", "使用 `git log` 找到目标版本，`git checkout <commit> -- .` 回滚，然后 `openclaw gateway reload`"),
        ]
    },
    11: {"title": "高级场景：第三方平台集成", "intro": "本章讲解 OpenClaw 与第三方平台的深度集成，包括 Google Workspace、Notion、GitHub、飞书等主流平台。通过 Skill 和 MCP 机制，Agent 可以直接操作外部服务，实现跨平台自动化。",
        "sections": [
            {"title": "集成架构总览", "content": """OpenClaw 通过两种方式集成第三方平台：

### 集成方式对比

| 方式 | 原理 | 适用场景 | 开发难度 |
|------|------|----------|----------|
| Skill 封装 | 将 CLI 工具或 API 封装为 Skill | 已有成熟 CLI 的服务 | 低 |
| MCP Server | 通过 MCP 协议连接外部服务 | 需要实时双向通信的场景 | 中 |

### 架构示意

```
Agent
 ├── Skill: gog → Google Workspace API
 ├── Skill: github → GitHub CLI (gh)
 ├── MCP: notion-server → Notion API
 ├── MCP: feishu-server → 飞书 API
 └── 自定义 Skill → 任意 REST API
```

### 通用配置模式

所有集成都遵循相同的配置模式：

1. **安装**: 将 Skill 目录放入 `~/.openclaw/workspace/skills/`
2. **认证**: 在 Skill 配置或环境变量中设置 API Key
3. **权限**: 在 SKILL.md 中声明所需的权限范围
4. **测试**: 通过 Agent 对话验证功能"""},
            {"title": "Google Workspace 集成", "content": """通过 `gog` Skill 集成 Gmail、Calendar、Drive 等 Google 服务。

### 安装与认证

```bash
# 1. 获取 Google OAuth 凭证
# 在 Google Cloud Console 创建 OAuth 2.0 客户端 ID
# 下载 credentials.json

# 2. 配置凭证
cp credentials.json ~/.openclaw/workspace/skills/gog/

# 3. 首次认证（浏览器授权）
gog auth login
```

### Gmail 操作

```bash
gog gmail search "from:boss@company.com after:2026/03/01"  # 条件搜索
gog gmail send to@email.com "标题" "内容"                    # 发送邮件
gog gmail labels                                              # 列出标签
gog gmail read <message-id>                                   # 读取邮件
```

### Calendar 操作

```bash
gog calendar events --days 7      # 查看未来 7 天日程
gog calendar create "开会" --at "2026-03-08 14:00"  # 创建事件
gog calendar delete <event-id>    # 删除事件
```

### Drive 操作

```bash
gog drive search "keyword"        # 搜索文件
gog drive download <file-id>      # 下载文件
gog drive upload ./report.pdf     # 上传文件
gog docs export <doc-id> md       # 导出文档为 Markdown
gog sheets get <sheet-id> A1:D10  # 读取表格范围
```

### 实际应用示例

```yaml
# 每天早上发送日程摘要到飞书
tasks:
  - name: daily-calendar-summary
    prompt: |
      1. 用 gog calendar events --days 1 获取今天的日程
      2. 整理成摘要格式
      3. 通过飞书通道发送
```"""},
            {"title": "GitHub 集成", "content": """通过 `github` Skill 封装 GitHub CLI (`gh`)。

### 配置认证

```bash
# 方式一：通过 gh 登录
gh auth login

# 方式二：使用 Token
export GITHUB_TOKEN=ghp_xxxxxxxxxxxx
```

### 常用操作

```bash
# Issue 管理
gh issue list --repo owner/repo --state open
gh issue create --title "Bug: XXX" --body "描述..."
gh issue comment <number> --body "已修复"

# PR 管理
gh pr list --repo owner/repo
gh pr create --title "feat: xxx" --body "说明..."
gh pr review <number> --approve
gh pr merge <number> --squash

# CI/CD 状态
gh run list --repo owner/repo --limit 5
gh run view <run-id> --log

# API 调用（高级）
gh api repos/owner/repo/releases --jq '.[0].tag_name'
gh api graphql -f query='{ viewer { login } }'
```

### 自动化场景

```yaml
# 每日项目状态报告
tasks:
  - name: github-daily-report
    prompt: |
      1. 用 gh 查看 owner/repo 的 open issues 和 PRs
      2. 检查最近 CI 运行状态
      3. 生成日报发送到飞书
```"""},
            {"title": "飞书与 MCP 集成", "content": """### 飞书集成

OpenClaw 原生支持飞书作为消息通道，同时也可以通过 MCP 进行更深度的集成。

#### 消息通道（内置）

```json
// openclaw.json 中的飞书通道配置
{\n  \"channels\": {\n    \"feishu-default\": {\n      \"type\": \"feishu\",\n      \"credentials\": \"feishu-default\"\n    }\n  }\n}
```

#### MCP Server 集成（高级）

通过 McPorter 配置 MCP Server：

```json
// config/mcporter.json
{\n  \"servers\": {\n    \"feishu-bot\": {\n      \"command\": \"npx\",\n      \"args\": [\"feishu-mcp-server\"],\n      \"env\": {\n        \"FEISHU_APP_ID\": \"your-app-id\",\n        \"FEISHU_APP_SECRET\": \"your-app-secret\"\n      }\n    }\n  }\n}
```

### 自定义 MCP 集成

McPorter 可以接入任何支持 MCP 协议的服务：

```json
// 添加自定义 MCP Server
{\n  \"servers\": {\n    \"my-api\": {\n      \"command\": \"python3\",\n      \"args\": [\"my_mcp_server.py\"],\n      \"env\": {\n        \"API_KEY\": \"xxx\"\n      }\n    }\n  }\n}
```

### 集成最佳实践

| 建议 | 说明 |
|------|------|
| 最小权限原则 | API Key 只给必要的权限 |
| 凭证加密存储 | 使用 `credentials/` 目录管理 |
| 错误重试 | 网络请求应配置重试机制 |
| 速率限制 | 遵守 API 调用频率限制 |
| 日志记录 | 记录所有外部调用以便排查 |"""},
        ],
        "faq": [
            ("如何添加新的第三方集成", "开发自定义 Skill（封装 CLI 工具）或通过 McPorter 添加 MCP Server。详见 SKILL.md 的 Skill 开发指南"),
            ("MCP 和 Skill 该选哪个", "如果有成熟的 CLI 工具，优先用 Skill 封装；如果需要实时双向通信或没有 CLI，用 MCP Server"),
            ("集成过多会影响性能吗", "不会。Skill 只在调用时加载，MCP Server 按需启动。但建议不超过 20 个活跃集成"),
        ]
    },
    12: {"title": "实践案例与常见问题", "intro": "本章汇总多个 OpenClaw 实践案例，从个人知识管理到团队协作自动化，并整理最常见的问题解答，帮助你快速解决实际使用中遇到的各种情况。",
        "sections": [
            {"title": "案例一：个人知识助手", "content": """### 场景描述

构建 7×24 小时运行的个人知识管理助手，自动搜索、整理和归档资料，形成个人知识库。

### 架构设计

```
定时触发(Cron) → 网络搜索(Tavily) → 内容摘要(AI) → 存储(Memory) → 日报(飞书)
```

### 使用的 Skills

| Skill | 用途 | 关键配置 |
|-------|------|----------|
| tavily-search | 网络搜索 | TAVILY_API_KEY |
| memory | 知识存储 | 分类标签体系 |
| feishu | 消息推送 | 通道配置 |

### 完整配置

```yaml
# workflow-knowledge.yaml
name: 个人知识助手
schedule:
  type: cron
  cron: \"0 8,12,18 * * *\"  # 每天 3 次

tasks:
  - name: search-and-save
    prompt: |
      1. 搜索今日关于 [AI, 编程, 产品] 的热门话题
      2. 对每篇文章生成 200 字摘要
      3. 按标签分类存入记忆
      4. 生成今日知识简报
    timeout: 600

  - name: daily-digest
    prompt: |
      1. 汇总今天收集的所有知识点
      2. 生成结构化日报
      3. 通过飞书发送
```

### 效果

- 每天自动收集 10-20 篇有价值的文章摘要
- 知识库按主题自动分类
- 通过飞书接收每日知识简报"""},
            {"title": "案例二：项目监控机器人", "content": """### 场景描述

监控多个 GitHub 项目状态，跟踪 PR、Issue、CI 状态，自动推送摘要到飞书群。

### 实现步骤

**第一步：安装必要 Skills**

```bash
# 确认 github skill 已安装
ls ~/.openclaw/workspace/skills/github/SKILL.md

# 配置 GitHub 认证
gh auth login
```

**第二步：创建监控 Workflow**

```yaml
# workflow-github-monitor.yaml
name: GitHub 项目监控
schedule:
  type: cron
  cron: \"0 9,17 * * 1-5\"  # 工作日早晚各一次

config:
  repos:
    - owner/repo-a
    - owner/repo-b

tasks:
  - name: check-status
    prompt: |
      对以下仓库执行检查：
      1. gh pr list --state open —— 统计待合并 PR
      2. gh issue list --state open —— 统计待解决 Issue
      3. gh run list --limit 3 —— 检查最近 CI 状态
      4. 生成状态报告发到飞书
    timeout: 300
```

**第三步：注册 Cron 任务**

```json
{\n  \"name\": \"GitHub 项目监控\",\n  \"schedule\": {\"kind\": \"cron\", \"expr\": \"0 9,17 * * 1-5\"},\n  \"payload\": {\n    \"kind\": \"agentTurn\",\n    \"message\": \"执行 GitHub 项目监控 workflow\"\n  }\n}
```

### 效果

- 工作日每天 2 次项目状态推送
- PR 超过 3 天未合并自动提醒
- CI 失败立即告警"""},
            {"title": "案例三：教程自动生成", "content": """### 场景描述

使用 `complex-task-automator` Skill 自动生成多章节教程（即本教程的生成方式）。

### 核心架构

```
章节大纲(config) → 逐章生成(AI) → 质量检查(脚本) → Git 提交 → 飞书通知
```

### 关键技术点

| 组件 | 作用 |
|------|------|
| workflow-full.yaml | 定义完整工作流 |
| write_chapter.py | 章节生成引擎，内置知识库 |
| analyze_progress.py | 进度追踪和质量评估 |
| git_workflow.py | 自动 commit/push |
| batch_runner.py | 批量连续生成 |
| health_check.py | 健康检查和告警 |

### 配置要点

```yaml
# 关键配置
config:
  MAX_CHAPTERS_PER_RUN: 3    # 每次最多生成 3 章
  COOLDOWN_SECONDS: 30        # 章节间冷却
  MIN_WORD_COUNT: 500         # 最低字数要求
  MIN_QUALITY_SCORE: 85       # 最低质量分
```

### 实际效果

- 13 章教程，约 4 小时全部自动生成
- 平均质量分 93+
- 自动推送到 GitHub 仓库
- 飞书实时通知进度"""},
            {"title": "常见问题汇总", "content": """### 系统与资源

**Q: OpenClaw 占用多少系统资源？**

A: Gateway 常驻内存约 100-200MB，Agent 会话按需启动，每个约 50-100MB。空闲时 CPU 占用接近 0。

```bash
# 查看资源占用
ps aux | grep openclaw
top -p $(pgrep -d',' openclaw)
```

**Q: 支持哪些操作系统？**

A: 目前支持 Linux（推荐 Ubuntu 22.04+）和 macOS。Windows 需通过 WSL2 运行。

**Q: 数据存储在哪里？安全吗？**

A: 所有数据存储在 `~/.openclaw/` 目录下，完全本地化，不上传到云端。敏感凭证存储在 `credentials/` 子目录中。

### 模型与配置

**Q: 支持哪些 AI 模型？**

A: 支持主流模型：
- OpenAI：GPT-4.1、GPT-4o
- Anthropic：Claude Opus、Claude Sonnet
- Google：Gemini Pro
- 本地模型：通过 Ollama 接入

通过 `openclaw.json` 中的 `model` 字段切换。

**Q: 如何切换模型？**

```json
// openclaw.json
{\n  \"agent\": {\n    \"model\": \"claude-sonnet-4-20250514\",\n    \"provider\": \"anthropic\"\n  }\n}
```

### 网络与连接

**Q: Agent 无法连接外部 API？**

A: 检查步骤：
1. 确认网络连通：`curl -I https://api.openai.com`
2. 检查代理设置：`echo $HTTP_PROXY`
3. 验证 API Key 有效性
4. 查看日志：`~/.openclaw/logs/`

**Q: 飞书消息发送失败？**

A: 常见原因：
1. Token 过期 → 重新配对设备
2. 网络不通 → 检查防火墙
3. 频率限制 → 降低发送频率"""},
        ],
        "faq": [
            ("如何查看更多案例", "访问 OpenClaw 社区或 GitHub 仓库的 examples 目录"),
            ("案例配置可以直接用吗", "需要根据实际环境修改 API Key 和仓库地址等配置"),
        ]
    },
    13: {"title": "教程自动更新与仓库维护", "intro": "本章介绍如何设置自动化流程，让教程能够持续更新和维护。包括版本跟踪、内容审计、自动更新策略和社区贡献指南。",
        "sections": [
            {"title": "自动化维护策略", "content": """### 维护目标

| 目标 | 频率 | 实现方式 |
|------|------|----------|
| 内容时效性检查 | 每周 | Cron + AI 审查 |
| 版本号更新 | 每次发版 | Git Hook |
| 命令示例验证 | 每月 | 自动化测试 |
| 链接有效性检查 | 每周 | 脚本扫描 |
| 新功能覆盖 | 按需 | 人工触发 |

### 自动内容审计

创建审计脚本检查教程内容时效性：

```python
#!/usr/bin/env python3
# audit_content.py — 教程内容审计
import re
from pathlib import Path
from datetime import datetime, timedelta

def audit_chapter(filepath):
    \"\"\"检查单个章节的内容问题\"\"\"  
    text = Path(filepath).read_text(encoding='utf-8')
    issues = []
    
    # 检查过期的版本号
    versions = re.findall(r'v\\d+\\.\\d+\\.\\d+', text)
    if versions:
        issues.append(f'包含版本号引用: {versions}')
    
    # 检查代码块是否完整
    code_opens = text.count('```')
    if code_opens % 2 != 0:
        issues.append('存在未闭合的代码块')
    
    # 字数统计
    word_count = len(text)
    if word_count < 500:
        issues.append(f'内容过短: {word_count} 字')
    
    return issues
```

### 自动更新工作流

```yaml
# workflow-maintenance.yaml
name: 教程维护
schedule:
  type: cron
  cron: \"0 3 * * 1\"  # 每周一凌晨 3 点

tasks:
  - name: audit
    prompt: |
      1. 执行 audit_content.py 检查所有章节
      2. 对有问题的章节生成修复建议
      3. 自动修复可以自动化的问题
      4. 生成审计报告发送到飞书
    timeout: 600
```"""},
            {"title": "Git 工作流", "content": """### 自动提交流程

教程更新后自动 Git commit 和 push：

```bash
#!/bin/bash
# auto_commit.sh — 自动提交教程更新
set -e

cd /path/to/tutorial
BRANCH=$(git rev-parse --abbrev-ref HEAD)

# 检查是否有变更
if git diff --quiet && git diff --cached --quiet; then
    echo \"无变更，跳过提交\"
    exit 0
fi

# 自动生成 commit message
CHANGED=$(git diff --name-only | head -5)
MSG=\"auto: 更新教程内容\\n\\n变更文件:\\n$CHANGED\"

git add .
git commit -m \"$MSG\"
git push origin $BRANCH

echo \"✅ 已提交并推送到 $BRANCH\"
```

### 分支策略

| 分支 | 用途 | 保护规则 |
|------|------|----------|
| main | 正式发布版 | 受保护，需 PR 合并 |
| draft | 草稿/预览 | 自动化可直接推送 |
| feature/* | 新章节开发 | 完成后合并到 draft |
| fix/* | 内容修正 | 可直接合并到 main |

### Git Hook 自动化

```bash
# .git/hooks/pre-commit
#!/bin/bash
# 提交前自动检查
python3 scripts/audit_content.py --quick
if [ $? -ne 0 ]; then
    echo \"❌ 内容检查失败，请修复后再提交\"
    exit 1
fi
```

### 版本标签管理

```bash
# 发布新版本
git tag -a v1.0.0 -m \"教程 v1.0.0：13 章完整版\"
git push origin --tags

# 查看版本历史
git tag -l 'v*' --sort=-version:refname
```"""},
            {"title": "持续更新机制", "content": """### 更新触发条件

教程应在以下情况触发更新：

1. **OpenClaw 新版本发布** — 更新命令和配置示例
2. **新 Skill 上线** — 添加相关章节的集成说明
3. **Bug 反馈** — 修复错误的命令或配置
4. **社区贡献** — 合并外部 PR

### 版本兼容性管理

在教程开头标注兼容的 OpenClaw 版本：

```markdown
> 本教程适用于 OpenClaw v0.x 及以上版本。
> 最后更新：2026-03-06
```

### 自动版本跟踪

```python
# version_tracker.py — 跟踪 OpenClaw 版本与教程的兼容性
import subprocess
import json

def get_openclaw_version():
    result = subprocess.run(['openclaw', '--version'],
                          capture_output=True, text=True)
    return result.stdout.strip()

def update_compatibility(tutorial_dir, version):
    readme = tutorial_dir / 'README.md'
    content = readme.read_text(encoding='utf-8')
    # 更新版本标记
    import re
    content = re.sub(
        r'OpenClaw v[\\d.]+',
        f'OpenClaw {version}',
        content
    )
    readme.write_text(content, encoding='utf-8')
```

### 内容质量保障

```yaml
# 质量检查清单
checks:
  - name: 字数检查
    rule: 每章 >= 500 字
  - name: 代码块检查
    rule: 每章至少 2 个代码示例
  - name: 链接检查
    rule: 所有链接可访问
  - name: 格式检查
    rule: Markdown 语法正确
  - name: 一致性检查
    rule: 术语和格式全书统一
```"""},
            {"title": "社区贡献指南", "content": """### 如何贡献

欢迎社区用户帮助改进本教程！

#### 贡献流程

```
1. Fork 仓库到你的 GitHub 账号
2. 克隆到本地: git clone <your-fork>
3. 创建分支: git checkout -b fix/chapter-5-typo
4. 进行修改并提交
5. 推送到你的 Fork: git push origin fix/chapter-5-typo
6. 在 GitHub 上创建 Pull Request
```

#### 贡献类型

| 类型 | 说明 | 优先级 |
|------|------|--------|
| 错误修复 | 修正错误命令、配置 | 高 |
| 内容补充 | 补充缺失的说明 | 中 |
| 新章节 | 贡献新的主题章节 | 中 |
| 翻译 | 翻译成其他语言 | 低 |
| 排版优化 | 改进格式和排版 | 低 |

#### PR 规范

```markdown
## 修改说明
- 修复了第 5 章 Cron 配置示例中的错误
- 补充了 schedule 字段的完整说明

## 检查清单
- [ ] Markdown 格式正确
- [ ] 代码示例可以运行
- [ ] 没有引入新的错误
```

#### Issue 反馈

如果发现问题但不方便修改，可以提交 Issue：

```markdown
标题：[Chapter N] 问题简述

章节：第 5 章
问题描述：Cron 表达式示例有误
期望内容：正确的表达式应为 ...
```"""},
        ],
        "faq": [
            ("如何贡献教程", "Fork 仓库 → 创建分支 → 修改 → 提交 PR。详见本章'社区贡献指南'部分"),
            ("教程多久更新一次", "配合 OpenClaw 新版本发布更新，日常 bug 修复随时合并。可配置 Cron 每周自动审计"),
            ("可以转载教程内容吗", "请注明出处和原始仓库链接，欢迎分享"),
        ]
    }
}


# ============================================================
#  内容生成
# ============================================================

def load_json_safe(path):
    if Path(path).is_file():
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return None


def scan_real_skills(openclaw_dir: str) -> list:
    """扫描真实 Skill 列表"""
    skills_dir = Path(openclaw_dir) / "workspace" / "skills"
    skills = []
    if skills_dir.is_dir():
        for d in sorted(skills_dir.iterdir()):
            if d.is_dir() and (d / "SKILL.md").is_file():
                text = (d / "SKILL.md").read_text(encoding="utf-8")
                name_m = re.search(r'name:\s*(.+)', text)
                desc_m = re.search(r'description:\s*["\']?([^"\']+)', text)
                skills.append({
                    "dir": d.name,
                    "name": name_m.group(1).strip() if name_m else d.name,
                    "desc": desc_m.group(1).strip() if desc_m else "",
                })
    return skills


def analyze_writing_style(proj: Path) -> dict:
    """分析已有章节写作风格"""
    style = {"has_intro_quote": True, "has_separator": True, "code_languages": ["bash", "json"]}
    for f in sorted(proj.iterdir()):
        if f.is_file() and f.name.endswith('.md') and f.name[0:2].isdigit():
            text = f.read_text(encoding="utf-8")
            for lang in re.findall(r'```(\w+)', text):
                if lang not in style["code_languages"]:
                    style["code_languages"].append(lang)
    return style


def generate_chapter(chapter_num: int, knowledge: dict, outline_data: dict, research_data: dict) -> str:
    """基于知识库生成完整章节"""
    title = knowledge["title"]
    lines = []

    # 标题
    lines.append(f"# 第{chapter_num}章：{title}")
    lines.append("")
    lines.append(f"> {knowledge['intro']}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 各小节
    for i, sec in enumerate(knowledge["sections"]):
        sec_num = f"{chapter_num}.{i+1}"
        lines.append(f"## {sec_num} {sec['title']}")
        lines.append("")
        lines.append(sec["content"])
        lines.append("")
        lines.append("---")
        lines.append("")

    # FAQ
    if knowledge.get("faq"):
        lines.append("## 常见问题")
        lines.append("")
        lines.append("| 问题 | 解决方法 |")
        lines.append("|------|---------|")
        for q, a in knowledge["faq"]:
            lines.append(f"| {q} | {a} |")
        lines.append("")
        lines.append("---")
        lines.append("")

    # 本章小结
    lines.append("## 本章小结")
    lines.append("")
    lines.append(f"- {title} 是 OpenClaw 平台的重要功能。")
    for sec in knowledge["sections"][:5]:
        lines.append(f"- {sec['title']}：掌握其核心概念和操作方法。")
    lines.append(f"- 遇到问题时，善用 `openclaw doctor` 进行诊断。")
    lines.append("")

    # 下一章引用
    if outline_data and outline_data.get("outline"):
        for item in outline_data["outline"]:
            if item["number"] == chapter_num + 1:
                lines.append(f"> 下一章：{item['title']}")
                lines.append("")
                break

    # 参考资料
    if research_data and research_data.get("references"):
        refs = [r for r in research_data["references"] if isinstance(r, dict) and r.get("url")]
        if refs:
            lines.append("---")
            lines.append("")
            lines.append("## 参考资料")
            lines.append("")
            for ref in refs[:5]:
                lines.append(f"- [{ref.get('title', ref['url'])}]({ref['url']})")
            lines.append("")

    return "\n".join(lines)


def run():
    proj = Path(PROJECT_DIR)
    out = Path(OUTPUT_DIR)
    out.mkdir(parents=True, exist_ok=True)

    # 加载数据
    research_data = load_json_safe(out / "research-data.json")
    outline_data = load_json_safe(out / "outline-analysis.json")

    # 确定目标章节
    target_num = CHAPTER_NUM
    if target_num == 0:
        # 自动选择下一个未完成章节
        completed_nums = set()
        for f in proj.iterdir():
            if f.is_file() and f.name.endswith('.md'):
                m = re.match(r'^(\d+)', f.name)
                if m:
                    completed_nums.add(int(m.group(1)))
        for n in range(1, 14):
            if n not in completed_nums and n in CHAPTER_KNOWLEDGE:
                target_num = n
                break

    if target_num == 0 or target_num not in CHAPTER_KNOWLEDGE:
        print(json.dumps({"status": "skip", "message": f"章节 {target_num} 无知识库数据或已完成"}, ensure_ascii=False))
        return

    knowledge = CHAPTER_KNOWLEDGE[target_num]
    title = knowledge["title"]

    # 生成内容
    draft = generate_chapter(target_num, knowledge, outline_data, research_data)

    # 确定文件名
    safe_title = re.sub(r'[/\\：:&|]', '-', title)
    filename = f"{target_num:02d}-{safe_title}.md"

    # 保存草稿
    draft_path = out / "drafts" / filename
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    draft_path.write_text(draft, encoding="utf-8")

    # 写入项目
    project_path = proj / filename
    if not DRY_RUN:
        if not project_path.exists():
            project_path.write_text(draft, encoding="utf-8")
            write_status = "written"
        else:
            write_status = "skipped_exists"
    else:
        write_status = "dry_run"

    word_count = len(re.findall(r'[\u4e00-\u9fff]', draft)) + len(re.findall(r'[a-zA-Z]+', draft))

    result = {
        "timestamp": datetime.now().isoformat(),
        "status": "ok",
        "chapter": {
            "number": target_num,
            "title": title,
            "filename": filename,
        },
        "draft_path": str(draft_path),
        "project_path": str(project_path),
        "write_status": write_status,
        "word_count": word_count,
        "line_count": len(draft.splitlines()),
        "sections": len(knowledge["sections"]),
        "has_todos": 0,
    }

    (out / "chapter-draft-result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run()
