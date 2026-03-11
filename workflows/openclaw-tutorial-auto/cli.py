#!/usr/bin/env python3
"""
cli.py — 交互式命令行界面
=============================
提供富交互式 CLI，实时查看进度、选择章节、手动触发阶段。

## 使用方式

    python3 cli.py                    # 进入交互模式
    python3 cli.py scan               # 直接执行扫描
    python3 cli.py status             # 查看状态
    python3 cli.py queue              # 查看任务队列
    python3 cli.py plugins            # 查看插件

## 交互模式命令

    scan [--max N]          扫描教程仓库
    analyze                 质量分析
    refine [chapter_num]    精炼指定/全部章节
    code <dir>              代码扫描
    run [stages...]         运行流水线
    status                  查看最近扫描结果摘要
    chapters                列出所有章节及评分
    diff [--since N]        增量扫描
    dashboard               启动 Dashboard
    queue                   查看/管理任务队列
    submit <type> [params]  提交异步任务
    plugins                 列出/管理插件
    score <file>            使用评分引擎评分
    help                    显示帮助
    quit / exit             退出
"""

from __future__ import annotations

import json
import os
import readline  # 启用输入历史和补全
import shlex
import sys
import time

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from modules.compat import setup_logger, cfg, load_json

log = setup_logger("cli")

# ── ANSI 颜色 ────────────────────────────────────────
class C:
    """ANSI color codes."""
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    RESET = "\033[0m"

    @staticmethod
    def ok(s): return f"{C.GREEN}{s}{C.RESET}"
    @staticmethod
    def warn(s): return f"{C.YELLOW}{s}{C.RESET}"
    @staticmethod
    def err(s): return f"{C.RED}{s}{C.RESET}"
    @staticmethod
    def info(s): return f"{C.CYAN}{s}{C.RESET}"
    @staticmethod
    def bold(s): return f"{C.BOLD}{s}{C.RESET}"
    @staticmethod
    def dim(s): return f"{C.DIM}{s}{C.RESET}"


OUTPUT_DIR = cfg("output_dir", os.environ.get(
    "OUTPUT_DIR", "/tmp/openclaw-tutorial-auto-reports"))

# ── 命令补全 ──────────────────────────────────────────
COMMANDS = [
    "scan", "analyze", "refine", "format", "code", "run",
    "status", "chapters", "diff", "dashboard", "queue",
    "submit", "plugins", "score", "help", "quit", "exit",
]

def _completer(text, state):
    options = [c for c in COMMANDS if c.startswith(text)]
    return options[state] if state < len(options) else None

