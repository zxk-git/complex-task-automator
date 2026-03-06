#!/usr/bin/env python3
"""
batch_runner.py — 批量章节生成器
循环调用 workflow-full 工作流，自动生成所有剩余章节。
"""
import os
import sys
import json
import time
import subprocess
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from utils import (
    get_project_dir, get_output_dir, get_scripts_dir, get_expected_chapters,
    parse_outline, find_completed_numbers, load_json, save_json,
    setup_logger, cfg, banner,
)

log = setup_logger("batch_runner")

PROJECT_DIR = get_project_dir()
OUTPUT_DIR = get_output_dir()
SCRIPTS_DIR = get_scripts_dir()

WORKFLOW_DIR = os.path.dirname(SCRIPT_DIR)
WORKFLOW_FILE = os.environ.get(
    "WORKFLOW_FILE",
    os.path.join(WORKFLOW_DIR, "workflow-full.yaml"),
)
TASK_RUN = os.environ.get(
    "TASK_RUN",
    cfg("execution.task_run", "/root/.openclaw/workspace/skills/complex-task-automator/scripts/task-run.py"),
)

# 批量参数
MAX_CHAPTERS_PER_RUN = int(os.environ.get("MAX_CHAPTERS_PER_RUN", cfg("batch.max_chapters_per_run", 3)))
COOLDOWN_SECONDS = int(os.environ.get("COOLDOWN_SECONDS", cfg("batch.cooldown_seconds", 30)))
MAX_CONSECUTIVE_FAILURES = int(os.environ.get("MAX_CONSECUTIVE_FAILURES", cfg("batch.max_consecutive_failures", 3)))
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"
EXPECTED_CHAPTERS = get_expected_chapters()
STATE_FILE = Path(OUTPUT_DIR) / "batch-state.json"


# ── 工具函数 ──────────────────────────────────────────
def load_state() -> dict:
    """加载批量运行状态"""
    data = load_json(STATE_FILE)
    if data:
        return data
    return {
        "created_at": datetime.now().isoformat(),
        "runs": [],
        "completed_chapters": [],
        "failed_chapters": [],
        "total_runs": 0,
        "last_run_at": None,
    }


def get_missing_chapters() -> list:
    """获取未完成章节列表（按编号排序）"""
    outline = parse_outline()
    completed = find_completed_numbers()
    missing = [ch for ch in outline if ch["number"] not in completed]
    missing.sort(key=lambda x: x["number"])
    return missing


def run_workflow_for_chapter(chapter_num: int) -> dict:
    """调用 task-run.py 执行单个章节的工作流"""
    start = time.time()
    result = {
        "chapter": chapter_num,
        "started_at": datetime.now().isoformat(),
        "status": "unknown",
        "duration": 0,
        "output": "",
        "error": "",
    }

    if DRY_RUN:
        log.info(f"[DRY_RUN] 跳过实际执行: 第{chapter_num}章")
        result["status"] = "dry_run"
        result["duration"] = 0
        return result

    cmd = [
        sys.executable,
        TASK_RUN,
        WORKFLOW_FILE,
        "--vars",
        f"CHAPTER_NUM={chapter_num}",
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 分钟超时
            cwd=os.path.dirname(TASK_RUN),
        )
        result["output"] = proc.stdout[-2000:] if proc.stdout else ""
        result["error"] = proc.stderr[-1000:] if proc.stderr else ""
        result["status"] = "success" if proc.returncode == 0 else "failed"
        result["return_code"] = proc.returncode
    except subprocess.TimeoutExpired:
        result["status"] = "timeout"
        result["error"] = "工作流执行超时 (>600s)"
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)

    result["duration"] = round(time.time() - start, 2)
    result["finished_at"] = datetime.now().isoformat()
    return result


