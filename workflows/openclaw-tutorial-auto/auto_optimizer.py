#!/usr/bin/env python3
"""
auto_optimizer.py — 统一自动优化入口
=======================================
支持两种优化模式:
  - tutorial: 教程文档优化 (Markdown)
  - code:     代码质量优化 (Python/JS/TS/Shell)

会根据项目内容自动检测模式，也可手动指定。

用法:
  python3 auto_optimizer.py                              # 自动检测
  python3 auto_optimizer.py --mode tutorial              # 教程模式
  python3 auto_optimizer.py --mode code /path/to/project # 代码模式
  python3 auto_optimizer.py --mode code --dry-run        # 代码干跑
  python3 auto_optimizer.py --mode both                  # 两种都运行
  python3 auto_optimizer.py --diff --since HEAD~3         # 增量模式
  python3 auto_optimizer.py --diff --staged               # 仅分析暂存区
"""

import argparse
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from modules.compat import setup_logger

log = setup_logger("auto_optimizer")


def detect_mode(project_dir: str) -> str:
    """自动检测项目类型。"""
    md_count = 0
    code_count = 0
    code_exts = {".py", ".js", ".ts", ".mjs", ".jsx", ".tsx", ".sh"}

    for f in os.listdir(project_dir):
        if f.endswith(".bak") or f.startswith("."):
            continue
        ext = os.path.splitext(f)[1].lower()
        if ext == ".md":
            md_count += 1
        elif ext in code_exts:
            code_count += 1

    # 也递归检查一层
    for d in os.listdir(project_dir):
        subdir = os.path.join(project_dir, d)
        if os.path.isdir(subdir) and not d.startswith("."):
            for f in os.listdir(subdir):
                ext = os.path.splitext(f)[1].lower()
                if ext in code_exts:
                    code_count += 1

    if md_count > 5 and md_count > code_count:
        return "tutorial"
    elif code_count > 3:
        return "code"
    elif md_count > 0:
        return "tutorial"
    else:
        return "code"


def run_tutorial_mode(args) -> dict:
    """运行教程优化模式。"""
    from pipeline import Pipeline
    stages = None
    if args.stage:
        if args.stage in Pipeline.STAGES:
            idx = Pipeline.STAGES.index(args.stage)
            stages = Pipeline.STAGES[:idx + 1]

    pipeline = Pipeline(
        max_chapters=args.max_chapters,
        dry_run=args.dry_run,
        stages=stages,
        web_search=getattr(args, "web_search", True),
        check_external=getattr(args, "check_external", False),
        incremental=getattr(args, "incremental", False),
        refine_threshold=getattr(args, "refine_threshold", None),
    )
    return pipeline.run()


def run_code_mode(args) -> dict:
    """运行代码优化模式。"""
    from code_pipeline import CodePipeline
    stages = None
    if args.stage:
        if args.stage in CodePipeline.STAGES:
            idx = CodePipeline.STAGES.index(args.stage)
            stages = CodePipeline.STAGES[:idx + 1]

    pipeline = CodePipeline(
        project_dir=args.project_dir,
        output_dir=args.output_dir,
        max_files=getattr(args, "max_files", None),
        dry_run=args.dry_run,
        stages=stages,
        extensions=getattr(args, "ext", None),
    )
    return pipeline.run()


