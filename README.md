# 🚀 Complex Task Automator

<div align="center">

**高级任务自动化引擎** — 从信息搜集到 Git 推送的全链路文档工作流自动化

[![Version](https://img.shields.io/badge/version-5.1.0-blue.svg)](SKILL.md)
[![Python](https://img.shields.io/badge/python-3.10+-green.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

</div>

---

## ✨ 核心特性

<table>
<tr>
<td width="50%">

### 📚 文档自动化
- 信息搜集 → 大纲 → 撰写 → 质检 → Git 推送
- 六维度质量评分（S/A/B/C/D/F 等级）
- YAML 可配置评分规则引擎
- 12 种自动修复操作

</td>
<td width="50%">

### 🔧 代码质量分析
- 8 语言深度分析 (Python/JS/TS/Go/Shell/Rust/C/C++/Java)
- 五维度评分 + 31 种优化建议模板
- 自动修复 (docstring/imports/header_guard)
- 权威引用 + Web 搜索增强

</td>
</tr>
<tr>
<td>

### ⚡ 任务引擎
- 拓扑排序 + 并行执行
- 6 种执行器 (Shell/Python/Node/HTTP/Webhook/Skill)
- 退避重试 + 检查点恢复
- Hooks 系统 (pre/post/failure)

</td>
<td>

### 🔌 扩展系统
- 插件热加载 (11 种 Hooks)
- 交互式 CLI (15 命令 + Tab 补全)
- 异步任务队列 (优先级 + 多线程)
- ECharts Dashboard 可视化

</td>
</tr>
</table>

---

## 🚀 快速开始

```bash
# 交互式 CLI（推荐）
cd workflows/openclaw-tutorial-auto
python3 cli.py

# 运行示例工作流
python3 scripts/task-run.py examples/simple-workflow.yaml

# 教程优化流水线
python3 workflows/openclaw-tutorial-auto/auto_optimizer.py --mode tutorial --dry-run

# 代码质量扫描
python3 workflows/openclaw-tutorial-auto/auto_optimizer.py --mode code /path/to/project

# 通过 OpenClaw Workflow
openclaw workflow run workflows/openclaw-tutorial-auto/workflow-pipeline.yaml
```

---

## 📁 项目结构

```
complex-task-automator/
├── 📄 README.md                   # 本文件
├── 📄 SKILL.md                    # 完整功能文档 (1800+ 行)
├── 📄 _meta.json                  # 元数据
│
├── 📂 scripts/                    # 任务引擎
│   ├── task-run.py                    # CLI 入口
│   ├── task-skills.py                 # Skill 管理
│   └── core/                          # 引擎核心
│       ├── engine.py                      # 执行引擎 (拓扑排序/Hooks/6 执行器)
│       ├── models.py                      # 数据模型
│       ├── logger.py                      # 结构化日志
│       ├── scheduler.py                   # 调度器 (Cron/Event)
│       ├── skill_executor.py              # Skill 执行器
│       └── utils.py                       # 共享工具
│
├── 📂 workflows/
│   ├── 📂 openclaw-tutorial-auto/     # 🌟 教程+代码自动优化系统 v5.1
│   │   ├── auto_optimizer.py              # 统一入口
│   │   ├── cli.py                         # 交互式 CLI (15 命令)
│   │   ├── pipeline.py                    # 教程流水线 (11 阶段)
│   │   ├── code_pipeline.py               # 代码流水线 (5 阶段)
│   │   ├── base_pipeline.py               # 流水线基类 + 插件集成
│   │   ├── plugin_loader.py               # 插件热加载系统
│   │   ├── scoring_engine.py              # YAML 评分规则引擎
│   │   ├── task_queue.py                  # 异步任务队列
│   │   ├── modules/                       # 17 功能模块
│   │   ├── plugins/                       # 插件目录
│   │   ├── scoring-rules/                 # 评分规则 (YAML)
│   │   ├── dashboard/                     # ECharts Dashboard
│   │   ├── docs/                          # 详细文档
│   │   │   ├── API.md                         # API 参考
│   │   │   ├── CLI-GUIDE.md                   # CLI 使用手册
│   │   │   └── PLUGIN-GUIDE.md                # 插件开发指南
│   │   ├── prompts/                       # AI 提示词
│   │   └── templates/                     # 输出模板
│   │
│   └── 📂 hubei-job-monitor/         # 湖北岗位监控
│
├── 📂 examples/                   # 工作流示例
│   ├── simple-workflow.yaml
│   ├── parallel-processing.yaml
│   ├── retry-demo.yaml
│   └── skill-integration.yaml
│
├── 📂 templates/                  # 工作流模板
├── 📂 assets/                     # 资源文件
│   └── TASK_GUIDE.md                  # 使用指南
└── 📂 _archive/                   # 归档遗留文件
```

---

## 📊 双模式流水线

### 教程模式 (11 阶段)

```
scan → analyze → collect_refs → check_links → check_consistency →
check_readability → refine → format → track → git → report
```

### 代码模式 (5 阶段)

```
scan → analyze → enrich → refine → report
```

> 详细说明见 [workflows/openclaw-tutorial-auto/README.md](workflows/openclaw-tutorial-auto/README.md)

---

## 🎯 质量评分体系

| 维度 | 说明 |
|------|------|
| **教程** (6 维度) | 内容深度 25% · 结构完整 20% · 代码质量 15% · 教学价值 15% · 参考来源 10% · 可读性 15% |
| **代码** (5 维度) | 结构 20% · 文档 20% · 复杂度 20% · 风格 20% · 最佳实践 20% |
| **等级** | S ≥95 · A ≥85 · B ≥75 · C ≥60 · D ≥40 · F <40 |

---

## 📖 文档导航

| 文档 | 说明 |
|------|------|
| [SKILL.md](SKILL.md) | 完整功能文档、架构设计、任务模型、API 参考 |
| [assets/TASK_GUIDE.md](assets/TASK_GUIDE.md) | 快速使用指南 |
| [workflows/.../README.md](workflows/openclaw-tutorial-auto/README.md) | 优化系统详细文档 |
| [docs/API.md](workflows/openclaw-tutorial-auto/docs/API.md) | 模块 API 参考 |
| [docs/CLI-GUIDE.md](workflows/openclaw-tutorial-auto/docs/CLI-GUIDE.md) | CLI 交互手册 |
| [docs/PLUGIN-GUIDE.md](workflows/openclaw-tutorial-auto/docs/PLUGIN-GUIDE.md) | 插件开发指南 |

---

## 🔗 链接

- **GitHub**: https://github.com/zxk-git/complex-task-automator
- **License**: MIT
