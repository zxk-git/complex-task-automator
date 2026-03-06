#!/usr/bin/env python3
"""
openclaw-tutorial-auto 项目 — 环境与项目状态检查
输出 JSON 格式检查结果
"""
import json, shutil
from pathlib import Path
from datetime import datetime

from utils import (
    get_project_dir,
    get_output_dir,
    parse_outline,
    find_completed_numbers,
    get_expected_chapters,
    save_json,
    check_disk_health,
    setup_logger,
    cfg,
    get_encoding,
)

log = setup_logger("check_env")


def check_tool(name: str) -> bool:
    return shutil.which(name) is not None


def run():
    PROJECT_DIR = get_project_dir()
    OUTPUT_DIR = get_output_dir()

    results = {
        "timestamp": datetime.now().isoformat(),
        "project_dir": PROJECT_DIR,
        "checks": {},
        "ok": True,
        "errors": [],
        "warnings": [],
    }

    # 1. 环境检查
    env_checks = {
        "python3":  check_tool("python3"),
        "node":     check_tool("node"),
        "git":      check_tool("git"),
        "curl":     check_tool("curl"),
        "openclaw": check_tool("openclaw"),
    }
    results["checks"]["environment"] = env_checks
    for tool, ok in env_checks.items():
        if not ok and tool in ("python3", "git"):
            results["errors"].append(f"缺少必需工具: {tool}")
            results["ok"] = False
            log.error("缺少必需工具: %s", tool)
        elif not ok:
            results["warnings"].append(f"缺少可选工具: {tool}")
            log.warning("缺少可选工具: %s", tool)

    # 2. 项目目录检查
    proj = Path(PROJECT_DIR)
    dir_exists = proj.is_dir()
    results["checks"]["project_exists"] = dir_exists
    if not dir_exists:
        results["errors"].append(f"项目目录不存在: {PROJECT_DIR}")
        results["ok"] = False
        log.error("项目目录不存在: %s", PROJECT_DIR)
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    # 3. 基础文件检查
    required_files = ["README.md", "OUTLINE.md"]
    file_check = {}
    for f in required_files:
        exists = (proj / f).is_file()
        file_check[f] = exists
        if not exists:
            results["errors"].append(f"缺少必需文件: {f}")
            results["ok"] = False
    results["checks"]["required_files"] = file_check

    # 4. 章节文件扫描（使用 utils 共享函数）
    completed_nums = find_completed_numbers(PROJECT_DIR)
    all_files = sorted([f.name for f in proj.iterdir() if f.is_file()])
    chapter_files = sorted([f for f in all_files if f[:2].isdigit() and f.endswith(".md")])
    results["checks"]["all_files"] = all_files
    results["checks"]["chapter_files"] = chapter_files
    results["checks"]["chapter_count"] = len(completed_nums)

    # 5. 大纲解析（使用 utils.parse_outline）
    outline_items = parse_outline(PROJECT_DIR)
    results["checks"]["outline_items"] = [
        f"{it['number']}. {it['title']}" for it in outline_items
    ]
    results["checks"]["outline_count"] = len(outline_items)

    # 6. 进度
    total = len(outline_items) if outline_items else get_expected_chapters()
    done = len(completed_nums)
    results["checks"]["progress"] = {
        "completed": done,
        "total": total,
        "percentage": round(done / total * 100, 1) if total > 0 else 0,
        "remaining": total - done,
    }

    # 7. 磁盘/文件大小
    total_size = sum(f.stat().st_size for f in proj.iterdir() if f.is_file())
    results["checks"]["total_size_bytes"] = total_size
    results["checks"]["total_size_kb"] = round(total_size / 1024, 1)
    results["checks"]["disk"] = check_disk_health(PROJECT_DIR)

    # 写出结果（使用 utils.save_json）
    out_file = Path(OUTPUT_DIR) / "01-env-check.json"
    save_json(out_file, results)
    log.info("环境检查完成 — %d 项通过，%d 错误，%d 警告",
             sum(env_checks.values()), len(results["errors"]), len(results["warnings"]))
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run()
