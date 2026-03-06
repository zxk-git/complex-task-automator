```skill
---
name: complex-task-automator
version: 2.2.0
description: "高级任务自动化引擎 - 支持信息搜集、大纲管理、文档撰写、Git 远程推送的全链路自动化。24/7 无人值守，OpenClaw Cron 自动调度，批量章节生成，六维度多指标质量检测，持续网络搜索优化，健康检查与飞书推送。包含依赖管理、并行执行、失败重试、断点恢复与完整执行追踪。"
author: openclaw
metadata:
  tags:
    - automation
    - task-management
    - workflow
    - scheduling
    - document-generation
    - git-automation
    - research
    - content-writing
  triggers:
    - "复杂任务"
    - "自动化工作流"
    - "批处理"
    - "任务调度"
    - "信息搜集"
    - "大纲管理"
    - "章节撰写"
    - "文档生成"
    - "Git 自动提交"
    - "Git 推送"
    - "教程自动化"
    - "写作助手"
    - "24/7 自动化"
    - "定时调度"
    - "批量生成"
    - "健康检查"
    - "持续优化"
    - "多维度质量检测"
    - "网络信息搜索"
    - "内容自动优化"
---

# Complex Task Automator 🚀

**高级任务自动化引擎** — 从信息搜集到 Git 推送的全链路文档工作流自动化

## 核心特性

| 特性 | 说明 |
|------|------|
| **信息搜集** | 自动从网络/本地资料源搜集信息，提取摘要，标注来源 |
| **大纲管理** | 生成与优化文档大纲，追踪版本变更历史 |
| **内容撰写** | 根据大纲生成 Markdown 草稿，保持风格一致，零占位符 |
| **Git 自动化** | 检测变更、生成 commit 信息、提交并推送到远程仓库 |
| **24/7 自动调度** | OpenClaw Cron 定时批量生成，健康检查，飞书推送，全自动无人值守 |
| **持续网络优化** | 自动搜索网络最新信息，智能识别可优化章节，合并新内容，自动提交推送 |
| **六维度质量检测** | 内容充实度、结构完整性、代码质量、可读性、教学价值、时效性多维评估 |
| **任务拆解** | 将复杂工作流分解为可执行的子任务 |
| **依赖管理** | 定义任务间依赖关系，确保正确执行顺序 |
| **并行执行** | 无依赖的任务并行运行，提高效率 |
| **失败重试** | 可配置重试机制，支持退避策略 |
| **状态追踪** | 完整的执行日志和状态管理 |
| **断点恢复** | 支持从失败点继续执行 |
| **安全可控** | DRY_RUN 模式、文件保护、Git 白名单，不破坏已确认数据 |

---

## 目录

1. [快速开始](#快速开始)
2. [文档自动化工作流](#文档自动化工作流)
3. [信息搜集与整理](#信息搜集与整理)
4. [大纲与章节管理](#大纲与章节管理)
5. [内容撰写与文档生成](#内容撰写与文档生成)
6. [Git 自动化与远程推送](#git-自动化与远程推送)
7. [安全与可控性](#安全与可控性)
8. [24/7 持续优化](#247-持续优化)
9. [六维度质量检测系统](#六维度质量检测系统)
9. [架构设计](#架构设计)
10. [任务模型](#任务模型)
11. [任务配置](#任务配置)
12. [执行引擎](#执行引擎)
13. [日志系统](#日志系统)
14. [失败处理](#失败处理)
15. [调度机制](#调度机制)
16. [扩展开发](#扩展开发)
17. [最佳实践](#最佳实践)
18. [API 参考](#api-参考)

---

## 快速开始

### 安装

**通过 ClawdHub（推荐）：**
```bash
clawdhub install complex-task-automator
```

**手动安装：**
```bash
git clone https://github.com/openclaw/complex-task-automator.git ~/.openclaw/skills/complex-task-automator
```

### 基本使用

```yaml
# 定义一个简单的任务流
name: my-first-workflow
tasks:
  - id: fetch-data
    type: shell
    command: "curl -o data.json https://api.example.com/data"
    
  - id: process-data
    type: python
    script: "scripts/process.py"
    depends_on: [fetch-data]
    
  - id: notify
    type: webhook
    url: "https://hooks.example.com/notify"
    depends_on: [process-data]
```

执行任务流：
```bash
python3 scripts/task-run.py my-first-workflow.yaml
```

---

## 文档自动化工作流

这是 v2.0.0 的核心功能——将文档生命周期各阶段串联成一条可控的自动化流水线。

### 完整工作链

```
信息搜集 (research.py)
    ↓ research-data.json
大纲分析 (manage_outline.py)
    ↓ outline-analysis.json
内容撰写 (write_chapter.py)
    ↓ 03-XXX.md (草稿)
质量检查 (check_quality.py)
    ↓ 02-quality-check.json
Git 提交 (git_workflow.py)
    ↓ commit [+ push]
报告生成 (generate_report.py)
    ↓ .automation-report.md
```

### 标准工作流配置

```yaml
# workflows/my-project/workflow-full.yaml
name: doc-automation-pipeline
version: "2.0"
description: "文档全链路自动化"

variables:
  PROJECT_DIR: "/path/to/your/project"
  OUTPUT_DIR: "/tmp/my-project-reports"
  SCRIPTS_DIR: "workflows/my-project/scripts"
  MIN_WORDS: "800"
  DRY_RUN: "false"
  GIT_AUTO_COMMIT: "true"
  GIT_AUTO_PUSH: "false"    # 谨慎：推送需明确开启
  CHAPTER_NUM: "0"          # 0 = 自动检测下一未完成章节

tasks:
  - id: init
    type: shell
    command: "mkdir -p ${OUTPUT_DIR}/drafts"

  - id: research
    type: python
    script: "${SCRIPTS_DIR}/research.py"
    depends_on: [init]

  - id: manage-outline
    type: python
    script: "${SCRIPTS_DIR}/manage_outline.py"
    depends_on: [research]

  - id: write-chapter
    type: python
    script: "${SCRIPTS_DIR}/write_chapter.py"
    depends_on: [manage-outline]

  - id: check-quality
    type: python
    script: "${SCRIPTS_DIR}/check_quality.py"
    depends_on: [write-chapter]

  - id: git-workflow
    type: python
    script: "${SCRIPTS_DIR}/git_workflow.py"
    depends_on: [check-quality]

  - id: generate-report
    type: python
    script: "${SCRIPTS_DIR}/generate_report.py"
    depends_on: [git-workflow]
