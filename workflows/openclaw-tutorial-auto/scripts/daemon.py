#!/usr/bin/env python3
"""
daemon.py — 24/7 自动化调度器入口
供 OpenClaw agentTurn Cron 调用的统一入口脚本。
支持多种运行模式：
  - batch      : 批量生成章节
  - health     : 健康检查与状态报告
  - full       : 先健康检查 → 批量生成 → 再健康检查
  - optimize   : 搜索网络最新信息 → 分析 → 优化章节 → Git 推送
  - continuous : full + optimize 组合（24/7 持续运行模式）
  - status     : 仅输出当前进度

用法:
  python daemon.py                       # 默认 continuous 模式
  python daemon.py --mode optimize       # 仅搜索+优化
  python daemon.py --mode continuous     # 完整24/7循环
  python daemon.py --mode batch          # 仅批量生成
  python daemon.py --mode health         # 仅健康检查
  python daemon.py --mode status         # 仅查看进度
  python daemon.py --max-chapters 5      # 每轮最多5章
  python daemon.py --dry-run             # 空运行
"""
import argparse
import importlib
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# 确保脚本目录在 Python 路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from utils import (
    get_project_dir,
    get_output_dir,
    save_json,
    load_json,
    parse_outline,
    find_completed_chapters,
    setup_logger,
    cfg,
    banner,
    get_expected_chapters,
)

log = setup_logger("daemon")


# ─────────────────────────────────────────────────────
# 环境变量初始化
# ─────────────────────────────────────────────────────

def set_env_defaults(args):
    """设置环境变量默认值（路径由 utils 统一管理）"""
    os.environ.setdefault("PROJECT_DIR", get_project_dir())
    os.environ.setdefault("OUTPUT_DIR", get_output_dir())
    os.environ.setdefault("SCRIPTS_DIR", SCRIPT_DIR)

    if args.max_chapters:
        os.environ["MAX_CHAPTERS_PER_RUN"] = str(args.max_chapters)
    if args.cooldown:
        os.environ["COOLDOWN_SECONDS"] = str(args.cooldown)
    if args.dry_run:
        os.environ["DRY_RUN"] = "true"


# ─────────────────────────────────────────────────────
# 各阶段执行器
# ─────────────────────────────────────────────────────

def run_health_check() -> dict:
    """执行健康检查"""
    banner("健康检查", "🏥")
    try:
        import health_check
        health_check.run()

        result_file = Path(get_output_dir()) / "health-check.json"
        return load_json(result_file, {})
    except Exception as e:
        log.error(f"健康检查阶段异常: {e}")
        return {"status": "error", "error": str(e)}


def run_batch() -> dict:
    """执行批量章节生成"""
    banner("批量章节生成", "📚")
    try:
        import batch_runner
        batch_runner.run()

        result_file = Path(get_output_dir()) / "batch-result.json"
        return load_json(result_file, {})
    except Exception as e:
        log.error(f"批量生成阶段异常: {e}")
        return {"status": "error", "error": str(e)}


def run_status() -> dict:
    """仅输出当前状态"""
    banner("当前进度", "📊")
    try:
        proj_dir = get_project_dir()
        outline = parse_outline(proj_dir)
        chapters = find_completed_chapters(proj_dir)
        total = len(outline) or get_expected_chapters()
        remaining = total - len(chapters)

        # 尝试读取 batch 状态
        batch_state = load_json(
            Path(get_output_dir()) / "batch-state.json", {}
        )

        status = {
            "timestamp": datetime.now().isoformat(),
            "progress": {
                "completed": len(chapters),
                "total": total,
                "remaining": remaining,
                "percentage": round(len(chapters) / max(total, 1) * 100, 1),
            },
            "batch_runs": batch_state.get("total_runs", 0) if batch_state else 0,
            "last_run": batch_state.get("last_run_at") if batch_state else None,
            "all_complete": remaining == 0,
        }
        log.info("当前进度: %d/%d (%.1f%%)",
                 status["progress"]["completed"],
                 status["progress"]["total"],
                 status["progress"]["percentage"])
        return status
    except Exception as e:
        log.error(f"状态查询异常: {e}")
        return {"status": "error", "error": str(e)}


def run_optimize(args) -> dict:
    """优化模式: 搜索网络最新信息 → 优化章节 → Git 推送"""
    banner("网络搜索 + 章节优化", "🔄")

    # 通过环境变量传递参数（避免 sys.argv hack）
    if args.max_chapters:
        os.environ["MAX_OPTIMIZE_CHAPTERS"] = str(args.max_chapters)
    else:
        os.environ.setdefault("MAX_OPTIMIZE_CHAPTERS", "3")
    if args.dry_run:
        os.environ["DRY_RUN"] = "true"

    try:
        import optimize_chapter
        # 重新加载以获取最新环境变量
        importlib.reload(optimize_chapter)
        result = optimize_chapter.run()
        return result or {}
    except Exception as e:
        log.error(f"优化阶段异常: {e}")
        return {"status": "error", "error": str(e)}


