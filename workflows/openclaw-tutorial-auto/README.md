# 📚 OpenClaw 自动优化系统 v5.2

<div align="center">

**统一自动化优化系统** — 教程文档 + 代码质量 · 双模式流水线 + 自动修复 + AI 精炼 + 插件 + 交互式 CLI

[![Pipeline](https://img.shields.io/badge/教程-14_阶段-blue.svg)]() [![Code](https://img.shields.io/badge/代码-5_阶段-green.svg)]() [![Plugins](https://img.shields.io/badge/插件-11_hooks-orange.svg)]() [![CLI](https://img.shields.io/badge/CLI-15_命令-purple.svg)]()

</div>

---

## 架构

```
openclaw-tutorial-auto/
├── auto_optimizer.py        # 统一入口（自动检测 tutorial/code/both）
├── pipeline.py              # 教程流水线编排器（14 阶段）
├── code_pipeline.py         # 代码流水线编排器（5 阶段）
├── base_pipeline.py         # 流水线基类（共享 run/banner/报告/插件）
├── cli.py                   # 交互式 CLI（15 命令, Tab 补全）
├── plugin_loader.py         # 插件热加载系统（discover/load/unload/reload）
├── scoring_engine.py        # YAML 评分规则引擎（20+ 内建检查）
├── task_queue.py            # 优先级任务队列（多线程 + 持久化）
├── config.yaml              # 全局配置
├── workflow-pipeline.yaml   # OpenClaw 工作流 v5.2
├── openclaw.sh              # 统一命令行入口脚本
├── run-optimize.sh          # Cron 定时调度脚本
│
├── modules/                 # 功能模块
│   ├── compat.py                # 兼容层: 统一 utils 导入 (消除 13 处重复)
│   ├── types.py                 # 类型定义: 17 个 TypedDict (全模块类型标注)
│   ├── diff_scanner.py          # 增量扫描: git diff 变更检测
│   ├── notifier.py              # 通知: 飞书/企微/钉钉/Slack/Webhook 多渠道
│   ├── ai_refiner.py            # AI 精炼: OpenClaw agent 驱动的智能优化
│   ├── tutorial_scanner.py      # 教程扫描: 章节元数据、结构、缺陷 (代码块感知)
│   ├── quality_analyzer.py      # 教程分析: 深度质量分析、优化计划
│   ├── tutorial_refiner.py      # 教程精炼: 增量修复（12 种操作）
│   ├── reference_collector.py   # 教程采集: 权威参考来源 (默认启用 Web 搜索)
│   ├── formatter.py             # 教程格式化: 统一 Markdown 风格 (优化评分权重)
│   ├── link_checker.py          # 链接检查 + 自动修复: 3 策略断链修复
│   ├── consistency_checker.py   # 一致性检查 + 自动修复: 术语/URL 规范化
│   ├── readability_analyzer.py  # 教程可读性: 段落密度/句长分析
│   ├── optimization_tracker.py  # 教程追踪: 优化历史记录
│   ├── readme_generator.py      # README 自动生成器
│   ├── code_scanner.py          # 代码扫描: 8 语言深度分析、五维度评分
│   ├── code_analyzer.py         # 代码分析: 31 种模板、优先级建议
│   ├── code_refiner.py          # 代码修复: docstring/imports/whitespace
│   └── suggestion_enricher.py   # 引用增强: 静态引用 + Web 搜索
│
├── plugins/                 # 插件目录
│   └── score_highlighter.py     # 示例: 低分告警标记 (after_scan hook)
│
├── scoring-rules/           # 评分规则 (YAML)
│   └── default.yaml             # 默认 6 维度评分规则
│
├── dashboard/               # 可视化 Dashboard
│   ├── server.py                # HTTP API 服务器 (端口 8686)
│   └── index.html               # ECharts 前端 (质量分布/趋势/缺陷)
│
├── prompts/                 # AI 提示词（模块化）
│   ├── scan_prompt.md           # 扫描阶段提示
│   ├── analyze_prompt.md        # 分析阶段提示
│   ├── refine_prompt.md         # 精炼阶段提示
│   ├── format_prompt.md         # 格式化提示
│   ├── reference_prompt.md      # 参考搜集提示
│   ├── chapter_template.md      # 章节模板
│   ├── discover_prompt.md       # 目录发现提示
│   └── readme_prompt.md         # README 生成提示
│
├── templates/               # 输出模板
├── utils/                   # 共享工具 (config/git_ops/markdown)
├── scripts/                 # 活跃脚本 (utils/daemon/feishu/health_check 等)
├── _archive/                # 归档遗留文件 (旧 workflow/scripts)
└── .task-logs/              # 运行日志
```

## 流水线阶段

### 教程模式 (14 阶段)
```
discover → scan → analyze → collect_refs → check_links → check_consistency →
check_readability → fix_issues → refine → format → track → update_readme → git → report
```

| # | 阶段 | 模块 | 说明 |
|---|------|------|------|
| 1 | **discover** | pipeline 内置 | 递归扫描教程目录，区分根目录/子目录文件，生成完整文件清单 |
| 2 | **scan** | `tutorial_scanner` | 扫描全部章节，提取元数据、结构、缺陷列表、六维度质量评分（代码块感知） |
| 3 | **analyze** | `quality_analyzer` | 深度分析每章质量，生成优先级排序的优化计划 |
| 4 | **collect_refs** | `reference_collector` | 按章节主题匹配权威参考来源（默认启用 Web 搜索） |
| 5 | **check_links** | `link_checker` | 内部/外部链接健康检查，生成断链报告 |
| 6 | **check_consistency** | `consistency_checker` | 术语、格式、URL 一致性检查 |
| 7 | **check_readability** | `readability_analyzer` | 段落密度、句长、可读性分析 |
| 8 | **fix_issues** | `link_checker` + `consistency_checker` | 自动修复断链（3 策略）+ 术语/URL 规范化（保护代码块） |
| 9 | **refine** | `tutorial_refiner` | 增量修复（导航、目录、标题、代码标签、FAQ、摘要等），处理所有文档 |
| 10 | **format** | `formatter` | 统一 Markdown 格式（优化评分权重） |
| 11 | **track** | `optimization_tracker` | 记录优化历史 |
| 12 | **update_readme** | `readme_generator` | 所有文档优化后自动生成/更新 README |
| 13 | **git** | `utils/git_ops` | 安全提交 + 推送 |
| 14 | **report** | pipeline 内置 | 生成结构化优化报告 (pipeline-report.md) |

### 代码模式 (5 阶段)
```
scan → analyze → enrich → refine → report
```

| # | 阶段 | 模块 | 说明 |
|---|------|------|------|
| 1 | **scan** | `code_scanner` | 8 语言深度分析 (Python/JS/TS/Go/Shell/Rust/C/C++/Java)，五维度评分 |
| 2 | **analyze** | `code_analyzer` | 生成优先级优化建议（31 种模板），覆盖 8 语言族 |
| 3 | **enrich** | `suggestion_enricher` | 为建议附加最佳实践参考链接（静态引用 + Web 搜索） |
| 4 | **refine** | `code_refiner` | 自动修复 (docstring/doxygen/javadoc/imports/header_guard 等) |
| 5 | **report** | code_pipeline 内置 | 生成 Markdown + HTML 双格式报告，含引用和分数表 |

### v5.2 数据流

```
discover-report.json ──→ scan-report.json ──→ analysis-report.json
                                                      │
    ┌─────────────────────────────────────────────────┘
    ↓
references.json ──→ link-check-report.json ──→ consistency-report.json
                                                      │
    ┌─────────────────────────────────────────────────┘
    ↓
readability-report.json ──→ fix-issues-report.json ──→ refine-result.json
                            (断链修复 + 术语规范化)
    ┌─────────────────────────────────────────────────┘
    ↓
format-result.json ──→ optimization-trends.json ──→ README.md
                                                      │
    ┌─────────────────────────────────────────────────┘
    ↓
git commit + push ──→ pipeline-report.md
```

## 使用方式

### Shell 脚本入口（推荐）

```bash
# 统一入口
./openclaw.sh tutorial --dry-run           # 教程流水线干跑
./openclaw.sh tutorial                     # 教程正式优化
./openclaw.sh code /path/to/project        # 代码分析
./openclaw.sh both --dry-run               # 双流水线干跑
./openclaw.sh auto                         # 自动检测模式
./openclaw.sh help                         # 查看帮助
```

### 交互式 CLI

```bash
python3 cli.py                    # 进入交互模式
python3 cli.py --dry-run          # 干跑模式
python3 cli.py scan               # 直接执行扫描
python3 cli.py discover           # 目录发现
python3 cli.py status             # 查看最近状态
```

交互模式下可用命令（支持 Tab 自动补全）：

| 命令 | 说明 |
|------|------|
| `scan [--max N]` | 扫描教程仓库 |
| `analyze` | 质量分析 |
| `refine [chapter_num]` | 精炼指定/全部章节 |
| `format` | 格式化 |
| `code <dir>` | 代码扫描 |
| `run [stages...]` | 运行指定/全流程 |
| `status` | 最近扫描摘要 |
| `chapters` | 列出所有章节及评分 |
| `diff [--since N]` | 增量扫描 |
| `dashboard` | 启动 Dashboard |
| `queue` | 查看任务队列 |
| `submit <type>` | 提交异步任务 |
| `plugins` | 查看/管理插件 |
| `score <file>` | 使用评分引擎评分 |
| `discover` | 目录发现 |

### Python 直接调用

```bash
# 自动检测
python3 auto_optimizer.py --mode auto --dry-run

# 教程模式
python3 auto_optimizer.py --mode tutorial --dry-run
python3 auto_optimizer.py --mode tutorial --max-chapters 5
python3 auto_optimizer.py --mode tutorial --no-web-search     # 禁用 Web 搜索

# 代码模式
python3 auto_optimizer.py --mode code /path/to/project --dry-run
python3 code_pipeline.py /path/to/project --ext .py .js

# 双模式
python3 auto_optimizer.py --mode both --dry-run

# 运行到指定阶段
python3 pipeline.py --dry-run --stage check_links   # 仅运行到链接检查

# 增量 diff
python3 auto_optimizer.py --diff --since HEAD~5
python3 auto_optimizer.py --diff --staged --dry-run
```

### AI 精炼 (OpenClaw Agent)
```bash
python3 auto_optimizer.py --mode tutorial --ai-refine
python3 auto_optimizer.py --ai-refine --ai-thinking high
python3 -m modules.ai_refiner --mode tutorial --file ch01.md --dry-run
```

### Dashboard 可视化
```bash
python3 -m dashboard.server                # http://localhost:8686
python3 cli.py dashboard                   # 通过 CLI 启动
```

### Cron 定时调度
```bash
# 使用 run-optimize.sh (自动防重入、日志轮转、飞书通知)
./run-optimize.sh

# 或配置 cron/jobs.json
{
  "schedule": "0 */4 * * *",
  "workflow": "openclaw-tutorial-auto/workflow-pipeline.yaml"
}
```

## v5.2 自动修复能力

### 断链修复 (fix_issues → link_checker.auto_fix_internal)

3 策略级联修复内部断链：

| 策略 | 说明 | 示例 |
|------|------|------|
| **精确匹配** | 去除路径前缀后匹配 | `../ch1/intro.md` → `01-intro.md` |
| **章节号匹配** | 从链接中提取章节编号 | `chapter-01.md` → `01-intro.md` |
| **模糊匹配** | 归一化后相似度匹配 | `quick_start.md` → `02-quick-start.md` |

### 一致性修复 (fix_issues → consistency_checker.auto_fix)

自动规范化术语和 URL（保护代码块和行内代码）：

| 类型 | 规则 | 示例 |
|------|------|------|
| **术语** | OpenClaw 统一大小写 | `open claw` / `Open Claw` → `OpenClaw` |
| **术语** | 文件名统一 | `skill.md` / `Skill.md` → `SKILL.md` |
| **URL** | GitHub 链接规范化 | 多种变体 → `https://github.com/user/repo` |
| **URL** | 文档站点统一 | `docs.openclaw.io` 等变体统一 |

## 质量评分体系

### 教程评分 (六维度, 0-100)

| 维度 | 权重 | 检查项 |
|------|------|--------|
| 内容深度 | 25 | 字数 ≥ 1200 / 段落完整性 |
| 结构完整性 | 20 | 必要段落、标题层级、导航链接 |
| 代码质量 | 15 | 代码块数量 + 语言标签覆盖率 |
| 教学价值 | 15 | FAQ、摘要、渐进式结构 |
| 参考来源 | 10 | 外部链接数量 |
| 可读性 | 15 | 段落密度、CJK 间距 |

### 代码评分 (五维度, 0-100)

| 维度 | 权重 | 检查项 |
|------|------|--------|
| 结构 | 20 | 函数/类组织、模块化程度 |
| 文档 | 20 | docstring 覆盖率、注释质量 |
| 复杂度 | 20 | McCabe 复杂度、函数长度 |
| 风格 | 20 | 命名规范、空白、一致性 |
| 实践 | 20 | 类型提示、main guard、异常处理 |

### 等级划分
| 等级 | 分数 |
|------|------|
| A | ≥ 90 |
| B | ≥ 75 |
| C | ≥ 60 |
| D | ≥ 40 |
| F | < 40 |

## 插件系统

插件放置在 `plugins/` 目录，自动发现和加载。

### 插件结构

```python
# plugins/my_plugin.py
PLUGIN_META = {
    "name": "my_plugin",
    "version": "1.0.0",
    "hooks": ["after_scan", "on_pipeline_end"],
    "priority": 50,
}

def after_scan(data, **ctx):
    return data  # 可修改后返回

def on_pipeline_end(data, **ctx):
    return data
```

### 可用 Hooks (11 种)

| Hook | 触发时机 | data 内容 |
|------|---------|----------|
| `on_pipeline_start` | 流水线启动 | `None` |
| `after_scan` | 扫描完成 | 扫描结果 dict |
| `before_analyze` / `after_analyze` | 分析前后 | 分析结果 |
| `before_refine` / `after_refine` | 精炼前后 | 精炼结果 |
| `before_format` / `after_format` | 格式化前后 | 格式化结果 |
| `on_report` | 生成报告时 | 报告 dict |
| `on_error` | 发生错误时 | 错误信息 |
| `on_pipeline_end` | 流水线完成 | 最终报告 |

## 评分规则引擎

通过 YAML 自定义评分维度、规则权重与等级划分。

```yaml
# scoring-rules/default.yaml
dimensions:
  content_depth:
    weight: 25
    rules:
      - check: word_count_min
        params: { min: 1200 }
        score: 10
        penalty: -15
grades:
  S: 95
  A: 85
  B: 75
  C: 60
  D: 40
  F: 0
```

### 内建检查函数 (20+)

`word_count_min/max` | `line_count_min` | `has_code_blocks` | `has_labeled_code` | `heading_hierarchy` | `has_toc` | `has_nav` | `has_section` | `min_h2_sections` | `has_images` | `has_tables` | `has_links` | `defect_count_max` | `defect_severity_max` | `has_cli_examples` | `has_blockquotes` | `regex_match` | `function_count_min` | `class_count_min`

## 任务队列

```python
from task_queue import TaskQueue, Task
tq = TaskQueue(workers=2)
tq.start()
tid = tq.submit(Task(task_type="tutorial", params={"stages": ["scan"]}))
tq.wait()
tq.stop()
```

## 与旧系统的对比

| 特性 | v1 (scripts/) | v3.0 (modules/) | v5.0 | v5.1 | v5.2 (当前) |
|------|--------------|-----------------|------|------|-------------|
| 架构 | 16 个扁平脚本 | 5 模块 + 编排器 | 12 模块 + 双流水线 | 17 模块 + BasePipeline | 20 模块 + 自动修复 |
| 模式 | 仅教程 | 仅教程 | 教程 + 代码 | + 交互 CLI | + 自动修复 + 代码块感知 |
| 流水线 | 无 | 7 阶段 | 教程 11 / 代码 4 | 教程 11 / 代码 5 | **教程 14** / 代码 5 |
| 质量评分 | 自评膨胀 (96-99) | 六维度 (0-100) | 六维度 + 五维度 | YAML 规则引擎 | + 代码块感知评分 |
| 自动修复 | 无 | 无 | 格式修复 | 格式修复 | **断链 + 术语 + URL** |
| 代码分析 | 无 | 无 | 8 语言深度分析 | + 20+ 自动检查 | 同上 |
| 插件 | 无 | 无 | 无 | 热加载 + 11 hooks | 同上 |
| 任务调度 | 无 | 无 | 无 | 优先队列 + 多线程 | 同上 |
| CLI | 无 | 无 | argparse | 交互式 REPL | + discover 命令 |
| Web 搜索 | 无 | 无 | 手动启用 | 手动启用 | **默认启用** |

## 配置

所有配置集中在 `config.yaml`，支持环境变量覆盖。关键配置项：

```yaml
# 教程配置
project_dir: /root/.openclaw/workspace/zxk-private/openclaw-tutorial-auto
quality:
  pass_score: 75
  weights: { content_depth: 25, structure: 20, code_quality: 15, pedagogy: 15, references: 10, readability: 15 }

# 目录发现
discover:
  extra_dirs: [docs, tutorial, guides, chapters]
  exclude_dirs: [node_modules, __pycache__, .git, _archive]

# README 自动生成
readme:
  auto_update: true
  include_quality_stats: true
  include_learning_path: true

# 代码配置
code:
  default_extensions: [.py, .js, .ts, .sh, .go, .rs, .c, .h, .cpp, .java]
  quality: { pass_score: 75 }
  refine:
    auto_fix: { docstrings: true, imports: true, trailing_whitespace: true }
```

---

## 📖 文档导航

| 文档 | 说明 |
|------|------|
| [docs/API.md](docs/API.md) | 全模块 API 参考 |
| [docs/CLI-GUIDE.md](docs/CLI-GUIDE.md) | CLI 交互手册 (15 命令详解) |
| [docs/PLUGIN-GUIDE.md](docs/PLUGIN-GUIDE.md) | 插件开发指南 (Hooks/示例/最佳实践) |
| [../../SKILL.md](../../SKILL.md) | 完整功能文档 |
| [../../assets/TASK_GUIDE.md](../../assets/TASK_GUIDE.md) | 使用指南 |
