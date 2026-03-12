# Changelog

All notable changes to the `complex-task-automator` skill are documented here.

---

## [5.5.0] — 2026-03-12

### Added
- **LLM 扩写分析** (`llm_expand` 阶段): 自动识别短段落/缺失维度，生成结构化扩写 Prompt (`modules/llm_expander.py`)
- **多语言 i18n 系统** (`modules/i18n.py`): zh-CN / en 双语消息目录，`set_locale()` / `t()` API，支持插件注册额外消息
- **HTML 可视化报告** (`html_report` 阶段): 静态 HTML + ECharts 5 图表 — 得分柱状图、分数区间饼图、维度雷达图、字数分布图
- `--language` CLI 参数: 控制报告和日志的输出语言 (`zh-CN` / `en`)
- Pipeline 升级至 16 阶段 (新增 `llm_expand` + `html_report`)

### Changed
- PIPELINE_VERSION 5.4 → 5.5
- STAGES 从 14 个增至 16 个
- SKILL.md 同步更新特性表和描述

## [5.4.0] — 2026-03-12

### Added
- **智能精炼阈值** (`--refine-threshold N`): 跳过分数 ≥N 的章节，节省 API 调用
- **章节评分仪表板**: 报告新增进度条 + 分数分布 + 等级可视化
- `--refine-threshold` CLI 参数透传 (auto_optimizer → Pipeline)

### Fixed
- Scanner: FAQ/Summary/References 正则支持章节编号 (如 `## 1.7 常见问题`)
- Scanner: 行级代码块解析替代正则，修复嵌套 `` ` `` `` ` `` `` ` `` 误匹配

## [5.3.0] — 2026-03-12

### Added
- **并行阶段执行**: 4 个 check 阶段 (collect_refs, check_links, check_consistency, check_readability) 使用 ThreadPoolExecutor 并发执行
- **锚点模糊匹配自动修复**: difflib SequenceMatcher + 子串加权，阈值 0.55
- **增量检测模式** (`--incremental`): mtime+size 缓存，仅处理变更文件
- `before_*` Hook 触发 (28 种 Hook 覆盖全部 14 阶段)
- discover 阶段记录文件 mtime

### Changed
- STAGES 重排: fix_issues 移至 refine 之后（防止 refine 覆盖修复）
- VALID_HOOKS 从 11 扩展到 28 个
- Track 阶段优化: 无精炼修改时跳过二次扫描

### Fixed
- Consistency checker: 移除 `openclaw config set/edit` 假阳别名
- Consistency checker: 跳过表格段落重复 + min_words 30→40
- Scanner: `code_block_count //2` 修复开闭 fence 双计数 bug

## [5.2.0] — 2026-03-11

### Added
- 14 阶段教程流水线 (新增 readability, consistency, collect_refs, track 等)
- BasePipeline 抽象基类
- 插件热加载系统
- 评分规则引擎 (YAML 配置)
- 交互式 CLI
- ECharts Dashboard