```

### 执行命令

```bash
# 逐章执行（自动识别下一未完成章节）
python3 scripts/task-run.py workflows/my-project/workflow-full.yaml

# 仅检查不写入
python3 scripts/task-run.py workflows/my-project/workflow-full.yaml --vars DRY_RUN=true

# 指定章节
python3 scripts/task-run.py workflows/my-project/workflow-full.yaml --vars CHAPTER_NUM=5

# 开启远程推送
python3 scripts/task-run.py workflows/my-project/workflow-full.yaml \
  --vars GIT_AUTO_PUSH=true GIT_REMOTE=origin GIT_BRANCH=main

# 从指定步骤断点续跑
python3 scripts/task-run.py workflows/my-project/workflow-full.yaml --resume-from write-chapter
```

---

## 信息搜集与整理

脚本：`workflows/<project>/scripts/research.py`

### 功能

- 根据章节标题自动构建多维搜索词
- 优先使用 Tavily API，无 key 时降级为 DuckDuckGo（零依赖）
- 从已有章节提取写作上下文，避免重复
- 所有结果标注来源，生成章节时自动插入参考资料链接
- 输出结构化 `research-data.json` 供后续步骤使用

### 输出格式

```json
{
  "timestamp": "2026-03-06T04:08:01",
  "chapter": { "number": 3, "title": "Skills 插件体系" },
  "queries": ["OpenClaw Skills 插件体系", "SKILL.md 编写规范"],
  "results": [
    {
      "query": "OpenClaw Skills 插件体系",
      "source": "duckduckgo",
      "items": [{ "title": "...", "url": "...", "snippet": "..." }]
    }
  ],
  "references": [{ "title": "外部资料", "url": "https://..." }],
  "context_from_existing": "从已有章节摘录的关键信息..."
}
```

### 搜索引擎配置

```bash
# 高质量搜索（推荐，需 API Key）
export TAVILY_API_KEY=tvly-xxxxxxxxxxxxxxxx

# 不配置时自动使用 DuckDuckGo Lite（免费，无需注册）
# curl -sL "https://lite.duckduckgo.com/lite/?q=..."
```

---

## 大纲与章节管理

脚本：`workflows/<project>/scripts/manage_outline.py`

### 功能

- 解析项目中的 `OUTLINE.md`，建立章节清单
- 对比已存在的章节文件，识别完成/待写状态
- 为目标章节生成推荐节结构（基于关键词映射）
- 在 `outline-analysis.json` 中追加每次运行的历史记录

### OUTLINE.md 格式

```markdown
# 教程大纲

1. 基础介绍与安装
2. 部署与环境初始化
3. Skills 插件体系与批量开发
4. Skills 安装与管理实践
5. ClawHub 平台与技能分发
```

### 输出格式

```json
{
  "timestamp": "2026-03-06T04:08:01",
  "outline": [
    { "number": 1, "title": "基础介绍", "status": "completed", "file": "01-xxx.md" },
    { "number": 3, "title": "Skills 插件体系", "status": "pending", "file": null }
  ],
  "next_chapter": { "number": 3, "title": "Skills 插件体系" },
  "recommended_structure": ["概述", "目录结构", "SKILL.md 编写规范", "开发实战"],
  "history": [{ "date": "2026-03-06", "action": "analyzed", "target": 3 }]
}
```

### 大纲版本追踪

每次运行追加历史记录到 `history` 字段，形成完整的调整轨迹。修改
`OUTLINE.md` 后重新运行，差异会被自动记录。

---

## 内容撰写与文档生成

脚本：`workflows/<project>/scripts/write_chapter.py`

### 功能

- 基于 `CHAPTER_KNOWLEDGE` 知识库字典生成结构化内容
- 自动插入真实命令、配置示例、数据表格
- **消除 TODO 占位符**，每节均有具体的技术内容
- 保持与已有章节一致的 Markdown 风格
- 先输出草稿到 `drafts/`，仅当项目中**不存在**同名文件时才发布

### 章节写作规范

```
✅ 每节有引导段落（连贯叙述，非列表堆砌）
✅ 代码块标注语言（```bash / ```json / ```yaml）
✅ 表格标题行清晰，列对齐
✅ 有"本章小结"段落
✅ 末尾有"下一章"导航链接
```

### 知识库扩展

在 `write_chapter.py` 的 `CHAPTER_KNOWLEDGE` 字典中添加新章节：

```python
CHAPTER_KNOWLEDGE = {
    5: {
        "title": "ClawHub 平台与技能分发",
        "intro": "本章介绍 ClawHub 平台...",
        "sections": [
            {
                "title": "ClawHub 平台简介",
                "content": """真实的技术内容，包含可运行的示例：

```bash
clawdhub install tavily-search
npx skills find "automation"
```"""
            }
        ],
        "faq": [("如何注册 ClawHub 账号", "访问 https://skills.sh 使用 GitHub 账号登录")]
    }
}
```

### 草稿与人工审校协同

```
OUTPUT_DIR/drafts/
├── 03-Skills 插件体系.md     ← 机器生成草稿
└── 04-Skills 安装管理.md      ← 待人工审校

PROJECT_DIR/
├── 01-基础介绍.md             ← 人工编写（受保护）
├── 03-Skills 插件体系.md      ← 审校通过后发布
```

**保护逻辑**：项目目录中已存在的文件不会被覆盖，人工修改安全。

---

## Git 自动化与远程推送

脚本：`workflows/<project>/scripts/git_workflow.py`

### 功能清单

| 操作 | 说明 | 默认 |
|------|------|------|
| 初始化仓库 | `git init` + `.gitignore` + `core.quotepath=false` | 自动 |
| 检测变更 | 扫描新增/修改的 `.md` 文件 | 自动 |
| 生成 commit 信息 | 从文件名提取章节名，规范化格式 | 自动 |
| 安全提交 | 仅提交 `.md` 和 `.gitignore`（白名单） | 自动 |
| 远程推送 | 推送到配置的远程仓库和分支 | **关闭** |

### 配置变量

```yaml
variables:
  GIT_AUTO_COMMIT: "true"      # 是否自动提交
  GIT_AUTO_PUSH: "false"       # 是否推送到远端（默认关闭）
  GIT_REMOTE: "origin"         # 远程仓库别名
  GIT_BRANCH: "main"           # 目标分支
  GIT_REMOTE_URL: ""           # 远程 URL（首次配置时使用）
```

### 配置远程仓库

```bash
# 方式 1：提前手动配置（推荐）
cd /your/project
git remote add origin https://github.com/user/repo.git

# 方式 2：通过工作流变量自动添加
# 设置 GIT_REMOTE_URL，脚本自动执行:
# git remote add origin <GIT_REMOTE_URL>
```

