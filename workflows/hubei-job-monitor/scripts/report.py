#!/usr/bin/env python3
"""
湖北招聘监控 — 日报生成
汇总本次运行的所有阶段结果。
"""
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import get_output_dir, get_data_dir, setup_logger, save_json, load_json, now_iso

log = setup_logger("report")


def run():
    out_dir = get_output_dir()
    data_dir = get_data_dir()

    # 收集各阶段结果
    scrape = load_json(Path(out_dir) / "scrape-result.json", {})
    filtered = load_json(Path(out_dir) / "filter-result.json", {})
    dedup = load_json(Path(out_dir) / "dedup-result.json", {})
    notify = load_json(Path(out_dir) / "notify-result.json", {})
    seen = load_json(Path(data_dir) / "seen.json", {})

    report = {
        "timestamp": now_iso(),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "pipeline": {
            "scrape": {
                "sources_checked": scrape.get("sources_checked", 0),
                "total_items": scrape.get("total_items", 0),
            },
            "filter": {
                "input": filtered.get("input_count", 0),
                "matched": filtered.get("matched_count", 0),
            },
            "dedup": {
                "input": dedup.get("input_count", 0),
                "new": dedup.get("new_count", 0),
                "duplicate": dedup.get("duplicate_count", 0),
            },
            "notify": {
                "pushed": notify.get("pushed", False),
                "items_sent": notify.get("item_count", 0),
            },
        },
        "stats": {
            "total_seen_all_time": seen.get("total_seen", 0),
        },
        "ok": True,
    }

    save_json(Path(out_dir) / "monitor-report.json", report)

    # 保存到历史
    history_dir = Path(data_dir) / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    save_json(history_dir / f"{date_str}.json", report)

    # 输出摘要
    log.info(
        "监控摘要: 抓取 %d → 筛选 %d → 新增 %d → 推送 %s",
        scrape.get("total_items", 0),
        filtered.get("matched_count", 0),
        dedup.get("new_count", 0),
        "✅" if notify.get("pushed") else "⏭️ 无新内容",
    )


if __name__ == "__main__":
    run()
