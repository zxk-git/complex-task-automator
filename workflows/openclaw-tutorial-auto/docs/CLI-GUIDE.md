# 🖥️ CLI 使用手册

> OpenClaw 自动优化系统 — 交互式命令行界面

---

## 快速开始

```bash
# 进入交互模式
python3 cli.py

# 干跑模式 (不写入文件)
python3 cli.py --dry-run

# 直接执行命令
python3 cli.py scan --max 5
python3 cli.py status
python3 cli.py chapters
```

进入交互模式后会看到：

```
╔════════════════════════════════════════════════════════╗
║  🐾  OpenClaw Tutorial Auto — Interactive CLI  v5.0   ║
╚════════════════════════════════════════════════════════╝
输入 'help' 查看命令列表, 'quit' 退出

openclaw>
```

**提示**: 按 `Tab` 键自动补全命令名。

---

## 命令详解

### scan — 扫描教程

```
openclaw> scan
openclaw> scan --max 5       # 只扫描前 5 章
```

扫描教程仓库，输出摘要（章节数、平均评分、总缺陷、低分 Top 5）。

示例输出：
```
📡 正在扫描教程仓库...
📊 扫描摘要

  章节总数: 21/21
  平均评分: 72.5
  总缺陷数: 138
  总字数:   104400

  低分 Top 5:
    Ch16: 0 分 — 第 16 章：MCP 工具协议与自定义集成
    Ch14: 59 分 — 第 14 章：安全与权限管理
    ...
```

### analyze — 质量分析

```
openclaw> analyze
```

执行扫描 + 深度质量分析，输出优化建议优先级分布。

### refine — 精炼章节

```
openclaw> refine           # 精炼全部（默认最多 3 章）
openclaw> refine 5         # 仅精炼第 5 章
```

执行完整精炼流程：扫描 → 分析 → 收集参考 → 精炼。

### format — 格式化

```
openclaw> format
```

统一 Markdown 格式（标题间距、代码块样式等）。

### code — 代码扫描

```
openclaw> code /path/to/project
openclaw> code .           # 扫描当前目录
```

输出：文件数、总行数、平均分、缺陷数。

### run — 运行流水线

```
openclaw> run              # 运行全部阶段
openclaw> run scan analyze # 只运行指定阶段
```

### status — 查看状态

```
openclaw> status
```

从最近的扫描报告加载并显示摘要。无需重新扫描。

### chapters — 章节列表

```
openclaw> chapters
```

表格显示所有章节的编号、评分、等级、字数、缺陷数和标题。  
评分颜色：🟢 ≥85 | 🟡 ≥60 | 🔴 <60

示例输出：
```
章节评分列表 (21 章)

    #  评分  等级    字数  缺陷  标题
  ───  ────  ────  ──────  ────  ──────────────────────────────
    1    63     B    3200     8  第一章：OpenClaw 基础介绍与安装
    2    78     B    4500     3  第二章：Agent 编写入门
   ...
```

### diff — 增量扫描

```
openclaw> diff                  # 默认 HEAD~1
openclaw> diff --since HEAD~5   # 最近 5 次提交
openclaw> diff --since 2026-03-01
```

### dashboard — 启动 Dashboard

```
openclaw> dashboard             # 默认端口 8686
openclaw> dashboard 9090        # 自定义端口
```

启动后在浏览器访问 `http://localhost:8686`。按 `Ctrl+C` 停止。

### queue — 查看任务队列

```
openclaw> queue
```

显示所有异步任务及其状态（✅ done / ❌ failed / ⏳ running / ⏸️ pending）。

### submit — 提交异步任务

```
openclaw> submit tutorial            # 提交教程扫描任务
openclaw> submit code                # 提交代码扫描任务
openclaw> submit tutorial --dry-run  # 干跑模式
```

### plugins — 插件管理

```
openclaw> plugins
```

显示所有已加载插件的名称、版本、描述和 hooks。

示例输出：
```
已加载插件 (1 个)

  ✅ score_highlighter v1.0.0
     为低分章节/文件添加告警标记
     hooks: after_scan
```

### score — 评分引擎

```
openclaw> score /tmp/openclaw-tutorial-auto-reports/scan-report.json
openclaw> score report.json --rules my-rules.yaml
```

使用 YAML 评分规则引擎对扫描数据评分，支持批量和单文件。

### help — 帮助

```
openclaw> help
```

### quit / exit — 退出

```
openclaw> quit
openclaw> exit
```

也可以按 `Ctrl+C` 或 `Ctrl+D` 退出。

---

## 高级用法

### 组合工作流

```
# 典型工作流：先扫描查看状态，再精炼低分章节
openclaw> scan
openclaw> chapters          # 查看哪些章节分低
openclaw> refine 16         # 精炼第 16 章
openclaw> scan              # 重新扫描验证
```

### 与任务队列结合

```
# 后台提交多个任务
openclaw> submit tutorial
openclaw> submit code
openclaw> queue             # 查看进度
```

### 编程方式调用

```python
from cli import InteractiveCLI

cli = InteractiveCLI(dry_run=True)
cli.cmd_scan(["--max", "3"])
cli.cmd_chapters([])
cli.cmd_score(["report.json", "--rules", "custom.yaml"])
```

---

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `OUTPUT_DIR` | 输出报告目录 | `/tmp/openclaw-tutorial-auto-reports` |
| `DRY_RUN` | 全局干跑模式 | `false` |
