# 📚 OpenClaw 自动优化系统 v5.1

> 统一自动化优化系统：教程文档 + 代码质量，双模式流水线 + AI 精炼 + 插件 + 交互式 CLI。

## 架构

```
openclaw-tutorial-auto/
├── auto_optimizer.py        # 统一入口（自动检测 tutorial/code/both）
├── pipeline.py              # 教程流水线编排器（11 阶段）
├── code_pipeline.py         # 代码流水线编排器（5 阶段）
├── base_pipeline.py         # 流水线基类（共享 run/banner/报告/插件）
├── cli.py                   # 交互式 CLI（15 命令, Tab 补全）
├── plugin_loader.py         # 插件热加载系统（discover/load/unload/reload）
├── scoring_engine.py        # YAML 评分规则引擎（20+ 内建检查）
├── task_queue.py            # 优先级任务队列（多线程 + 持久化）
├── config.yaml              # 全局配置
├── workflow-pipeline.yaml   # OpenClaw 工作流 v5.0
│
├── modules/                 # 功能模块
│   ├── compat.py                # 兼容层: 统一 utils 导入 (消除 13 处重复)
│   ├── types.py                 # 类型定义: 17 个 TypedDict (全模块类型标注)
│   ├── diff_scanner.py          # 增量扫描: git diff 变更检测
│   ├── notifier.py              # 通知: 飞书/企微/钉钉/Slack/Webhook 多渠道
│   ├── ai_refiner.py            # AI 精炼: OpenClaw agent 驱动的智能优化
│   ├── tutorial_scanner.py      # 教程扫描: 章节元数据、结构、缺陷
│   ├── quality_analyzer.py      # 教程分析: 深度质量分析、优化计划
│   ├── tutorial_refiner.py      # 教程精炼: 增量修复（12 种操作）
│   ├── reference_collector.py   # 教程采集: 权威参考来源
│   ├── formatter.py             # 教程格式化: 统一 Markdown 风格
│   ├── link_checker.py          # 教程链接: 内部/外部链接健康检查
│   ├── consistency_checker.py   # 教程一致性: 术语/格式一致检查
│   ├── readability_analyzer.py  # 教程可读性: 段落密度/句长分析
│   ├── optimization_tracker.py  # 教程追踪: 优化历史记录
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
├── templates/               # 输出模板
├── utils/                   # 共享工具 (config/git_ops/markdown)
├── scripts/                 # 活跃脚本 (utils/daemon/feishu/health_check 等)
├── _archive/                # 归档遗留文件 (旧 workflow/scripts)
└── .task-logs/              # 运行日志
```

## 流水线阶段

### 教程模式 (11 阶段)
```
scan → analyze → collect_refs → check_links → check_consistency →
check_readability → refine → format → track → git → report
```

| 阶段 | 模块 | 说明 |
|------|------|------|
| **scan** | `tutorial_scanner` | 扫描全部章节，提取元数据、结构、缺陷列表、质量评分 |
| **analyze** | `quality_analyzer` | 深度分析每章质量，生成优先级排序的优化计划 |
| **collect_refs** | `reference_collector` | 按章节主题匹配权威参考来源 |
| **check_links** | `link_checker` | 内部/外部链接健康检查，自动修复断链 |
| **check_consistency** | `consistency_checker` | 术语、格式、风格一致性检查 |
| **check_readability** | `readability_analyzer` | 段落密度、句长、可读性分析 |
| **refine** | `tutorial_refiner` | 增量修复（导航、目录、标题、代码标签、FAQ、摘要等） |
| **format** | `formatter` | 统一 Markdown 格式 |
| **track** | `optimization_tracker` | 记录优化历史 |
| **git** | `utils/git_ops` | 安全提交 + 推送 |
| **report** | pipeline 内置 | 生成结构化优化报告 |

### 代码模式 (5 阶段)
```
scan → analyze → enrich → refine → report
```

| 阶段 | 模块 | 说明 |
|------|------|------|
| **scan** | `code_scanner` | 8 语言深度分析 (Python/JS/TS/Go/Shell/Rust/C/C++/Java)，五维度评分 |
| **analyze** | `code_analyzer` | 生成优先级优化建议（31 种模板），覆盖 8 语言族 |
| **enrich** | `suggestion_enricher` | 为建议附加最佳实践参考链接（静态引用 + Web 搜索） |
| **refine** | `code_refiner` | 自动修复 (docstring/doxygen/javadoc/imports/header_guard 等) |
| **report** | code_pipeline 内置 | 生成 Markdown + HTML 双格式报告，含引用和分数表 |

## 使用方式

### 交互式 CLI（推荐）

