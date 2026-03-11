# Complex Task Automator v2.4.0

> 高级任务自动化引擎 — 从信息搜集到 Git 推送的全链路文档工作流自动化，24/7 无人值守

## 核心特性

| 类别 | 特性 |
|------|------|
| **文档自动化** | 信息搜集 → 大纲管理 → 内容撰写 → 质量检测 → Git 推送 全链路 |
| **六维度质量检测** | 内容充实度、结构完整性、代码质量、可读性、教学价值、时效性 |
| **24/7 持续优化** | OpenClaw Cron 调度、批量生成、网络搜索优化、健康检查 |
| **统一配置管理** | `config.yaml` 单一配置源 + `utils.py` 共享工具模块 |
| **结构化日志** | 双输出 (JSON+Text)、检查点恢复、上下文管理器支持 |
| **任务引擎** | 拓扑排序、并行执行、退避重试、检查点恢复、断点续跑 |
| **6 种执行器** | Shell / Python / Node / HTTP / Webhook / Skill |
| **Hooks 系统** | pre_run / post_run / on_failure 钩子自动执行 |
| **Git 自动化** | 安全白名单提交、远程推送、中文文件名支持 |
| **安全可控** | DRY_RUN 模式（增强校验）、文件保护、exec-approvals 集成 |

## v2.4.0 更新 (相对 v2.3.0)

- **引擎**: 完整解析 workflow config/hooks；新增 Node.js 执行器；拓扑排序算法简化
- **Hooks**: pre_run / post_run / on_failure 钩子现已自动执行（shell/webhook/python）
- **CLI**: `--parallel`/`--timeout` 参数正确传递至引擎；新增 `--log-dir`
- **Dry Run**: 增强校验 — 检测 ID 重复与无效依赖引用
- **Utils**: 新增 safe_read/write_file/json、resolve_path、ensure_dir、load_yaml、which
- **Logger**: 上下文管理器 (`with`)、`reset_logger()`、防止重复 handler
- **SkillExecutor**: 统一变量替换（含 `{{ result.* }}` 引用）；跨平台 `which` 检测

## 快速开始

```bash
# 运行示例工作流
python3 scripts/task-run.py examples/simple-workflow.yaml

# 文档自动化 — 全链路执行（搜集→编写→质检→提交→报告）
python3 scripts/task-run.py workflows/openclaw-tutorial-auto/workflow-full.yaml

# 持续优化模式
python3 scripts/task-run.py workflows/openclaw-tutorial-auto/workflow-optimize.yaml

# 列出可用 skills
python3 scripts/task-skills.py
```

## 目录结构

```
complex-task-automator/
├── SKILL.md              # 完整文档 (1800+ 行)
├── README.md             # 本文件
├── _meta.json            # 元数据 (v2.4.0)
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
│   ├── task-run.py       # CLI 入口 (--parallel/--timeout/--log-dir)
│   ├── task-skills.py    # Skill 管理
│   └── core/
│       ├── __init__.py   # v2.4.0
│       ├── models.py     # 数据模型 (Task, Workflow, RetryConfig...)
│       ├── engine.py     # 执行引擎 (拓扑排序, Hooks, 6 种执行器)
│       ├── logger.py     # 日志系统 (JSON+Text, 上下文管理器)
│       ├── scheduler.py  # 调度器 (Cron, Event)
│       ├── skill_executor.py  # Skill 执行器
│       └── utils.py      # 共享工具 (变量替换, 安全 I/O, YAML, which)
└── workflows/
    ├── openclaw-tutorial-auto/   # 教程自动化项目 (模块化 v2)
    │   ├── config.yaml
    │   ├── pipeline.py           # 七阶段优化流水线
    │   ├── workflow-pipeline.yaml
    │   ├── modules/              # 5 个功能模块
    │   ├── prompts/              # 6 个提示词模板
    │   ├── templates/            # 2 个报告模板
    │   ├── utils/                # 3 个工具模块
    │   └── scripts/              # 遗留脚本
    └── hubei-job-monitor/        # 湖北岗位监控项目
```

## 文档

- [SKILL.md](SKILL.md) — 完整功能文档、架构设计、API 参考
- [assets/TASK_GUIDE.md](assets/TASK_GUIDE.md) — 快速使用指南

## GitHub

https://github.com/zxk-git/complex-task-automator

## 许可证

MIT