### 开启自动推送

```bash
# 单次推送
python3 scripts/task-run.py workflows/my-project/workflow-full.yaml \
  --vars GIT_AUTO_COMMIT=true GIT_AUTO_PUSH=true

# 永久开启（修改 config.yaml 中的 GIT_AUTO_PUSH 为 "true"）
```

### 安全保障

```
✅ 仅提交 .md 和 .gitignore（白名单机制，不触及其他文件）
✅ push 前检查 remote 是否存在
✅ 不使用 --force（不强制覆盖远端历史）
✅ 推送失败仅记录警告，不影响整体流程
✅ 不提交未追踪的敏感文件（credentials/、logs/ 等）
✅ core.quotepath=false 正确处理中文文件名
```

### commit 信息格式

```
add: 新增章节 Skills 插件体系与批量开发, Skills 安装与管理实践 [2026-03-06 04:08]
```

### 输出格式

```json
{
  "status": "ok",
  "git_initialized": true,
  "committed": true,
  "commit_hash": "258a83c",
  "commit_message": "add: 新增章节 Skills 插件体系与批量开发 [2026-03-06 04:08]",
  "pushed": false,
  "push_skipped_reason": "GIT_AUTO_PUSH 未启用",
  "files_committed": ["03-Skills 插件体系与批量开发.md"]
}
```

---

## 安全与可控性

### 操作安全矩阵

| 场景 | 保护机制 |
|------|----------|
| 项目文件已存在 | `write_chapter.py` 自动跳过，不覆盖人工内容 |
| Git 提交范围 | 白名单：仅 `.md` + `.gitignore`，排除所有其他文件 |
| 远程推送 | 默认 **关闭**，需显式设置 `GIT_AUTO_PUSH=true` |
| 工作流执行 | `--dry-run` 仅验证不执行，`DRY_RUN=true` 环境变量全局生效 |
| 任务失败 | `on_failure: continue` 保证流程继续，错误完整记录在日志 |
| 敏感配置 | API Key 通过环境变量传入，不硬编码到工作流文件 |

### DRY_RUN 全局控制

```bash
# 所有脚本均响应 DRY_RUN 环境变量
python3 scripts/task-run.py workflow-full.yaml --vars DRY_RUN=true

# 效果：
# research.py        → 正常搜集，不写入文件
# write_chapter.py   → 生成草稿，不复制到项目目录
# git_workflow.py    → 检测变更，不执行 commit/push
# generate_report.py → 生成报告，不归档
```

### 断点恢复

```bash
# 从指定任务续跑（跳过已完成的前置任务）
python3 scripts/task-run.py workflow-full.yaml --resume-from write-chapter

# Git 层面回滚（恢复到上次提交状态）
git -C /path/to/project checkout HEAD -- .
```

### exec-approvals.json 集成

对需要系统级审批的命令，可与 `~/.openclaw/exec-approvals.json` 联动：

```json
{
  "autoApprove": ["python3", "git status", "git add", "git commit"],
  "requireApproval": ["git push"],
  "deny": ["rm -rf /"]
}
```

---

## 24/7 持续优化

本 Skill 支持通过 OpenClaw Cron 实现 **完全无人值守的 24 小时自动运行**，包括：

- 定时批量生成章节（全部完成后自动转为优化模式）
- **持续搜索网络最新信息并自动优化已有章节**
- 六维度多指标质量检测驱动优化优先级
- 每日健康检查与状态报告
- 飞书自动推送执行结果

### 架构概览

```
 OpenClaw Cron (jobs.json)
       │
       ├──── 每6小时 ────→ agentTurn: 执行 daemon.py --mode continuous
       │                      │
       │                      ├─ 1. health_check.py  (前置健康检查)
       │                      ├─ 2. batch_runner.py   (仅在有未完成章节时)
       │                      ├─ 3. web_researcher.py (搜索网络最新信息)
       │                      ├─ 4. optimize_chapter.py (智能优化章节)
       │                      │    ├─ 六维度质量评分选择优先章节
       │                      │    ├─ 提取新信息 → 合并到章节
       │                      │    └─ 自动 git commit + push
       │                      └─ 5. health_check.py  (后置健康检查)
       │                      └─ 3. health_check.py  (后置健康检查)
       │
       └──── 每日8AM ────→ agentTurn: 执行 daemon.py --mode health
                               │
                               └─ 生成 health-report.md → 飞书推送
```

### 核心组件

| 组件 | 文件 | 功能 |
|------|------|------|
| **调度入口** | `daemon.py` | 统一命令行入口，支持 full/batch/health/optimize/continuous/status 六种模式 |
| **批量生成** | `batch_runner.py` | 循环调用 workflow-full 生成多个章节，含状态持久化与断点恢复 |
| **网络研究** | `web_researcher.py` | Tavily + DuckDuckGo 双引擎搜索，13章定制化搜索关键词，每日缓存 |
| **智能优化** | `optimize_chapter.py` | 六维度质量评分选择优先章节，提取新信息合并，自动提交推送 |
| **质量检测** | `check_quality.py` | 六维度多指标评估（内容/结构/代码/可读性/教学/时效），A-F 分级 |
| **健康检查** | `health_check.py` | 进度追踪、异常预警、磁盘监控、可读 Markdown 报告 |
| **Cron 注册** | `cron/jobs.json` | OpenClaw 原生定时任务，agentTurn 模式触发 |

### daemon.py 运行模式

```bash
# continuous 模式（推荐）: 健康检查 → 批量生成(如需) → 网络搜索+优化 → 健康检查
python3 daemon.py --mode continuous --max-chapters 3

# full 模式: 健康检查 → 批量生成 → 健康检查
python3 daemon.py --mode full --max-chapters 3

# optimize 模式: 仅网络搜索 + 优化
python3 daemon.py --mode optimize --max-chapters 3

# batch 模式: 仅批量生成
python3 daemon.py --mode batch --max-chapters 5

# health 模式: 仅健康检查与报告
python3 daemon.py --mode health

# status 模式: 快速查看当前进度
python3 daemon.py --mode status

# 空运行模式（测试用）
python3 daemon.py --mode continuous --dry-run
```

### 批量生成参数