```bash
python3 cli.py                    # 进入交互模式
python3 cli.py --dry-run          # 干跑模式
python3 cli.py scan               # 直接执行扫描
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

### 自动检测模式
```bash
python3 auto_optimizer.py                            # 自动检测 tutorial/code
python3 auto_optimizer.py --mode auto --dry-run      # 自动检测 + 干跑
```

### 教程模式
```bash
python3 auto_optimizer.py --mode tutorial --dry-run
python3 auto_optimizer.py --mode tutorial --max-chapters 5
python3 pipeline.py --dry-run                        # 直接调用教程流水线
```

### 代码模式
```bash
python3 auto_optimizer.py --mode code /path/to/project --dry-run
python3 code_pipeline.py /path/to/project --dry-run  # 直接调用代码流水线
python3 code_pipeline.py /path --ext .py .js          # 仅指定扩展名
```

### 双模式 (教程 + 代码)
```bash
python3 auto_optimizer.py --mode both --dry-run
```

### 增量 diff 模式
```bash
python3 auto_optimizer.py --diff --since HEAD~5         # 分析最近 5 次提交变更
python3 auto_optimizer.py --diff --since 2026-03-01     # 从指定日期
python3 auto_optimizer.py --diff --staged --dry-run     # 仅暂存区
```

### AI 精炼 (OpenClaw Agent)
```bash
python3 auto_optimizer.py --mode tutorial --ai-refine   # Pipeline + AI 精炼
python3 auto_optimizer.py --ai-refine --ai-thinking high # 高思考级别
python3 -m modules.ai_refiner --mode tutorial --file ch01.md --dry-run  # 单文件
python3 -m modules.ai_refiner --mode code --file app.py               # 代码精炼
python3 -m modules.ai_refiner --mode suggest --report analysis.json   # 智能建议
```

### Dashboard 可视化
```bash
python3 -m dashboard.server                             # 启动 http://localhost:8686
python3 -m dashboard.server --port 9090                 # 自定义端口
python3 cli.py dashboard                                # 通过 CLI 启动
```

### 通知
```bash
python3 -m modules.notifier --title "测试" --body "Hello" --level success
python3 -m modules.notifier --channel feishu wecom      # 指定渠道
```

### 任务队列
```bash
# 通过 CLI 交互
python3 cli.py
> submit tutorial --dry-run    # 提交教程扫描任务
> submit code                  # 提交代码扫描任务
> queue                        # 查看队列状态

# 编程方式
from task_queue import TaskQueue, Task
tq = TaskQueue(workers=2)
tq.start()
tid = tq.submit(Task(task_type="tutorial", params={"stages": ["scan"]}))
tq.wait()
print(tq.get_status(tid))
tq.stop()
```

### 评分引擎
```bash
# 对扫描报告评分
python3 cli.py score /tmp/openclaw-tutorial-auto-reports/scan-report.json

# 使用自定义规则
python3 cli.py score report.json --rules my-rules.yaml

# 编程方式
from scoring_engine import ScoringEngine
engine = ScoringEngine()
engine.load_default()  # 或 engine.load_rules("my-rules.yaml")
result = engine.evaluate(chapter_data)
print(f"{result.grade}: {result.total:.1f}")
```

### 通过 OpenClaw Workflow
```bash
openclaw workflow run workflow-pipeline.yaml
```

### Cron 调度
在 `cron/jobs.json` 中配置：
```json
{
  "id": "tutorial-optimize",
  "schedule": "0 3 * * *",
  "workflow": "openclaw-tutorial-auto/workflow-pipeline.yaml"
}
```

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
    "description": "自定义插件描述",
    "hooks": ["after_scan", "on_pipeline_end"],
    "priority": 50,  # 越小优先级越高
}

def after_scan(data, **ctx):
    """after_scan hook: 扫描完成后处理数据。"""
    # data 为前一阶段输出，可修改后返回
    return data

def on_pipeline_end(data, **ctx):
    """on_pipeline_end hook: 流水线结束时触发。"""
    return data
```

### 可用 Hooks

| Hook | 触发时机 | data 内容 |
|------|---------|----------|
| `on_pipeline_start` | 流水线启动 | `None` |
| `after_scan` | 扫描阶段完成 | 扫描结果 dict |
| `before_analyze` / `after_analyze` | 分析前后 | 分析结果 |
| `before_refine` / `after_refine` | 精炼前后 | 精炼结果 |
| `before_format` / `after_format` | 格式化前后 | 格式化结果 |
| `on_report` | 生成报告时 | 报告 dict |
| `on_error` | 发生错误时 | 错误信息 |
| `on_pipeline_end` | 流水线完成 | 最终报告 |

### 管理命令

```bash
python3 cli.py plugins                     # 列出已加载插件
```