# ── 主流程 ────────────────────────────────────────────
def run():
    banner("批量章节生成器 — Batch Runner", "📚")

    state = load_state()
    missing = get_missing_chapters()
    completed_set = find_completed_numbers()

    log.info(f"进度: {len(completed_set)}/{EXPECTED_CHAPTERS} 章已完成")
    log.info(f"待生成: {len(missing)} 章")
    log.info(f"每轮最多生成: {MAX_CHAPTERS_PER_RUN} 章")
    log.info(f"冷却间隔: {COOLDOWN_SECONDS}s")

    if not missing:
        log.info("所有章节已完成！无需生成。")
        result = {
            "status": "all_complete",
            "timestamp": datetime.now().isoformat(),
            "total_chapters": EXPECTED_CHAPTERS,
            "completed": len(completed_set),
        }
        save_json(STATE_FILE, state)
        log.info(json.dumps(result, ensure_ascii=False, indent=2))
        return

    # 本轮要处理的章节
    batch = missing[: MAX_CHAPTERS_PER_RUN]
    consecutive_failures = 0
    batch_results = []

    for i, chapter in enumerate(batch):
        num = chapter["number"]
        title = chapter["title"]

        log.info(f"{'─'*50}")
        log.info(f"[{i+1}/{len(batch)}] 第{num}章: {title}")
        log.info(f"开始时间: {datetime.now().strftime('%H:%M:%S')}")

        # 执行工作流
        run_result = run_workflow_for_chapter(num)
        batch_results.append(run_result)

        if run_result["status"] in ("success", "dry_run"):
            log.info(f"{'成功' if run_result['status'] == 'success' else '[DRY_RUN] 已验证'} (耗时 {run_result['duration']}s)")
            consecutive_failures = 0
            if run_result["status"] == "success":
                entry = {"chapter": num, "title": title, "at": run_result.get("finished_at", datetime.now().isoformat())}
                if num not in {c["chapter"] for c in state["completed_chapters"]}:
                    state["completed_chapters"].append(entry)
        else:
            log.warning(f"失败: {run_result['status']}")
            if run_result["error"]:
                log.warning(f"错误: {run_result['error'][:200]}")
            consecutive_failures += 1
            state["failed_chapters"].append(
                {
                    "chapter": num,
                    "title": title,
                    "status": run_result["status"],
                    "error": run_result["error"][:500],
                    "at": datetime.now().isoformat(),
                }
            )

        # 检查连续失败
        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            log.warning(f"连续失败 {consecutive_failures} 次，停止批量生成")
            break

        # 冷却（最后一章不需要）
        if i < len(batch) - 1 and COOLDOWN_SECONDS > 0:
            log.info(f"冷却 {COOLDOWN_SECONDS}s ...")
            time.sleep(COOLDOWN_SECONDS)

    # 更新状态
    run_record = {
        "run_id": state["total_runs"] + 1,
        "timestamp": datetime.now().isoformat(),
        "chapters_attempted": [r["chapter"] for r in batch_results],
        "chapters_succeeded": [
            r["chapter"] for r in batch_results if r["status"] in ("success", "dry_run")
        ],
        "chapters_failed": [
            r["chapter"] for r in batch_results if r["status"] not in ("success", "dry_run")
        ],
        "total_duration": sum(r["duration"] for r in batch_results),
    }
    state["runs"].append(run_record)
    state["total_runs"] += 1
    state["last_run_at"] = datetime.now().isoformat()
    save_json(STATE_FILE, state)

    # 重新检查进度
    new_completed = find_completed_numbers()
    remaining = EXPECTED_CHAPTERS - len(new_completed)

    # 汇总
    banner("批量生成汇总", "📊")
    succeeded = len(run_record["chapters_succeeded"])
    failed = len(run_record["chapters_failed"])
    log.info(f"本轮: 成功 {succeeded}, 失败 {failed}")
    log.info(f"总进度: {len(new_completed)}/{EXPECTED_CHAPTERS} ({round(len(new_completed)/EXPECTED_CHAPTERS*100, 1)}%)")
    log.info(f"剩余: {remaining} 章")
    log.info(f"总耗时: {run_record['total_duration']:.1f}s")

    # 输出 JSON 结果（供工作流引擎消费）
    summary = {
        "status": "all_complete" if remaining == 0 else "in_progress",
        "timestamp": datetime.now().isoformat(),
        "batch": run_record,
        "progress": {
            "completed": len(new_completed),
            "total": EXPECTED_CHAPTERS,
            "remaining": remaining,
            "percentage": round(len(new_completed) / EXPECTED_CHAPTERS * 100, 1),
        },
        "next_action": "none" if remaining == 0 else "continue_batch",
    }

    # 保存结果
    save_json(Path(OUTPUT_DIR) / "batch-result.json", summary)
    log.info(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run()