| 参数 | 环境变量 | 默认值 | 说明 |
|------|----------|--------|------|
| `--max-chapters` | `MAX_CHAPTERS_PER_RUN` | 3 | 每轮最多生成章节数 |
| `--cooldown` | `COOLDOWN_SECONDS` | 30 | 章节间冷却时间（秒） |
| `--dry-run` | `DRY_RUN` | false | 空运行模式 |
| - | `MAX_CONSECUTIVE_FAILURES` | 3 | 连续失败 N 次后停止本轮 |

### 健康检查内容

健康检查 (`health_check.py`) 自动检测：

- **项目进度**: 已完成/剩余章节数，百分比进度条
- **批量运行历史**: 总运行次数、成功/失败统计
- **异常预警**:
  - 🟡 超过 24 小时无新运行
  - 🔴 上次运行连续失败 ≥ 3 章
  - 🟡 累计失败超过 5 次
- **系统状态**: 磁盘空间、Python 版本、目录可用性

输出文件:
- `health-check.json` — 结构化检查结果
- `health-report.md` — 可读 Markdown 报告（适合飞书推送）

### 状态持久化

批量运行状态保存在 `batch-state.json`：

```json
{
  "created_at": "2026-03-06T10:00:00",
  "total_runs": 5,
  "last_run_at": "2026-03-06T22:00:00",
  "completed_chapters": [
    {"chapter": 5, "title": "...", "at": "2026-03-06T10:05:00"},
    {"chapter": 6, "title": "...", "at": "2026-03-06T10:10:00"}
  ],
  "failed_chapters": [],
  "runs": [
    {
      "run_id": 1,
      "timestamp": "2026-03-06T10:00:00",
      "chapters_attempted": [5, 6, 7],
      "chapters_succeeded": [5, 6, 7],
      "chapters_failed": [],
      "total_duration": 180.5
    }
  ]
}
```

### OpenClaw Cron 注册

已注册两个定时任务到 `~/.openclaw/cron/jobs.json`：

#### 1. 批量章节生成（每 4 小时）

```json
{
  "id": "3d0c64b3-f223-43ba-beca-ec1ad64b0ca0",
  "name": "教程自动化-批量章节生成",
  "schedule": {"kind": "cron", "expr": "0 */4 * * *", "tz": "Asia/Shanghai"},
  "sessionTarget": "isolated",
  "payload": {
    "kind": "agentTurn",
    "message": "执行 daemon.py --mode full --max-chapters 3 ..."
  },
  "delivery": {"mode": "announce", "channel": "feishu", "to": "chat:oc_..."}
}
```

#### 2. 每日健康报告（每天 8:00）

```json
{
  "id": "b1a966ae-67c6-4872-89b5-57706a829bd3",
  "name": "教程自动化-健康检查报告",
  "schedule": {"kind": "cron", "expr": "0 8 * * *", "tz": "Asia/Shanghai"},
  "sessionTarget": "isolated",
  "payload": {
    "kind": "agentTurn",
    "message": "执行 daemon.py --mode health ..."
  },
  "delivery": {"mode": "announce", "channel": "feishu", "to": "chat:oc_..."}
}
```

### 手动控制

```bash
# 启用/禁用 Cron 任务（修改 jobs.json 中 enabled 字段）
# enabled: true → 正常调度
# enabled: false → 暂停调度

# 手动触发一次批量生成
python3 daemon.py --mode full --max-chapters 5

# 手动触发健康检查
python3 daemon.py --mode health

# 查看当前进度
python3 daemon.py --mode status
```

### 自动停止策略

当所有 13 章全部生成完毕后：

1. `batch_runner.py` 检测到 `missing == 0`，输出 `"status": "all_complete"`
2. `daemon.py` full 模式检测到 `all_complete`，跳过批量生成
3. 健康检查报告显示 **100%** 完成
4. Cron 任务继续运行但不产生新内容（幂等安全）
5. 可手动将 `enabled` 设为 `false` 停止调度

---

## 六维度质量检测系统

脚本：`workflows/<project>/scripts/check_quality.py` (v2.0)

### 六大质量维度

| 维度 | 权重 | 评估内容 |
|------|------|----------|
| **内容充实度** (Content) | 25% | 字数、段落数、信息密度（结构化内容占比） |
| **结构完整性** (Structure) | 20% | 标题层级、小节数、H2/H3 分布、本章小结、标题重复 |
| **代码质量** (Code) | 15% | 代码块数量、语言标注率、代码长度、语言多样性 |
| **可读性** (Readability) | 15% | 段落长度、列表/表格使用、提示块、排版密度 |
| **教学价值** (Pedagogy) | 15% | FAQ、步骤化操作、外部链接、代码解释比例、下一章导航 |
| **时效性** (Freshness) | 10% | 修改时间、更新标记、内容新鲜度 |

### 评分等级

| 等级 | 分数范围 | 含义 |
|------|----------|------|
| A | ≥ 90 | 优秀，无需优化 |
| B | 80-89 | 良好，可微调 |
| C | 70-79 | 合格，应改进 |
| D | 60-69 | 较差，需要优化 |
| F | < 60 | 不合格，急需重写 |

### 使用方式

```bash
# 检查所有章节
python3 scripts/check_quality.py

# 检查指定章节，详细输出
python3 scripts/check_quality.py --chapter 5 --verbose

# 输出示例
#  🟢 01-基础介绍.md    91.0 (A)  736字  3问题
#  🔵 05-ClawHub.md     87.8 (B)  705字  5问题
```

### 输出文件

| 文件 | 说明 |
|------|------|
| `quality-report.json` | 完整六维度检测结果，包含每章详细评分 |
| `quality-report.md` | Markdown 格式报告，适合飞书推送 |
| `02-quality-check.json` | 兼容旧版接口的简化数据 |

### 与优化引擎联动

`optimize_chapter.py` 自动调用六维度质量评分来决定优化优先级：

1. **F/D 级** → 高优先级，立即优化
2. **C 级** → 中优先级，本轮可优化
3. **B 级** → 低优先级，微调
4. **A 级** → 跳过，资源留给低分章节
5. **单维度 < 60** → 额外加权，针对性补强

---

## 持续网络搜索优化

脚本：`workflows/<project>/scripts/web_researcher.py` + `optimize_chapter.py`

### 完整优化循环

```
网络搜索 (web_researcher.py)
    ↓ research-cache/ch01-2026-03-07.json
质量评估 (check_quality.py)
    ↓ quality-report.json (六维度)
选择章节 (optimize_chapter.py)
    ↓ 按优化评分排序，选 top-N
提取新信息 → 对比现有内容
    ↓ 识别缺失信息、过时内容
合并新内容 → 质量验证
    ↓ 插入"最新动态与补充"小节
Git 提交 + 推送
    ↓ optimize: 基于网络最新信息优化第 X 章
更新历史 → 设置冷却期
    ↓ optimize-history.json (12h 冷却)
```

