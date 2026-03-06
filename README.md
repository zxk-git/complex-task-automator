# Complex Task Automator v2.3.0

> 高级任务自动化引擎 — 从信息搜集到 Git 推送的全链路文档工作流自动化，24/7 无人值守

## 核心特性

| 类别 | 特性 |
|------|------|
| **文档自动化** | 信息搜集 → 大纲管理 → 内容撰写 → 质量检测 → Git 推送 全链路 |
| **六维度质量检测** | 内容充实度、结构完整性、代码质量、可读性、教学价值、时效性 |
| **24/7 持续优化** | OpenClaw Cron 调度、批量生成、网络搜索优化、健康检查 |
| **统一配置管理** | `config.yaml` 单一配置源 + `utils.py` 共享工具模块 |
| **结构化日志** | 全部 13 个脚本统一 `setup_logger()` |
| **任务引擎** | 拓扑排序、并行执行、退避重试、检查点恢复、断点续跑 |
| **Git 自动化** | 安全白名单提交、远程推送、中文文件名支持 |
| **安全可控** | DRY_RUN 模式、文件保护、exec-approvals 集成 |

## 快速开始

```bash
# 运行示例工作流
python3 scripts/task-run.py examples/simple-workflow.yaml

# 文档自动化 — 全链路执行（搜集→编写→质检→提交→报告）
python3 scripts/task-run.py workflows/openclaw-tutorial-auto/workflow-full.yaml

# 指定章节号
python3 scripts/task-run.py workflows/openclaw-tutorial-auto/workflow-full.yaml --vars CHAPTER_NUM=5

# 试运行（不实际写入文件）
python3 scripts/task-run.py workflows/openclaw-tutorial-auto/workflow-full.yaml --vars DRY_RUN=true

# 持续优化模式
python3 scripts/task-run.py workflows/openclaw-tutorial-auto/workflow-optimize.yaml

# 列出可用 skills
python3 scripts/task-skills.py
```

## 目录结构

```
complex-task-automator/
├── SKILL.md              # 完整文档 (1700+ 行)
├── README.md             # 本文件
├── _meta.json            # 元数据 (v2.3.0)
├── .gitignore
├── assets/
│   └── TASK_GUIDE.md     # 使用指南
├── templates/
│   ├── basic.yaml        # 基础模板
│   └── data-pipeline.yaml
├── examples/
│   ├── simple-workflow.yaml
│   ├── parallel-processing.yaml
│   ├── retry-demo.yaml
│   ├── research-assistant.yaml
│   └── skill-integration.yaml
├── scripts/
│   ├── task-run.py       # CLI 入口
│   ├── task-skills.py    # Skill 管理
│   └── core/
│       ├── __init__.py   # v2.3.0
│       ├── models.py     # 数据模型 (Task, Workflow, RetryConfig...)
│       ├── engine.py     # 执行引擎 (拓扑排序, 并行, 重试)
│       ├── logger.py     # 日志系统 (JSON+Text)
│       ├── scheduler.py  # 调度器 (Cron, Event)
│       ├── skill_executor.py  # Skill 执行器
│       └── utils.py      # 共享工具 (substitute_variables)
└── workflows/
    └── openclaw-tutorial-auto/   # 教程自动化项目
        ├── config.yaml           # 统一配置源
        ├── workflow.yaml         # 标准工作流
        ├── workflow-full.yaml    # 完整流水线
        ├── workflow-optimize.yaml # 优化流水线
        ├── workflow-batch.yaml   # 批量生成
        └── scripts/
            ├── utils.py          # 项目共享工具
            ├── check_quality.py  # 六维度质量检测
            ├── optimize_chapter.py
            ├── web_researcher.py
            ├── daemon.py         # 24/7 调度入口
            ├── batch_runner.py
            ├── health_check.py
            ├── git_workflow.py
            ├── generate_report.py
            ├── manage_outline.py
            ├── analyze_progress.py
            ├── check_env.py
            ├── check_dependencies.py
            ├── research.py       # 兼容 shim → web_researcher
            └── write_chapter.py  # 知识库驱动的章节生成
```

## 文档

- [SKILL.md](SKILL.md) — 完整功能文档、架构设计、API 参考
- [assets/TASK_GUIDE.md](assets/TASK_GUIDE.md) — 快速使用指南

## GitHub

https://github.com/zxk-git/complex-task-automator

## 许可证

MIT
