# 📚 OpenClaw 自动优化系统 v5.0

> 统一自动化优化系统：教程文档 + 代码质量，双模式流水线。

## 架构

```
openclaw-tutorial-auto/
├── auto_optimizer.py        # 统一入口（自动检测 tutorial/code/both）
├── pipeline.py              # 教程流水线编排器（11 阶段）
├── code_pipeline.py         # 代码流水线编排器（5 阶段）
├── config.yaml              # 全局配置
├── workflow-pipeline.yaml   # OpenClaw 工作流 v5.0
│
├── modules/                 # 功能模块
│   ├── tutorial_scanner.py      # 教程扫描: 章节元数据、结构、缺陷
│   ├── quality_analyzer.py      # 教程分析: 深度质量分析、优化计划
│   ├── tutorial_refiner.py      # 教程精炼: 增量修复（12 种操作）
│   ├── reference_collector.py   # 教程采集: 权威参考来源
│   ├── formatter.py             # 教程格式化: 统一 Markdown 风格
│   ├── link_checker.py          # 教程链接: 内部/外部链接健康检查
│   ├── consistency_checker.py   # 教程一致性: 术语/格式一致检查
│   ├── readability_analyzer.py  # 教程可读性: 段落密度/句长分析
│   ├── optimization_tracker.py  # 教程追踪: 优化历史记录
│   ├── code_scanner.py          # 代码扫描: 8 语言深度分析、五维度评分、缺陷检测
│   ├── code_analyzer.py         # 代码分析: 31 种模板、优先级建议、引用元数据
│   ├── code_refiner.py          # 代码修复: docstring/imports/whitespace/doxygen/javadoc
│   └── suggestion_enricher.py   # 引用增强: 静态引用 + Web搜索最佳实践
│
├── prompts/                 # AI 提示词（模块化）
├── templates/               # 输出模板
├── utils/                   # 共享工具
├── scripts/                 # 遗留脚本（向下兼容）
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
| **collect_refs** | `reference_collector` | 按章节主题匹配权威参考来源数据库 |
| **refine** | `tutorial_refiner` | 按优先级对章节执行增量修复（导航、目录、标题、代码标签、FAQ、摘要、参考链接、中英文间距、密集段落拆分） |
| **format** | `formatter` | 统一全仓 Markdown 格式（反引号、标题间距、空行、尾部空格、CJK 间距、链接格式） |
| **git** | `utils/git_ops` | 安全提交 + 推送（白名单模式） |
| **report** | pipeline 内置 | 生成结构化优化报告 |

## 使用方式

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

## 与旧系统的对比

| 特性 | v1 (scripts/) | v3.0 (modules/) | v5.0 (当前) |
|------|--------------|-----------------|-------------|
| 架构 | 16 个扁平脚本 | 5 模块 + 编排器 | 12 模块 + 双流水线 |
| 模式 | 仅教程 | 仅教程 | 教程 + 代码 |
| 流水线 | 无 | 7 阶段 | 教程 11 / 代码 4 |
| 质量评分 | 自评膨胀 (96-99) | 六维度 (0-100) | 六维度教程 + 五维度代码 |
| 代码分析 | 无 | 无 | 8 语言深度分析 (Python/JS/TS/Go/Shell/Rust/C/C++/Java) |
| 优化建议 | 无 | 无 | 31 种模板 + 权威引用 (Web搜索增强) |
| 自动修复 | 无 | 教程格式修复 | 教程 + 代码 (docstring/doxygen/javadoc/header_guard) |
| 进度报告 | 13/13 (实际 21 章) | 真实 21/21 | Markdown + HTML 双格式报告 |
| 配置 | 分散各处 | 统一 yaml | 统一 yaml + 代码配置 |
| 可测试性 | 无 | 支持 dry-run | 全链路 dry-run |

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