### 搜索引擎策略

| 引擎 | 用途 | 优先级 |
|------|------|--------|
| **Tavily Search** | 主搜索引擎，高质量结果，支持 content extraction | 优先 |
| **DuckDuckGo Lite** | 备用引擎，零配置零依赖，免费 | 回退 |

每章配有 3 组定制化搜索关键词，覆盖技术概念、实操命令、最新动态。

### 优化引擎参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--max-chapters` | 3 | 每轮最多优化章节数 |
| `--dry-run` | false | 空运行，不实际修改 |
| `--chapter N` | 0(自动) | 指定章节优化 |
| `--all` | false | 优化所有章节 |
| `MIN_OPTIMIZE_INTERVAL_HOURS` | 12 | 同一章节冷却期 |

---

## 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                    Task Automator Engine                     │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │   Parser    │  │  Scheduler  │  │   Logger    │         │
│  │ (任务解析)   │  │  (任务调度)  │  │ (日志记录)   │         │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘         │
│         │                │                │                 │
│  ┌──────▼────────────────▼────────────────▼──────┐         │
│  │              Execution Engine                  │         │
│  │              (执行引擎)                         │         │
│  └──────┬────────────────┬────────────────┬──────┘         │
│         │                │                │                 │
│  ┌──────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐         │
│  │   Workers   │  │   Workers   │  │   Workers   │         │
│  │  (执行节点)  │  │  (执行节点)  │  │  (执行节点)  │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
├─────────────────────────────────────────────────────────────┤
│  Storage Layer: Tasks DB | Logs | State | Checkpoints      │
└─────────────────────────────────────────────────────────────┘
```

### 核心组件

| 组件 | 职责 |
|------|------|
| **Parser** | 解析任务配置，构建任务依赖图 |
| **Scheduler** | 根据依赖关系调度任务执行 |
| **Execution Engine** | 管理任务执行生命周期 |
| **Workers** | 实际执行任务的工作节点 |
| **Logger** | 记录执行日志和状态变更 |
| **State Manager** | 管理任务状态和检查点 |

---

## 任务模型

### 任务状态机

```
                    ┌──────────┐
                    │ PENDING  │
                    └────┬─────┘
                         │ schedule()
                    ┌────▼─────┐
             ┌──────┤ RUNNING  ├──────┐
             │      └────┬─────┘      │
             │           │            │
        fail()      success()    timeout()
             │           │            │
      ┌──────▼──────┐    │     ┌──────▼──────┐
      │   FAILED    │    │     │   TIMEOUT   │
      └──────┬──────┘    │     └──────┬──────┘
             │           │            │
        retry()          │       retry()
             │      ┌────▼─────┐      │
             └─────►│ COMPLETED├◄─────┘
                    └──────────┘
                         │
                    skip/cancel
                         │
                    ┌────▼─────┐
                    │ SKIPPED  │
                    └──────────┘
```

### 任务类型

| 类型 | 说明 | 示例 |
|------|------|------|
| `shell` | 执行 Shell 命令 | `ls -la` |
| `python` | 执行 Python 脚本 | `scripts/process.py` |
| `node` | 执行 Node.js 脚本 | `scripts/handler.js` |
| `http` | HTTP 请求 | GET/POST/PUT/DELETE |
| `webhook` | Webhook 触发 | 发送通知 |
| `skill` | 调用本地 OpenClaw Skill | `tavily-search`, `summarize` |
| `agent` | 调用 AI Agent | Claude/GPT 任务 |
| `composite` | 复合任务（包含子任务） | 嵌套工作流 |
| `conditional` | 条件任务 | if/else 逻辑 |

---

## Skill 任务类型

### 调用本地 Skills

`skill` 类型允许你在工作流中调用本地安装的 OpenClaw Skills：

```yaml
tasks:
  # 使用 tavily-search skill 进行网页搜索
  - id: search
    type: skill
    config:
      skill_name: "tavily-search"  # Skill 名称
      script: "search.mjs"          # 要执行的脚本
      args:                         # 传递给脚本的参数
        - "AI automation tools"
        - "-n"
        - "10"
    timeout: 60

  # 使用 summarize skill
  - id: summarize
    type: skill
    config:
      skill_name: "summarize"
      command: "summarize https://example.com --length short"
    depends_on:
      - search
```

### 管理本地 Skills

```bash
# 列出所有可用的 skills
python3 scripts/task-skills.py list

# 查看 skill 详情
python3 scripts/task-skills.py info tavily-search

# 检查 skill 依赖
python3 scripts/task-skills.py check summarize
```

### Skill 配置选项

| 选项 | 说明 |
|------|------|
| `skill_name` | **必填** - 要调用的 skill 名称 |
| `script` | 要执行的脚本文件名（在 skill 的 scripts 目录中查找） |
| `command` | 要执行的完整命令 |
| `args` | 传递给脚本/命令的参数列表 |

---

## 任务配置

### 完整配置示例

```yaml
# workflow.yaml - 完整的任务流配置
name: data-processing-pipeline
version: "1.0"
description: "数据处理流水线"

# 全局配置
config:
  # 执行配置
  execution:
    max_parallel: 5          # 最大并行数
    timeout: 3600            # 全局超时（秒）
    retry_policy:
      max_attempts: 3        # 最大重试次数
      backoff: exponential   # 退避策略：linear/exponential/fixed
      initial_delay: 5       # 初始延迟（秒）
      max_delay: 300         # 最大延迟（秒）
  
  # 调度配置
  schedule:
    type: cron               # once/cron/interval
    cron: "0 2 * * *"        # 每天凌晨2点
    timezone: "Asia/Shanghai"
  
  # 通知配置
  notifications:
    on_start: true
    on_complete: true
    on_failure: true
    channels:
      - type: webhook
        url: "https://hooks.example.com/notify"
      - type: email
        to: "admin@example.com"

# 变量定义
variables:
  data_dir: "/data/input"
  output_dir: "/data/output"
  api_endpoint: "https://api.example.com"