readline.set_completer(_completer)
readline.parse_and_bind("tab: complete")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CLI 主类
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class InteractiveCLI:
    """交互式命令行。"""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self._pipeline = None
        self._code_pipeline = None

    def banner(self):
        print(f"""
{C.BOLD}╔════════════════════════════════════════════════════════╗
║  🐾  OpenClaw Tutorial Auto — Interactive CLI  v5.0   ║
╚════════════════════════════════════════════════════════╝{C.RESET}
{C.DIM}输入 'help' 查看命令列表, 'quit' 退出{C.RESET}
""")

    def run(self):
        """交互主循环。"""
        self.banner()
        while True:
            try:
                raw = input(f"{C.CYAN}openclaw>{C.RESET} ").strip()
                if not raw:
                    continue
                parts = shlex.split(raw)
                cmd = parts[0].lower()
                args = parts[1:]

                handler = getattr(self, f"cmd_{cmd}", None)
                if handler:
                    handler(args)
                elif cmd in ("quit", "exit", "q"):
                    print(C.dim("👋 再见"))
                    break
                else:
                    print(C.err(f"未知命令: {cmd}。输入 'help' 查看帮助"))

            except (EOFError, KeyboardInterrupt):
                print(f"\n{C.dim('👋 再见')}")
                break
            except Exception as e:
                print(C.err(f"错误: {e}"))

    # ── 命令处理器 ────────────────────────────────────

    def cmd_help(self, args):
        """显示帮助。"""
        print(f"""
{C.bold('可用命令:')}

  {C.info('scan')} [--max N]           扫描教程仓库
  {C.info('analyze')}                  质量分析
  {C.info('refine')} [chapter_num]     精炼指定/全部章节
  {C.info('format')}                   格式化
  {C.info('code')} <dir>               代码扫描
  {C.info('run')} [stages...]          运行流水线
  {C.info('status')}                   最近扫描结果摘要
  {C.info('chapters')}                 列出所有章节及评分
  {C.info('diff')} [--since N]         增量扫描
  {C.info('dashboard')}                启动 Dashboard 服务器
  {C.info('queue')}                    查看任务队列
  {C.info('submit')} <tutorial|code>   提交异步任务
  {C.info('plugins')}                  插件管理
  {C.info('score')} <file.json>        评分引擎评分
  {C.info('help')}                     显示此帮助
  {C.info('quit')} / {C.info('exit')}              退出

{C.dim('提示: 按 Tab 键自动补全命令')}
""")

    def cmd_scan(self, args):
        """执行扫描阶段。"""
        from pipeline import Pipeline
        max_ch = None
        if "--max" in args:
            idx = args.index("--max")
            if idx + 1 < len(args):
                max_ch = int(args[idx + 1])

        print(C.info("📡 正在扫描教程仓库..."))
        p = Pipeline(dry_run=self.dry_run, stages=["scan"], max_chapters=max_ch)
        result = p.run()
        self._pipeline = p
        self._show_scan_summary(p.results.get("scan", {}).get("data", {}))

    def cmd_analyze(self, args):
        """执行分析阶段。"""
        from pipeline import Pipeline
        print(C.info("🔍 正在分析质量..."))
        p = Pipeline(dry_run=self.dry_run, stages=["scan", "analyze"])
        result = p.run()
        self._pipeline = p
        self._show_analysis_summary(p.results.get("analyze", {}).get("data", {}))

    def cmd_refine(self, args):
        """执行精炼。"""
        from pipeline import Pipeline
        stages = ["scan", "analyze", "collect_refs", "refine"]
        max_ch = int(args[0]) if args and args[0].isdigit() else None
        print(C.info(f"✨ 正在精炼{'第 ' + args[0] + ' 章' if args else '全部章节'}..."))
        p = Pipeline(dry_run=self.dry_run, stages=stages, max_chapters=max_ch or 3)
        p.run()
        self._pipeline = p

    def cmd_format(self, args):
        """执行格式化。"""
        from pipeline import Pipeline
        print(C.info("📐 正在格式化..."))
        p = Pipeline(dry_run=self.dry_run, stages=["scan", "analyze", "format"])
        p.run()

    def cmd_code(self, args):
        """代码扫描。"""
        from code_pipeline import CodePipeline
        project_dir = args[0] if args else os.getcwd()
        print(C.info(f"🔧 正在扫描代码: {project_dir}"))
        cp = CodePipeline(project_dir=project_dir, dry_run=self.dry_run, stages=["scan"])
        cp.run()
        scan = cp.results.get("scan", {}).get("data", {})
        s = scan.get("summary", {})
        print(f"\n  文件: {s.get('total_files', 0)} | "
              f"总行: {s.get('total_loc', 0)} | "
              f"平均分: {s.get('avg_score', 0):.1f} | "
              f"缺陷: {s.get('total_defects', 0)}")

    def cmd_run(self, args):
        """运行完整流水线或指定阶段。"""
        from pipeline import Pipeline
        stages = args if args else None
        print(C.info(f"🚀 运行流水线: {' → '.join(stages) if stages else '全流程'}"))
        p = Pipeline(dry_run=self.dry_run, stages=stages)
        p.run()
        self._pipeline = p

    def cmd_status(self, args):
        """显示最近扫描状态。"""
        scan_path = os.path.join(OUTPUT_DIR, "scan-report.json")
        data = load_json(scan_path)
        if not data:
            print(C.warn("没有找到扫描报告。先运行 'scan' 命令"))
            return
        self._show_scan_summary(data)

    def cmd_chapters(self, args):
        """列出所有章节及评分。"""
        scan_path = os.path.join(OUTPUT_DIR, "scan-report.json")
        data = load_json(scan_path)
        if not data:
            print(C.warn("没有扫描报告。先运行 'scan'"))
            return

        chapters = data.get("chapters", [])
        print(f"\n{C.bold('章节评分列表')} ({len(chapters)} 章)\n")
        print(f"  {'#':>3}  {'评分':>4}  {'等级':>4}  {'字数':>6}  {'缺陷':>4}  标题")
        print(f"  {'─'*3}  {'─'*4}  {'─'*4}  {'─'*6}  {'─'*4}  {'─'*30}")

        for ch in chapters:
            num = ch.get("number", 0)
            score = ch.get("quality_score", 0)
            grade = ch.get("score_detail", {}).get("grade", "?")
            wc = ch.get("word_count", 0)
            defects = len(ch.get("defects", []))
            title = ch.get("title", "?")[:40]

            # 颜色
            if score >= 85:
                sc = C.ok(f"{score:>4}")
            elif score >= 60:
                sc = C.warn(f"{score:>4}")
            else:
                sc = C.err(f"{score:>4}")

            print(f"  {num:>3}  {sc}  {grade:>4}  {wc:>6}  {defects:>4}  {title}")

        print()

    def cmd_diff(self, args):
        """增量扫描。"""
        from modules.diff_scanner import scan_diff
        since = "HEAD~1"
        if "--since" in args:
            idx = args.index("--since")
            if idx + 1 < len(args):
                since = args[idx + 1]
        print(C.info(f"📊 增量扫描 (since {since})..."))
        result = scan_diff(since=since)
        files = result.get("files", [])
        print(f"\n  变更文件: {result.get('total_changed', 0)}")
        for f in files[:10]:
            print(f"    {f.get('status', '?')} {f.get('file', '?')}")

    def cmd_dashboard(self, args):
        """启动 Dashboard 服务器。"""
        port = int(args[0]) if args else 8686
        print(C.info(f"🖥️  正在启动 Dashboard (port {port})..."))
        print(C.dim(f"   访问: http://localhost:{port}"))
        print(C.dim("   按 Ctrl+C 停止"))
        from dashboard.server import start_server
        start_server(port=port)

    def cmd_queue(self, args):
        """查看任务队列。"""
        from task_queue import TaskQueue
        tq = TaskQueue()
        state_path = tq.persist_file
        data = load_json(state_path)
        if not data:
            print(C.dim("队列为空"))
            return

        tasks = data.get("tasks", {})
        print(f"\n{C.bold('任务队列')} ({len(tasks)} 个任务)\n")
        for tid, t in tasks.items():
            status = t.get("status", "?")
            status_icon = {
                "done": C.ok("✅"),
                "failed": C.err("❌"),
                "running": C.info("⏳"),
                "pending": C.dim("⏸️"),
                "cancelled": C.dim("🚫"),
            }.get(status, "?")
            print(f"  {status_icon} {tid} | {t.get('task_type', '?')} | {status}")
        print()

    def cmd_submit(self, args):
        """提交异步任务。"""
        from task_queue import TaskQueue, Task
        if not args:
            print(C.warn("用法: submit <tutorial|code> [--dry-run]"))
            return
        task_type = args[0]
        dry_run = "--dry-run" in args
        tq = TaskQueue()
        tq.start()
        tid = tq.submit(Task(
            task_type=task_type,
            params={"dry_run": dry_run, "stages": ["scan"]},
        ))
        print(C.info(f"任务已提交: {tid}"))
        print(C.dim("等待完成..."))
        tq.wait(timeout=60)
        status = tq.get_status(tid)
        if status:
            print(f"  状态: {status['status']}")
        tq.stop()

    def cmd_plugins(self, args):
        """插件管理。"""
        from plugin_loader import get_plugin_manager
        pm = get_plugin_manager()
        pm.load_all()
        plugins = pm.list_plugins()

        if not plugins:
            print(C.dim("没有已加载的插件"))
            return

        print(f"\n{C.bold('已加载插件')} ({len(plugins)} 个)\n")
        for p in plugins:
            status = C.ok("✅") if p["enabled"] else C.dim("⏸️")
            print(f"  {status} {C.bold(p['name'])} v{p['version']}")
            if p["description"]:
                print(f"     {C.dim(p['description'])}")
            print(f"     hooks: {', '.join(p['hooks']) or 'none'}")
        print()

    def cmd_score(self, args):
        """评分引擎评分。"""
        from scoring_engine import ScoringEngine
        if not args:
            print(C.warn("用法: score <scan-data.json> [--rules rules.yaml]"))
            return

        data_file = args[0]
        rules_file = None
        if "--rules" in args:
            idx = args.index("--rules")
            if idx + 1 < len(args):
                rules_file = args[idx + 1]

        with open(data_file, encoding="utf-8") as f:
            data = json.load(f)

        engine = ScoringEngine()
        if rules_file:
            engine.load_rules(rules_file)
        else:
            engine.load_default()

        # 支持单章节或批量
        if "chapters" in data:
            chapters = data["chapters"]
        else:
            chapters = [data]

        for ch in chapters:
            result = engine.evaluate(ch)
            title = ch.get("title", ch.get("file", "?"))
            grade_color = C.ok if result.grade in ("S", "A") else (
                C.warn if result.grade in ("B", "C") else C.err)
            print(f"  {grade_color(result.grade)} {result.total:.0f}  {title}")

    # ── 显示辅助 ──────────────────────────────────────

    def _show_scan_summary(self, data):
        """显示扫描摘要。"""
        s = data.get("summary", {})
        chapters = data.get("chapters", [])
        print(f"""
{C.bold('📊 扫描摘要')}

  章节总数: {s.get('completed', 0)}/{data.get('expected_chapters', '?')}
  平均评分: {C.bold(str(s.get('avg_score', 0)))}
  总缺陷数: {s.get('total_defects', 0)}
  总字数:   {s.get('total_words', 0)}
""")
        # Top 5 低分章节
        low = sorted(chapters, key=lambda x: x.get("quality_score", 100))[:5]
        if low:
            print(f"  {C.warn('低分 Top 5:')}")
            for ch in low:
                print(f"    Ch{ch.get('number', '?'):02d}: "
                      f"{ch.get('quality_score', 0)} 分 — {ch.get('title', '?')[:35]}")
            print()

    def _show_analysis_summary(self, data):
        """显示分析摘要。"""
        print(f"""
{C.bold('🔍 分析摘要')}

  优先级分布: {data.get('priority_distribution', {})}
  总优化项:   {data.get('total_improvements', 0)}
""")


# ── 入口 ─────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(description="OpenClaw Tutorial Auto — Interactive CLI")
    parser.add_argument("command", nargs="*", help="直接命令 (可选)")
    parser.add_argument("--dry-run", action="store_true", help="干跑模式")
    args = parser.parse_args()

    cli = InteractiveCLI(dry_run=args.dry_run)

    if args.command:
        cmd = args.command[0]
        cmd_args = args.command[1:]
        handler = getattr(cli, f"cmd_{cmd}", None)
        if handler:
            handler(cmd_args)
        else:
            print(C.err(f"未知命令: {cmd}"))
            sys.exit(1)
    else:
        cli.run()


if __name__ == "__main__":
    main()