def main():
    parser = argparse.ArgumentParser(
        description="统一自动优化入口 — 支持教程 & 代码",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s                                    # 自动检测模式
  %(prog)s --mode tutorial                    # 教程优化
  %(prog)s --mode code /path/to/project       # 代码优化
  %(prog)s --mode code --dry-run              # 代码干跑
  %(prog)s --mode both                        # 两种都运行
"""
    )

    parser.add_argument("project_dir", nargs="?", default=None,
                        help="目标项目目录 (代码模式必需)")
    parser.add_argument("--mode", choices=["tutorial", "code", "both", "auto"],
                        default="auto",
                        help="优化模式 (默认: auto)")
    parser.add_argument("--stage", type=str, default=None,
                        help="仅运行指定阶段")
    parser.add_argument("--dry-run", action="store_true",
                        help="干跑模式")
    parser.add_argument("--output-dir", type=str, default=None,
                        help="报告输出目录")

    # 教程专用参数
    parser.add_argument("--max-chapters", type=int, default=None,
                        help="[tutorial] 最大优化章节数")
    parser.add_argument("--no-web-search", action="store_true",
                        help="[tutorial] 禁用 Web 搜索 (默认启用)")
    parser.add_argument("--web-search", action="store_true", default=True,
                        help="[tutorial] 启用 Web 搜索 (默认启用)")
    parser.add_argument("--check-external", action="store_true",
                        help="[tutorial] 检查外部链接")

    # 代码专用参数
    parser.add_argument("--max-files", type=int, default=None,
                        help="[code] 最大优化文件数")
    parser.add_argument("--ext", nargs="+", default=None,
                        help="[code] 仅扫描指定扩展名")

    # 增量模式参数
    parser.add_argument("--incremental", action="store_true",
                        help="[tutorial] 增量模式: 仅处理上次运行后变更的文件 (mtime+size 缓存)")
    parser.add_argument("--refine-threshold", type=int, default=None,
                        help="[tutorial] 智能精炼阈值: 跳过超过此分数的章节 (如 95)")
    parser.add_argument("--diff", action="store_true",
                        help="增量模式: 仅分析 git diff 变更的文件")
    parser.add_argument("--since", type=str, default="HEAD~1",
                        help="[diff] Git 起始点 (默认: HEAD~1)")
    parser.add_argument("--staged", action="store_true",
                        help="[diff] 仅分析暂存区")

    # AI 精炼参数
    parser.add_argument("--ai-refine", action="store_true",
                        help="启用 AI 精炼 (通过 OpenClaw agent)")
    parser.add_argument("--ai-agent", type=str, default="coding",
                        help="[ai] OpenClaw agent ID (默认: coding)")
    parser.add_argument("--ai-thinking", type=str, default="medium",
                        choices=["off", "minimal", "low", "medium", "high"],
                        help="[ai] 思考级别 (默认: medium)")

    args = parser.parse_args()

    # 处理 --no-web-search 标志
    if getattr(args, "no_web_search", False):
        args.web_search = False

    # 自动检测模式
    mode = args.mode
    if mode == "auto":
        # 教程目录
        tutorial_dir = os.environ.get(
            "PROJECT_DIR",
            "/root/.openclaw/workspace/zxk-private/openclaw-tutorial-auto"
        )
        if args.project_dir:
            detected = detect_mode(args.project_dir)
            log.info(f"自动检测模式: {detected} (项目: {args.project_dir})")
            mode = detected
        elif os.path.isdir(tutorial_dir):
            mode = "tutorial"
            log.info("自动检测模式: tutorial (默认教程目录)")
        else:
            mode = "code"
            args.project_dir = os.getcwd()
            log.info("自动检测模式: code (当前目录)")

    results = {}

    # ── 增量 diff 模式 ──
    if getattr(args, "diff", False):
        from modules.diff_scanner import scan_diff
        diff_dir = args.project_dir or os.environ.get(
            "PROJECT_DIR",
            "/root/.openclaw/workspace/zxk-private/openclaw-tutorial-auto"
        )
        log.info("")
        log.info("=" * 60)
        log.info("  📋 增量 diff 模式")
        log.info("=" * 60)
        diff_result = scan_diff(
            project_dir=diff_dir,
            since=getattr(args, "since", "HEAD~1"),
            staged=getattr(args, "staged", False),
        )
        results["diff"] = diff_result
        s = diff_result["summary"]
        log.info(f"  变更文件: {diff_result['total_changed']}")
        log.info(f"  教程: {s['tutorial_count']}, 代码: {s['code_count']}")
        if s["chapters_affected"]:
            log.info(f"  影响章节: {s['chapters_affected']}")
        if s["languages_affected"]:
            log.info(f"  影响语言: {s['languages_affected']}")

        # 设置环境变量供后续 pipeline 过滤
        os.environ["DIFF_MODE"] = "true"
        os.environ["DIFF_SINCE"] = getattr(args, "since", "HEAD~1")

        # 自动决定运行哪些模式
        if s["tutorial_count"] > 0:
            mode = "tutorial" if s["code_count"] == 0 else "both"
        elif s["code_count"] > 0:
            mode = "code"
        else:
            log.info("  无需优化的变更文件")
            sys.exit(0)

    if mode in ("tutorial", "both"):
        log.info("")
        log.info("=" * 60)
        log.info("  📚 教程优化模式")
        log.info("=" * 60)
        results["tutorial"] = run_tutorial_mode(args)

    if mode in ("code", "both"):
        if not args.project_dir:
            if mode == "both":
                # both 模式下 code 使用 Skill 自身目录
                args.project_dir = _ROOT
            else:
                log.error("代码模式需要指定 project_dir")
                sys.exit(1)
        log.info("")
        log.info("=" * 60)
        log.info("  🔧 代码优化模式")
        log.info("=" * 60)
        results["code"] = run_code_mode(args)

    # ── AI 精炼 ──
    if getattr(args, "ai_refine", False):
        log.info("")
        log.info("=" * 60)
        log.info("  🤖 AI 精炼 (OpenClaw)")
        log.info("=" * 60)
        try:
            from modules.ai_refiner import ai_refine_batch
            os.environ.setdefault("OPENCLAW_AGENT", getattr(args, "ai_agent", "coding"))
            os.environ.setdefault("OPENCLAW_THINKING", getattr(args, "ai_thinking", "medium"))

            # 从已有结果中提取待精炼条目
            chapters = []
            code_files = []
            if "tutorial" in results:
                scan_data = results["tutorial"].get("stage_results", {}).get("scan", {}).get("data", {})
                analysis_data = results["tutorial"].get("stage_results", {}).get("analyze", {}).get("data", {})
                for ch in analysis_data.get("chapters", []):
                    if ch.get("quality_score", 100) < 75:  # 只对 B 级以下做 AI 精炼
                        project_dir = os.environ.get("PROJECT_DIR",
                            "/root/.openclaw/workspace/zxk-private/openclaw-tutorial-auto")
                        chapters.append({
                            "path": os.path.join(project_dir, ch.get("file", "")),
                            "defects": ch.get("defects", []),
                            "chapter": ch.get("chapter", 0),
                            "score": ch.get("quality_score", 0),
                            "grade": ch.get("grade", "?"),
                        })
            if "code" in results:
                scan_data = results["code"].get("stage_results", {}).get("scan", {}).get("data", {})
                for f in scan_data.get("files", []):
                    if f.get("quality_score", 100) < 75:
                        code_files.append({
                            "path": f.get("file", ""),
                            "language": f.get("language", "python"),
                            "defects": f.get("defects", []),
                        })

            ai_result = ai_refine_batch(chapters=chapters, code_files=code_files)
            results["ai_refine"] = ai_result
            t_ok = sum(1 for r in ai_result.get("tutorial", []) if r.get("ok"))
            c_ok = sum(1 for r in ai_result.get("code", []) if r.get("ok"))
            log.info(f"  AI 精炼: 教程 {t_ok} 章, 代码 {c_ok} 文件, "
                     f"建议 {len(ai_result.get('suggestions', []))} 条")
        except Exception as e:
            log.error(f"  AI 精炼失败 (非致命): {e}")
            results["ai_refine"] = {"error": str(e)}

    # 汇总
    total_ok = sum(r.get("stages_ok", 0) for r in results.values())
    total_failed = sum(r.get("stages_failed", 0) for r in results.values())

    log.info("")
    log.info("═" * 60)
    log.info(f"  全部完成: {total_ok} 阶段成功, {total_failed} 阶段失败")
    log.info("═" * 60)

    if total_failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