```python
from plugin_loader import get_plugin_manager
pm = get_plugin_manager()
pm.load_all()                              # 加载所有插件
pm.unload("my_plugin")                     # 卸载指定插件
pm.reload("my_plugin")                     # 热重载
pm.trigger("after_scan", scan_data)        # 手动触发 hook
```

## 评分规则引擎

可通过 YAML 自定义评分维度、规则权重与等级划分。

### 规则文件结构 (scoring-rules/default.yaml)

```yaml
dimensions:
  content_depth:
    weight: 25
    rules:
      - check: word_count_min
        params: { min: 1200 }
        score: 10
        penalty: -15
      - check: has_code_blocks
        params: { min: 2 }
        score: 8

grades:
  S: 95
  A: 85
  B: 75
  C: 60
  D: 40
  F: 0
```

### 内建检查函数 (20+)

| 检查 | 说明 |
|------|------|
| `word_count_min/max` | 字数范围 |
| `line_count_min` | 最小行数 |
| `has_code_blocks` | 代码块数量 |
| `has_labeled_code` | 带语言标签的代码块 |
| `heading_hierarchy` | 标题层级正确性 |
| `has_toc` / `has_nav` | 目录/导航 |
| `has_section` | 包含指定章节 |
| `min_h2_sections` | 最少二级标题数 |
| `has_images` / `has_tables` / `has_links` | 多媒体元素 |
| `defect_count_max` / `defect_severity_max` | 缺陷约束 |
| `has_cli_examples` / `has_blockquotes` | CLI 示例/引用块 |
| `regex_match` | 自定义正则匹配 |
| `function_count_min` / `class_count_min` | 代码结构 |

支持通过 `register_check()` 注册自定义检查函数。

## 任务队列

多线程异步任务执行，支持优先级调度和持久化。

```python
from task_queue import TaskQueue, Task

tq = TaskQueue(workers=2, persist_file=".queue.json")
tq.start()

# 提交任务 (priority 越小越先执行)
tid1 = tq.submit(Task(task_type="tutorial", params={"stages": ["scan"]}, priority=1))
tid2 = tq.submit(Task(task_type="code", params={"project_dir": "/app"}, priority=5))

# 自定义任务类型
tq.register_executor("lint", lambda task: {"ok": True})
tid3 = tq.submit(Task(task_type="lint"))

# 等待完成
tq.wait(timeout=120)
print(tq.stats())  # {'total': 3, 'by_status': {'done': 3}}

tq.stop()
```

特性：
- **优先级队列**: priority 1-10，越小越优先
- **多线程**: 可配置 worker 数量
- **超时保护**: 单任务超时自动标记失败
- **任务持久化**: JSON 文件自动保存/恢复
- **状态追踪**: pending → running → done/failed/cancelled/timeout

## 与旧系统的对比

| 特性 | v1 (scripts/) | v3.0 (modules/) | v5.0 | v5.1 (当前) |
|------|--------------|-----------------|------|-------------|
| 架构 | 16 个扁平脚本 | 5 模块 + 编排器 | 12 模块 + 双流水线 | 17 模块 + BasePipeline + 插件 |
| 模式 | 仅教程 | 仅教程 | 教程 + 代码 | 教程 + 代码 + 交互 CLI |
| 流水线 | 无 | 7 阶段 | 教程 11 / 代码 4 | 教程 11 / 代码 5 + 队列 |
| 质量评分 | 自评膨胀 (96-99) | 六维度 (0-100) | 六维度教程 + 五维度代码 | YAML 规则引擎 (S/A/B/C/D/F) |
| 代码分析 | 无 | 无 | 8 语言深度分析 | 8 语言 + 20+ 自动检查 |
| 插件 | 无 | 无 | 无 | 热加载 + 11 种 hooks |
| 任务调度 | 无 | 无 | 无 | 优先队列 + 多线程 |
| CLI | 无 | 无 | argparse | 交互式 REPL + Tab 补全 |
| 类型安全 | 无 | 无 | 无 | 17 TypedDict + 注解 |
| 可测试性 | 无 | 支持 dry-run | 全链路 dry-run | dry-run + E2E 验证 |

## 配置

所有配置集中在 `config.yaml`，支持环境变量覆盖：

```yaml
# 教程配置
project_dir: /root/.openclaw/workspace/zxk-private/openclaw-tutorial-auto
quality:
  pass_score: 75
  weights: { content_depth: 25, structure: 20, ... }

# 代码配置
code:
  default_extensions: [.py, .js, .ts, .sh, .go, .rs, .c, .h, .cpp, .java]
  quality:
    pass_score: 75
    weights: { structure: 20, documentation: 20, complexity: 20, style: 20, practices: 20 }
  refine:
    auto_fix: { docstrings: true, imports: true, trailing_whitespace: true, main_guard: true }
```