# 任务定义
tasks:
  # 任务1：数据获取
  - id: fetch-data
    name: "获取源数据"
    type: http
    config:
      method: GET
      url: "${api_endpoint}/data"
      headers:
        Authorization: "Bearer ${API_TOKEN}"
      output: "${data_dir}/raw.json"
    retry:
      max_attempts: 5
      delay: 10
    timeout: 300
    
  # 任务2：数据验证
  - id: validate-data
    name: "数据验证"
    type: python
    config:
      script: "scripts/validate.py"
      args:
        - "--input"
        - "${data_dir}/raw.json"
    depends_on:
      - fetch-data
    on_failure: abort  # abort/continue/skip_downstream
    
  # 任务3：并行处理（无依赖可并行）
  - id: process-batch-1
    name: "处理批次1"
    type: shell
    config:
      command: "python scripts/process.py --batch 1"
    depends_on:
      - validate-data
      
  - id: process-batch-2
    name: "处理批次2"
    type: shell
    config:
      command: "python scripts/process.py --batch 2"
    depends_on:
      - validate-data
      
  - id: process-batch-3
    name: "处理批次3"
    type: shell
    config:
      command: "python scripts/process.py --batch 3"
    depends_on:
      - validate-data
    
  # 任务4：合并结果
  - id: merge-results
    name: "合并处理结果"
    type: python
    config:
      script: "scripts/merge.py"
      args:
        - "--output"
        - "${output_dir}/final.json"
    depends_on:
      - process-batch-1
      - process-batch-2
      - process-batch-3
    
  # 任务5：条件分支
  - id: quality-check
    name: "质量检查"
    type: conditional
    config:
      condition: "{{ result.merge-results.record_count > 1000 }}"
      on_true:
        - id: full-analysis
          type: agent
          config:
            prompt: "对数据进行完整分析..."
      on_false:
        - id: quick-summary
          type: shell
          config:
            command: "python scripts/summary.py"
    depends_on:
      - merge-results
    
  # 任务6：通知完成
  - id: notify-complete
    name: "发送完成通知"
    type: webhook
    config:
      url: "https://hooks.slack.com/services/xxx"
      method: POST
      body:
        text: "数据处理完成: {{ result.merge-results.summary }}"
    depends_on:
      - quality-check
    on_failure: continue  # 通知失败不影响整体状态

# 钩子定义
hooks:
  pre_run:
    - type: shell
      command: "mkdir -p ${data_dir} ${output_dir}"
  post_run:
    - type: shell
      command: "rm -rf ${data_dir}/temp"
  on_failure:
    - type: webhook
      url: "https://hooks.example.com/alert"
```

### 依赖关系可视化

上述配置的依赖图：

```
fetch-data
    │
    ▼
validate-data
    │
    ├───────────┬───────────┐
    ▼           ▼           ▼
process-1   process-2   process-3
    │           │           │
    └───────────┴───────────┘
                │
                ▼
          merge-results
                │
                ▼
          quality-check
          ┌─────┴─────┐
          ▼           ▼
    full-analysis  quick-summary
          └─────┬─────┘
                ▼
          notify-complete
```

---

## 执行引擎

### 执行流程

```python
# 伪代码：执行引擎核心逻辑
class ExecutionEngine:
    def run(self, workflow):
        # 1. 解析配置，构建任务图
        task_graph = self.parser.parse(workflow)
        
        # 2. 拓扑排序，确定执行顺序
        execution_order = topological_sort(task_graph)
        
        # 3. 初始化执行上下文
        context = ExecutionContext(workflow.variables)
        
        # 4. 执行任务
        for level in execution_order:
            # 同一层级的任务可并行执行
            parallel_tasks = [t for t in level if self.can_run(t, context)]
            
            # 并行执行
            results = await asyncio.gather(*[
                self.execute_task(task, context)
                for task in parallel_tasks
            ])
            
            # 更新上下文
            for task, result in zip(parallel_tasks, results):
                context.set_result(task.id, result)
                
        # 5. 返回执行结果
        return context.get_summary()
```

### 并行执行策略

```yaml
# 并行配置选项
execution:
  # 策略1：固定并行数
  parallel_mode: fixed
  max_parallel: 5
  
  # 策略2：动态并行（根据资源）
  parallel_mode: dynamic
  resource_based:
    cpu_threshold: 80%
    memory_threshold: 70%
  
  # 策略3：分组并行
  parallel_mode: grouped
  groups:
    - name: io_tasks
      max_parallel: 10
    - name: cpu_tasks
      max_parallel: 2
```

---

## 日志系统

### 日志结构

```
.task-logs/
├── workflows/
│   └── {workflow-id}/
│       ├── run-{timestamp}.log      # 执行日志
│       ├── run-{timestamp}.json     # 结构化数据
│       └── checkpoints/
│           └── checkpoint-{task-id}.json
├── tasks/
│   └── {task-id}/
│       ├── stdout.log
│       ├── stderr.log
│       └── metrics.json
└── summary/
    ├── daily.json
    └── weekly.json
```

### 日志级别

| 级别 | 用途 |
|------|------|
| `DEBUG` | 详细调试信息 |
| `INFO` | 一般执行信息 |
| `WARN` | 警告（可继续执行） |
| `ERROR` | 错误（任务失败） |
| `FATAL` | 致命错误（流程终止） |

### 日志示例

```json
{
  "timestamp": "2026-03-06T10:30:45.123Z",
  "workflow_id": "data-processing-pipeline",
  "run_id": "run-20260306-103000",
  "task_id": "fetch-data",
  "level": "INFO",
  "message": "Task started",
  "context": {
    "attempt": 1,
    "max_attempts": 3,
    "timeout": 300
  },
  "metrics": {
    "start_time": "2026-03-06T10:30:45.123Z",
    "memory_mb": 128,
    "cpu_percent": 25
  }
}
```

### 执行追踪

```bash
# 查看执行历史
task-history my-workflow

# 输出：
┌──────────────────────────────────────────────────────────────┐
│ Workflow: data-processing-pipeline                           │
├──────────────────────────────────────────────────────────────┤
│ Run ID          │ Status    │ Started          │ Duration   │
├──────────────────────────────────────────────────────────────┤
│ run-20260306-10 │ ✓ Success │ 2026-03-06 10:30│ 5m 23s     │
│ run-20260305-22 │ ✗ Failed  │ 2026-03-05 22:00│ 2m 15s     │
│ run-20260305-10 │ ✓ Success │ 2026-03-05 10:00│ 6m 02s     │
└──────────────────────────────────────────────────────────────┘

# 查看特定执行详情
task-detail run-20260305-22

