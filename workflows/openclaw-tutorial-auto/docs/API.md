# 📖 API 参考

> OpenClaw 自动优化系统 v5.1 — 模块 API 文档

---

## 目录

- [核心流水线](#核心流水线)
  - [BasePipeline](#basepipeline)
  - [Pipeline](#pipeline)
  - [CodePipeline](#codepipeline)
- [扩展系统](#扩展系统)
  - [PluginManager](#pluginmanager)
  - [ScoringEngine](#scoringengine)
  - [TaskQueue](#taskqueue)
- [功能模块](#功能模块)
  - [compat](#compat)
  - [types](#types)
  - [tutorial_scanner](#tutorial_scanner)
  - [quality_analyzer](#quality_analyzer)
  - [tutorial_refiner](#tutorial_refiner)
  - [diff_scanner](#diff_scanner)
  - [notifier](#notifier)
  - [ai_refiner](#ai_refiner)
  - [code_scanner](#code_scanner)
  - [code_refiner](#code_refiner)
- [CLI](#cli)

---

## 核心流水线

### BasePipeline

**模块**: `base_pipeline.py`

流水线基类，提供共享的运行循环、Banner 输出、错误处理和插件集成。

```python
class BasePipeline:
    STAGES: list[str]           # 子类必须定义
    CRITICAL_STAGES: tuple      # 关键阶段 (失败即终止)
    PIPELINE_NAME: str          # 显示名称
    VERSION: str                # 版本号
    ICON: str                   # 图标
```

#### `__init__(dry_run, stages, plugins, **kwargs)`

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `dry_run` | `bool` | `False` | 干跑模式 |
| `stages` | `list[str]` | `None` | 要执行的阶段列表 (None=全部) |
| `plugins` | `bool` | `True` | 是否启用插件 |

#### `run() → dict`

执行流水线，返回结果字典：
```python
{
    "status": "success" | "partial" | "failed",
    "stages_ok": 10,
    "stages_fail": 1,
    "results": {"scan": {...}, "analyze": {...}, ...}
}
```

#### `results: dict`

各阶段执行结果，key 为阶段名。

---

### Pipeline

**模块**: `pipeline.py`  
**继承**: `BasePipeline`

教程优化流水线，11 个阶段。

```python
Pipeline(
    dry_run=False,
    stages=None,          # 默认全部 11 阶段
    max_chapters=None,    # 限制章节数
    plugins=True,
)
```

**阶段**: `scan → analyze → collect_refs → check_links → check_consistency → check_readability → refine → format → track → git → report`

---

### CodePipeline

**模块**: `code_pipeline.py`  
**继承**: `BasePipeline`

代码优化流水线，5 个阶段。

```python
CodePipeline(
    project_dir=None,     # 目标项目路径
    dry_run=False,
    stages=None,          # 默认全部 5 阶段
    extensions=None,      # 文件扩展名列表
    plugins=True,
)
```

**阶段**: `scan → analyze → enrich → refine → report`

---

## 扩展系统

### PluginManager

**模块**: `plugin_loader.py`

插件热加载管理器。单例模式，通过 `get_plugin_manager()` 获取。

```python
from plugin_loader import get_plugin_manager

pm = get_plugin_manager()
```

#### 方法

| 方法 | 参数 | 返回 | 说明 |
|------|------|------|------|
| `load_all(plugin_dir?)` | `str \| None` | `int` | 加载目录下所有插件，返回数量 |
| `load(path)` | `str` | `PluginInfo` | 加载单个插件文件 |
| `unload(name)` | `str` | `bool` | 卸载插件 |
| `reload(name)` | `str` | `PluginInfo` | 热重载插件 |
| `trigger(hook, data, **ctx)` | `str, Any, **Any` | `Any` | 触发 hook，pipe 模式传递 data |
| `list_plugins()` | - | `list[dict]` | 返回所有插件信息 |
| `get(name)` | `str` | `PluginInfo \| None` | 按名称获取插件 |

#### PluginInfo

```python
@dataclass
class PluginInfo:
    name: str
    version: str
    description: str
    hooks: list[str]
    priority: int        # 越小优先级越高 (默认 50)
    path: str
    module: ModuleType
    enabled: bool
```

#### VALID_HOOKS

```python
VALID_HOOKS = {
    "after_scan", "before_analyze", "after_analyze",
    "before_refine", "after_refine", "before_format", "after_format",
    "on_report", "on_error", "on_pipeline_start", "on_pipeline_end",
}
```

---

### ScoringEngine

**模块**: `scoring_engine.py`

YAML 可配置评分规则引擎。

```python
from scoring_engine import ScoringEngine, score, get_engine

# 方式一: 工厂函数
engine = get_engine()

# 方式二: 手动创建
engine = ScoringEngine()
engine.load_rules("scoring-rules/default.yaml")  # 或 engine.load_default()

# 方式三: 便捷函数
result = score(chapter_data)
```

#### `evaluate(data: dict) → ScoreResult`

对数据进行评分。

```python
result = engine.evaluate(chapter_data)
print(result.total)    # float: 总分 (0-100)
print(result.grade)    # str: 等级 (S/A/B/C/D/F)
print(result.dims)     # list[DimensionScore]: 维度得分
```

#### ScoreResult

```python
@dataclass
class ScoreResult:
    total: float          # 总分
    grade: str            # S/A/B/C/D/F
    dims: list[DimensionScore]
    bonuses: int          # 加分项数
    penalties: int        # 罚分项数
```

#### DimensionScore

```python
@dataclass
class DimensionScore:
    name: str             # 维度名
    weight: int           # 权重
    raw: float            # 原始分
    weighted: float       # 加权分
    rules: list[RuleResult]
```

#### `register_check(name, func)`

注册自定义检查函数：

```python
def my_check(data: dict, **params) -> bool:
    return data.get("custom_field", 0) > params.get("min", 0)

engine.register_check("my_check", my_check)
```

---

### TaskQueue

**模块**: `task_queue.py`

多线程优先级任务队列。

```python
from task_queue import TaskQueue, Task

tq = TaskQueue(workers=2, persist_file=".queue.json")
```

#### 方法

| 方法 | 参数 | 返回 | 说明 |
|------|------|------|------|
| `start()` | - | - | 启动工作线程 |
| `stop(wait?)` | `bool=True` | - | 停止队列 |
| `submit(task)` | `Task` | `str` | 提交任务，返回 task_id |
| `cancel(task_id)` | `str` | `bool` | 取消待执行任务 |
| `wait(timeout?)` | `float=None` | - | 等待所有任务完成 |
| `get_status(task_id)` | `str` | `dict \| None` | 查询任务状态 |
| `stats()` | - | `dict` | 统计信息 |
| `register_executor(type, func)` | `str, Callable` | - | 注册自定义执行器 |
| `persist()` | - | - | 手动持久化 |
| `restore()` | - | `int` | 从文件恢复任务 |

#### Task

```python
@dataclass
class Task:
    task_type: str        # "tutorial" | "code" | 自定义
    params: dict = {}     # 传递给执行器的参数
    priority: int = 5     # 1-10, 越小越优先
    timeout: float = 0    # 超时秒数 (0=无限)
```

#### TaskStatus

```
pending → running → done | failed | cancelled | timeout
```

---

## 功能模块

### compat

**模块**: `modules/compat.py`

统一兼容层，消除跨模块重复导入。

```python
from modules.compat import (
    setup_logger,      # 创建 logger
    cfg,               # 读取配置项: cfg("quality.pass_score", 75)
    load_config,       # 读取完整 config.yaml
    load_json,         # 安全加载 JSON 文件
    save_json,         # 保存 JSON 文件
    word_count,        # 中英文字数统计
    parse_outline,     # 解析教程目录结构
    find_completed_chapters,  # 查找已完成章节
    read_chapter,      # 读取章节内容
    run_git,           # 执行 git 命令
    get_project_dir,   # 获取项目目录
    get_output_dir,    # 获取输出目录
    progress_bar,      # 进度条
    read_file_safe,    # 安全读取文件 (处理编码错误)
    PROJECT_DIR,       # 教程项目路径 (常量)
    OUTPUT_DIR,        # 输出目录 (常量)
    DRY_RUN,           # 全局 dry-run 标志 (常量)
)
```

### types

**模块**: `modules/types.py`

17 个 TypedDict 类型定义：

| 类型 | 用途 |
|------|------|
| `ChapterScanResult` | 教程扫描结果 |
| `ChapterAnalysis` | 质量分析结果 |
| `RefineResult` | 精炼结果 |
| `CodeFileScanResult` | 代码文件扫描结果 |
| `CodeRefineResult` | 代码修复结果 |
| `CodeScoreDetail` | 代码评分详情 |
| `CodeImprovement` | 代码优化建议 |
| `HeadingDetail` | 标题结构详情 |
| `ScoreDetail` | 评分明细 |
| `Defect` | 缺陷定义 |
| `H2SectionSummary` | H2 章节摘要 |
| `StructureInfo` | 结构信息 |
| `ContentInfo` | 内容信息 |
| `Improvement` | 优化项 |
| `StageResult` | 阶段结果 |
| `PipelineResult` | 流水线结果 |
| `DiffResult` | 增量扫描结果 |
| `NotifyResult` | 通知结果 |
| `AIRefineResult` | AI 精炼结果 |

### tutorial_scanner

**模块**: `modules/tutorial_scanner.py`

```python
from modules.tutorial_scanner import scan_chapter

result: ChapterScanResult = scan_chapter(chapter_path, project_dir)
# result = {
#     "number": 1, "title": "...", "word_count": 1500,
#     "quality_score": 78.5, "grade": "B",
#     "defects": [...], "score_detail": {...},
#     "headings": [...], "structure": {...},
# }
```

### quality_analyzer

**模块**: `modules/quality_analyzer.py`

```python
from modules.quality_analyzer import analyze_chapter

analysis: ChapterAnalysis = analyze_chapter(scan_result)
# analysis = {
#     "priority": "high", "improvements": [...],
#     "estimated_effort": "30min",
# }
```

### tutorial_refiner

**模块**: `modules/tutorial_refiner.py`

```python
from modules.tutorial_refiner import refine_chapter

result: RefineResult = refine_chapter(chapter_path, analysis, dry_run=True)
# 支持 12 种自动修复操作
```

### diff_scanner

**模块**: `modules/diff_scanner.py`

```python
from modules.diff_scanner import scan_diff

result = scan_diff(since="HEAD~5", staged=False)
# result = {
#     "total_changed": 3,
#     "files": [{"file": "ch01.md", "status": "M", "additions": 20, "deletions": 5}],
# }
```

### notifier

**模块**: `modules/notifier.py`

```python
from modules.notifier import send_notification

result = send_notification(
    title="优化完成",
    body="21 章节已扫描",
    level="success",        # success | warning | error | info
    channels=["feishu"],    # feishu | wecom | dingtalk | slack | webhook
)
```

### ai_refiner

**模块**: `modules/ai_refiner.py`

```python
from modules.ai_refiner import ai_refine

result = ai_refine(
    mode="tutorial",        # tutorial | code | suggest
    file_path="ch01.md",
    thinking="high",        # low | medium | high
    dry_run=True,
)
```

### code_scanner

**模块**: `modules/code_scanner.py`

```python
from modules.code_scanner import scan_file

result: CodeFileScanResult = scan_file(file_path)
# 支持: .py, .js, .ts, .go, .sh, .rs, .c, .h, .cpp, .java
```

### code_refiner

**模块**: `modules/code_refiner.py`

```python
from modules.code_refiner import refine_file

result: CodeRefineResult = refine_file(file_path, suggestions, dry_run=True)
# 自动修复: docstring, imports, whitespace, header_guard, main_guard
```

---

## CLI

**模块**: `cli.py`

```python
from cli import InteractiveCLI

cli = InteractiveCLI(dry_run=True)
cli.run()                  # 进入交互循环
cli.cmd_scan(["--max", "5"])  # 编程方式调用命令
cli.cmd_status([])
```

所有 `cmd_*` 方法均接受 `args: list[str]` 参数，与命令行参数一致。