def run_full(args) -> dict:
    """完整模式: 健康检查 → 批量生成 → 健康检查"""
    results = {
        "mode": "full",
        "started_at": datetime.now().isoformat(),
        "stages": [],
    }

    # 1. 前置健康检查
    try:
        pre_health = run_health_check()
    except Exception as e:
        log.error(f"前置健康检查失败: {e}")
        pre_health = {"status": "error", "error": str(e)}
    results["stages"].append({"stage": "pre-health", "result": pre_health})

    # 检查是否所有章节已完成
    if pre_health.get("all_complete"):
        log.info("所有章节已完成，跳过批量生成")
        results["stages"].append({
            "stage": "batch",
            "result": {"status": "skipped", "reason": "all_complete"},
        })
    # 检查是否有严重错误
    elif pre_health.get("alert_count", 0) > 0 and not pre_health.get("overall_healthy", True):
        log.warning("存在严重预警，跳过批量生成")
        results["stages"].append({
            "stage": "batch",
            "result": {"status": "skipped", "reason": "unhealthy"},
        })
    else:
        # 2. 批量生成
        try:
            batch_result = run_batch()
        except Exception as e:
            log.error(f"批量生成失败: {e}")
            batch_result = {"status": "error", "error": str(e)}
        results["stages"].append({"stage": "batch", "result": batch_result})

        # 3. 后置健康检查
        time.sleep(2)
        try:
            post_health = run_health_check()
        except Exception as e:
            log.error(f"后置健康检查失败: {e}")
            post_health = {"status": "error", "error": str(e)}
        results["stages"].append({"stage": "post-health", "result": post_health})

    results["finished_at"] = datetime.now().isoformat()
    results["duration"] = (
        datetime.fromisoformat(results["finished_at"])
        - datetime.fromisoformat(results["started_at"])
    ).total_seconds()

    # 保存结果
    save_json(Path(get_output_dir()) / "daemon-result.json", results)

    banner("调度器执行完毕", "📋")
    log.info("耗时: %.1fs | 阶段: %d", results["duration"], len(results["stages"]))
    return results


def run_continuous(args) -> dict:
    """持续运行模式: 健康检查 → 生成(如有) → 搜索优化 → 健康检查"""
    results = {
        "mode": "continuous",
        "started_at": datetime.now().isoformat(),
        "stages": [],
    }

    # 1. 前置健康检查
    try:
        pre_health = run_health_check()
    except Exception as e:
        log.error(f"前置健康检查失败: {e}")
        pre_health = {"status": "error", "error": str(e)}
    results["stages"].append({"stage": "pre-health", "result": pre_health})

    # 2. 如果有未完成章节，先生成
    if not pre_health.get("all_complete"):
        if pre_health.get("overall_healthy", True) or pre_health.get("alert_count", 0) == 0:
            try:
                batch_result = run_batch()
            except Exception as e:
                log.error(f"批量生成失败: {e}")
                batch_result = {"status": "error", "error": str(e)}
            results["stages"].append({"stage": "batch", "result": batch_result})
            time.sleep(5)
        else:
            log.warning("存在严重预警，跳过批量生成")
            results["stages"].append({
                "stage": "batch",
                "result": {"status": "skipped", "reason": "unhealthy"},
            })

    # 3. 搜索网络最新信息并优化已有章节（核心 24/7 环节）
    banner("网络搜索 + 智能优化", "🌐")
    try:
        optimize_result = run_optimize(args)
    except Exception as e:
        log.error(f"优化阶段失败: {e}")
        optimize_result = {"status": "error", "error": str(e)}
    results["stages"].append({"stage": "optimize", "result": optimize_result})

    # 4. 后置健康检查
    time.sleep(2)
    try:
        post_health = run_health_check()
    except Exception as e:
        log.error(f"后置健康检查失败: {e}")
        post_health = {"status": "error", "error": str(e)}
    results["stages"].append({"stage": "post-health", "result": post_health})

    results["finished_at"] = datetime.now().isoformat()
    results["duration"] = (
        datetime.fromisoformat(results["finished_at"])
        - datetime.fromisoformat(results["started_at"])
    ).total_seconds()

    # 保存结果
    save_json(Path(get_output_dir()) / "daemon-result.json", results)

    optimized = optimize_result.get("optimized", 0) if isinstance(optimize_result, dict) else 0
    banner("持续优化调度器执行完毕", "📋")
    log.info("耗时: %.1fs | 阶段: %d | 优化章节: %d",
             results["duration"], len(results["stages"]), optimized)
    return results


# ─────────────────────────────────────────────────────
# 入口
# ─────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="24/7 教程自动化调度器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--mode",
        choices=["full", "batch", "health", "optimize", "continuous", "status"],
        default="continuous",
        help="运行模式 (默认: continuous)",
    )
    parser.add_argument(
        "--max-chapters",
        type=int,
        default=None,
        help="每轮最多生成章节数 (默认: 3)",
    )
    parser.add_argument(
        "--cooldown",
        type=int,
        default=None,
        help="章节间冷却时间/秒 (默认: 30)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="空运行模式（不实际生成）",
    )

    args = parser.parse_args()
    set_env_defaults(args)

    banner("OpenClaw 24/7 教程自动化调度器", "🤖")
    log.info("模式: %s | 项目: %s", args.mode, get_project_dir())

    dispatch = {
        "continuous": lambda: run_continuous(args),
        "full":       lambda: run_full(args),
        "optimize":   lambda: run_optimize(args),
        "batch":      lambda: run_batch(),
        "health":     lambda: run_health_check(),
        "status":     lambda: run_status(),
    }

    handler = dispatch.get(args.mode)
    if handler:
        return handler()
    else:
        log.error("未知模式: %s", args.mode)
        return None


if __name__ == "__main__":
    main()