# 输出：
┌──────────────────────────────────────────────────────────────┐
│ Run: run-20260305-22                                         │
├──────────────────────────────────────────────────────────────┤
│ Task            │ Status    │ Duration  │ Attempts │ Error   │
├──────────────────────────────────────────────────────────────┤
│ fetch-data      │ ✓ Success │ 30s       │ 1        │ -       │
│ validate-data   │ ✓ Success │ 5s        │ 1        │ -       │
│ process-batch-1 │ ✓ Success │ 45s       │ 1        │ -       │
│ process-batch-2 │ ✗ Failed  │ 60s       │ 3        │ OOM     │
│ process-batch-3 │ ○ Skipped │ -         │ -        │ -       │
│ merge-results   │ ○ Skipped │ -         │ -        │ -       │
└──────────────────────────────────────────────────────────────┘
```

---

## 失败处理

### 重试机制

```yaml
# 任务级别的重试配置
tasks:
  - id: api-call
    type: http
    retry:
      max_attempts: 5
      backoff: exponential
      initial_delay: 5
      max_delay: 300
      retry_on:
        - timeout
        - connection_error
        - status_code: [500, 502, 503, 504]
      no_retry_on:
        - status_code: [400, 401, 403, 404]
```

### 退避策略

| 策略 | 延迟计算 | 适用场景 |
|------|----------|----------|
| `fixed` | 固定延迟 | 简单场景 |
| `linear` | `delay * attempt` | 线性增长 |
| `exponential` | `delay * 2^(attempt-1)` | API 限流 |
| `random` | `random(delay, delay*2)` | 避免惊群 |

### 失败处理策略

```yaml
# 任务失败时的处理策略
tasks:
  - id: critical-task
    on_failure: abort        # 终止整个流程
    
  - id: optional-task
    on_failure: continue     # 继续执行其他任务
    
  - id: dependent-task
    on_failure: skip_downstream  # 跳过下游任务
    
  - id: fallback-task
    on_failure:
      action: fallback
      fallback_task: alternative-task  # 执行降级任务
```

### 断点恢复

```bash
# 从最后失败的任务继续执行
task-resume run-20260305-22

# 从指定任务开始执行
task-resume run-20260305-22 --from process-batch-2

# 跳过失败的任务继续
task-resume run-20260305-22 --skip process-batch-2
```

---

## 调度机制

### 调度类型

| 类型 | 说明 | 示例 |
|------|------|------|
| `once` | 一次性执行 | 手动触发 |
| `cron` | Cron 表达式 | `0 2 * * *` |
| `interval` | 固定间隔 | 每 5 分钟 |
| `event` | 事件触发 | 文件变化、Webhook |

### Cron 配置

```yaml
schedule:
  type: cron
  cron: "0 2 * * *"      # 每天凌晨2点
  timezone: "Asia/Shanghai"
  
  # 高级选项
  catch_up: false        # 是否补执行错过的
  max_concurrent: 1      # 最大并发执行数
  start_date: "2026-03-01"
  end_date: "2026-12-31"
```

### 事件触发

```yaml
schedule:
  type: event
  triggers:
    # 文件变化触发
    - type: file_watcher
      path: "/data/input"
      patterns: ["*.csv", "*.json"]
      events: [created, modified]
      debounce: 60  # 防抖时间（秒）
    
    # Webhook 触发
    - type: webhook
      endpoint: "/trigger/my-workflow"
      auth:
        type: bearer
        token_env: "WEBHOOK_TOKEN"
    
    # 依赖其他工作流
    - type: workflow
      workflow_id: "upstream-workflow"
      on_status: [completed]
```

---

## 扩展开发

### 自定义任务类型

```python
# scripts/custom_tasks/my_task.py
from task_automator import BaseTask, TaskResult

class MyCustomTask(BaseTask):
    """自定义任务类型"""
    
    task_type = "my_custom"
    
    def validate_config(self, config):
        """验证配置"""
        required_fields = ["param1", "param2"]
        for field in required_fields:
            if field not in config:
                raise ValueError(f"Missing required field: {field}")
    
    def execute(self, context):
        """执行任务"""
        config = self.config
        
        # 获取上游任务结果
        upstream_result = context.get_result("upstream-task")
        
        try:
            # 执行自定义逻辑
            result = self.do_something(
                param1=config["param1"],
                param2=config["param2"],
                input_data=upstream_result
            )
            
            return TaskResult(
                status="success",
                output=result,
                metrics={"processed_count": len(result)}
            )
            
        except Exception as e:
            return TaskResult(
                status="failed",
                error=str(e),
                retryable=True
            )
    
    def do_something(self, param1, param2, input_data):
        """实际业务逻辑"""
        # ... 实现
        pass

# 注册自定义任务
# 在 config/custom_tasks.yaml 中添加
# custom_tasks:
#   - module: scripts.custom_tasks.my_task
#     class: MyCustomTask
```

### 自定义钩子

```python
# scripts/hooks/my_hook.py
from task_automator import BaseHook

class SlackNotificationHook(BaseHook):
    """Slack 通知钩子"""
    
    hook_type = "slack_notify"
    
    def on_workflow_start(self, workflow, context):
        """工作流开始时触发"""
        self.send_slack(f"🚀 工作流 {workflow.name} 开始执行")
    
    def on_workflow_complete(self, workflow, context, result):
        """工作流完成时触发"""
        status = "✅" if result.success else "❌"
        self.send_slack(f"{status} 工作流 {workflow.name} 执行完成")
    
    def on_task_failure(self, task, context, error):
        """任务失败时触发"""
        self.send_slack(f"⚠️ 任务 {task.id} 失败: {error}")
    
    def send_slack(self, message):
        """发送 Slack 消息"""
        import requests
        requests.post(
            self.config["webhook_url"],
            json={"text": message}
        )
```

### 插件系统

```yaml
# 使用插件
plugins:
  - name: slack-notifier
    source: clawdhub://slack-notifier
    config:
      webhook_url: "${SLACK_WEBHOOK}"
  
  - name: prometheus-metrics
    source: local://scripts/plugins/prometheus.py
    config:
      push_gateway: "http://prometheus:9091"
```

---

## 最佳实践

### 任务设计原则

1. **原子性**：每个任务应该是独立的、可重试的
2. **幂等性**：多次执行应产生相同结果
3. **超时设置**：总是为任务设置合理的超时
4. **日志记录**：任务内部应有足够的日志
5. **资源清理**：使用钩子清理临时资源

### 依赖管理

```yaml
# 好的做法：明确的依赖关系
tasks:
  - id: A
  - id: B
    depends_on: [A]
  - id: C
    depends_on: [A]
  - id: D
    depends_on: [B, C]

