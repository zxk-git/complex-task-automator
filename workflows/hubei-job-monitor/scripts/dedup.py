#!/usr/bin/env python3
"""
湖北招聘监控 — 去重
排除已推送过的公告，基于 seen.json 状态文件。
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import (
    cfg, get_output_dir, get_data_dir, setup_logger,
    save_json, load_json, make_job_id, now_iso,
)

log = setup_logger("dedup")


def run():
    out_dir = get_output_dir()
    data_dir = get_data_dir()

    filter_file = Path(out_dir) / "filter-result.json"
    filter_data = load_json(filter_file, {"items": []})
    items = filter_data.get("items", [])

    # 加载已推送状态
    state_file = Path(data_dir) / cfg("dedup.state_file", "seen.json")
    seen = load_json(state_file, {"jobs": {}, "last_cleanup": ""})
    seen_jobs = seen.get("jobs", {})

    # 清理过期记录
    retention_days = cfg("dedup.retention_days", 90)
    cutoff = (datetime.now() - timedelta(days=retention_days)).isoformat()
    cleaned = {k: v for k, v in seen_jobs.items() if v.get("first_seen", "") > cutoff}
    if len(cleaned) < len(seen_jobs):
        log.info("清理 %d 条过期记录", len(seen_jobs) - len(cleaned))
        seen_jobs = cleaned

    # 去重（公告级）
    new_items = []
    for item in items:
        job_id = make_job_id(item["source_id"], item["title"], item.get("url", ""))
        if job_id not in seen_jobs:
            item["_job_id"] = job_id
            new_items.append(item)

    # 去重（岗位级，matched_jobs 跟随公告去重）
    matched_jobs = filter_data.get("matched_jobs", [])
    new_titles = {item["title"] for item in new_items}
    new_matched_jobs = [
        job for job in matched_jobs
        if job.get("_announcement_title", "") in new_titles
    ]

    result = {
        "timestamp": now_iso(),
        "input_count": len(items),
        "new_count": len(new_items),
        "duplicate_count": len(items) - len(new_items),
        "items": new_items,
        "matched_jobs": new_matched_jobs,
        "matched_jobs_count": len(new_matched_jobs),
    }

    save_json(Path(out_dir) / "dedup-result.json", result)
    log.info("去重完成: %d 新 / %d 已见", len(new_items), len(items) - len(new_items))

    # 保存更新后的 seen 状态（包括新发现的 + 清理后的旧记录）
    for item in new_items:
        seen_jobs[item["_job_id"]] = {
            "title": item["title"],
            "source": item["source_id"],
            "first_seen": now_iso(),
            "url": item.get("url", ""),
        }

    save_json(state_file, {
        "jobs": seen_jobs,
        "last_cleanup": now_iso(),
        "total_seen": len(seen_jobs),
    })


if __name__ == "__main__":
    run()
