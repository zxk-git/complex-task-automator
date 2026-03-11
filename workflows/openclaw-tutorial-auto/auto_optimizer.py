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
"""

import argparse
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_SCRIPTS = os.path.join(_ROOT, "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

try:
    import importlib
    _utils_mod = importlib.import_module("utils")
    setup_logger = _utils_mod.setup_logger
except (ImportError, AttributeError):
    import logging
    def setup_logger(name):
        logging.basicConfig(level=logging.INFO,
                            format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
        return logging.getLogger(name)

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
        web_search=getattr(args, "web_search", False),
        check_external=getattr(args, "check_external", False),
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
    parser.add_argument("--web-search", action="store_true",
                        help="[tutorial] 启用 Web 搜索")
    parser.add_argument("--check-external", action="store_true",
                        help="[tutorial] 检查外部链接")

    # 代码专用参数
    parser.add_argument("--max-files", type=int, default=None,
                        help="[code] 最大优化文件数")
    parser.add_argument("--ext", nargs="+", default=None,
                        help="[code] 仅扫描指定扩展名")

    args = parser.parse_args()

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