# 避免：循环依赖（会被检测并报错）
# A -> B -> C -> A  ❌
```

### 错误处理

```yaml
# 为关键任务设置完善的错误处理
tasks:
  - id: critical-api-call
    type: http
    retry:
      max_attempts: 5
      backoff: exponential
    timeout: 60
    on_failure:
      action: fallback
      fallback_task: use-cached-data
    alerts:
      - type: webhook
        on: [failure, timeout]
        url: "${ALERT_WEBHOOK}"
```

### 性能优化

```yaml
# 1. 合理设置并行度
execution:
  max_parallel: 5  # 根据资源调整

# 2. 使用条件跳过
tasks:
  - id: expensive-task
    condition: "{{ needs_full_processing }}"
    
# 3. 增量处理
tasks:
  - id: process-data
    config:
      mode: incremental
      last_checkpoint: "${LAST_PROCESSED_ID}"
```

---

## API 参考

### 命令行工具

```bash
# 执行工作流
task-run <workflow.yaml> [options]
  --dry-run          # 仅验证，不执行
  --vars key=value   # 覆盖变量
  --parallel N       # 设置并行数
  --timeout N        # 设置超时
  --verbose          # 详细输出

# 查看状态
task-status <run-id>

# 查看历史
task-history <workflow-name> [--limit N]

# 查看详情
task-detail <run-id>

# 恢复执行
task-resume <run-id> [--from <task-id>] [--skip <task-id>]

# 取消执行
task-cancel <run-id>

# 调度管理
task-schedule list
task-schedule enable <workflow>
task-schedule disable <workflow>
task-schedule next <workflow>  # 下次执行时间
```

### 配置模板

```bash
# 创建新工作流
task-init <name>

# 验证配置
task-validate <workflow.yaml>

# 可视化依赖图
task-graph <workflow.yaml>
```

---

## 安装与配置

### OpenClaw 工作区结构

```
~/.openclaw/workspace/skills/complex-task-automator/
├── SKILL.md                        # 本文件
├── _meta.json                      # 安装元数据
├── scripts/
│   ├── task-run.py                 # 主入口：执行工作流
│   ├── task-skills.py              # Skill 管理工具
│   └── core/
│       ├── engine.py               # 执行引擎（拓扑排序、并行调度）
│       ├── models.py               # 数据模型（Task, Workflow, TaskStatus）
│       ├── logger.py               # 日志系统
│       ├── scheduler.py            # Cron/事件调度器
│       └── skill_executor.py       # Skill 类型任务执行器
├── templates/
│   ├── basic.yaml                  # 基础工作流模板
│   ├── data-pipeline.yaml          # 数据处理模板
│   └── doc-automation.yaml         # 文档自动化模板 (新增)
├── examples/
│   ├── simple-workflow.yaml
│   ├── parallel-processing.yaml
│   └── skill-integration.yaml
└── workflows/
    └── <your-project>/             # 项目专属工作流目录
        ├── workflow.yaml           # 基础健康检查流程
        ├── workflow-full.yaml      # 完整文档生成流程（含 health-check 阶段）
        ├── workflow-batch.yaml     # 24/7 批量调度工作流（供 Cron 调用）
        ├── config.yaml             # 参数配置
        └── scripts/
            ├── daemon.py           # 24/7 调度入口 (full/batch/health/status)
            ├── batch_runner.py     # 批量章节生成（循环 workflow-full）
            ├── health_check.py     # 健康检查与状态报告
            ├── check_env.py        # 环境检查
            ├── check_quality.py    # 文档质量评分（0-100）
            ├── check_dependencies.py # 链接与引用检查
            ├── analyze_progress.py  # 进度分析与建议
            ├── research.py         # 信息搜集（Tavily/DDG 降级）
            ├── manage_outline.py   # 大纲解析、推荐结构、历史追踪
            ├── write_chapter.py    # 章节内容生成（知识库驱动，零占位符）
            ├── git_workflow.py     # Git 提交与远程推送（白名单安全）
            └── generate_report.py  # 综合 Markdown 报告生成
```

### 首次使用

1. 复制模板：`cp templates/basic.yaml my-workflow.yaml`
2. 编辑配置：根据需求修改任务定义
3. 验证配置：`task-validate my-workflow.yaml`
4. 执行测试：`task-run my-workflow.yaml --dry-run`
5. 正式执行：`task-run my-workflow.yaml`

---

## 版本历史

### v2.1.0 (2026-03-07)
- **新增** 24/7 自动调度：OpenClaw Cron 定时触发批量章节生成
- **新增** `daemon.py`：统一调度入口，支持 full/batch/health/status 四种模式
- **新增** `batch_runner.py`：批量章节生成器，循环调用 workflow-full，状态持久化与断点恢复
- **新增** `health_check.py`：健康检查与状态报告，异常预警，Markdown 格式飞书推送
- **新增** `workflow-batch.yaml`：专为 Cron 调度设计的轻量批量工作流
- **新增** Cron 任务注册：每 4 小时批量生成 + 每日 8AM 健康报告
- **改进** `workflow-full.yaml`：新增 health-check 任务阶段，schedule 从 once 升级为 cron
- **改进** 通知阶段增加进度百分比与预警数显示

### v2.0.0 (2026-03-06)
- **新增** 文档自动化全链路工作流（信息搜集 → 大纲 → 撰写 → Git 推送）
- **新增** `research.py`：多引擎搜索（Tavily 优先 / DuckDuckGo 自动降级）
- **新增** `manage_outline.py`：大纲解析、推荐节结构、历史版本追踪
- **新增** `write_chapter.py` v2：知识库驱动的章节生成，零 TODO 占位符，内容质量 80-90 分
- **新增** `git_workflow.py`：安全 Git 提交（白名单）+ 可选远程推送（默认关闭）
- **新增** `generate_report.py`：综合 Markdown 报告，含进度条、质量评分、Git 状态
- **新增** `check_quality.py`：0-100 分质量评分，检测字数/代码块/标题/表格
- **新增** 安全控制：DRY_RUN 全局模式、文件保护（已存在不覆盖）、exec-approvals 集成
- **新增** `--resume-from <task-id>` 断点续跑支持
- **改进** Git 支持 `core.quotepath=false` 正确处理中文文件名
- **改进** 工作流支持 `GIT_AUTO_PUSH` / `GIT_REMOTE` / `GIT_BRANCH` 变量配置

### v1.0.0 (2026-03-06)
- 初始版本
- 支持任务拆解与依赖管理
- 支持并行执行
- 支持失败重试
- 完整的日志系统
- Cron 调度支持
- 断点恢复功能

---

## 许可证

MIT License

---

## 贡献

欢迎提交 Issue 和 PR！

---

*Made with ❤️ for OpenClaw*
```
