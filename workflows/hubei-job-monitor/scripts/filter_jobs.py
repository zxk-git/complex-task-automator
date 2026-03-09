#!/usr/bin/env python3
"""
湖北招聘监控 — 硕士岗位筛选 + 工科专业匹配
两级筛选：
  1. 公告级：学历关键词筛选（标题/正文含硕士/研究生）
  2. 岗位级：从 Excel 岗位表按专业关键词匹配具体岗位
输出 filter-result.json:
  - items: 匹配的公告（含 excel_jobs）
  - matched_jobs: 专业匹配的具体岗位列表（用于推送）
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import cfg, get_output_dir, setup_logger, save_json, load_json, now_iso

log = setup_logger("filter_jobs")


def matches_education(item: dict) -> bool:
    """判断公告是否匹配学历关键词"""
    keywords = cfg("filter.education_keywords", ["硕士", "研究生"])
    exclude = cfg("filter.exclude_keywords", [])

    title = item.get("title", "")
    text = item.get("detail_text", "")
    combined = f"{title} {text}"

    for kw in exclude:
        if kw in title:
            return False

    for kw in keywords:
        if kw in title or kw in text:
            return True

    edu_patterns = [
        r"学历[^\n]{0,10}(硕士|研究生)",
        r"(硕士|研究生)[^\n]{0,10}(及以上|以上|学历|学位)",
        r"(招聘|岗位)[^\n]{0,30}(硕士|研究生)",
        r"全日制[^\n]{0,10}(硕士|研究生)",
    ]
    for pattern in edu_patterns:
        if re.search(pattern, combined):
            return True

    return False


def matches_region(item: dict) -> bool:
    """地域过滤"""
    keywords = cfg("filter.region_keywords", [])
    if not keywords:
        return True
    combined = f"{item.get('title', '')} {item.get('detail_text', '')[:500]}"
    return any(kw in combined for kw in keywords)


def match_job_major(job: dict) -> bool:
    """
    判断单个岗位的专业是否匹配工科关键词。
    仅匹配 major（专业要求）字段，不搜描述和岗位名（避免误匹配）。
    如果未配置 major_keywords，则所有硕士岗位都匹配。
    """
    keywords = cfg("filter.major_keywords", [])
    if not keywords:
        return True

    major = job.get("major", "")
    if not major:
        return False

    return any(kw in major for kw in keywords)


def run():
    out_dir = get_output_dir()
    scrape_file = Path(out_dir) / "scrape-result.json"
    scrape_data = load_json(scrape_file, {"items": []})

    excel_file = Path(out_dir) / "excel-jobs.json"
    excel_data = load_json(excel_file, {"items": []})

    items = scrape_data.get("items", [])
    excel_items = excel_data.get("items", [])

    if not items:
        log.info("无公告需要筛选")
        save_json(Path(out_dir) / "filter-result.json", {
            "timestamp": now_iso(),
            "input_count": 0,
            "matched_count": 0,
            "matched_jobs": [],
            "items": [],
        })
        return

    # ── 第一级：公告级学历筛选 ──
    matched_announcements = []
    for item in items:
        if matches_education(item) and matches_region(item):
            matched_announcements.append(item)

    # Excel 补充：有硕士岗位的公告也拉进来
    matched_titles = {item["title"] for item in matched_announcements}
    excel_by_title = {}
    for job in excel_items:
        t = job.get("_announcement_title", "")
        excel_by_title.setdefault(t, []).append(job)

    for item in items:
        if item["title"] not in matched_titles and item["title"] in excel_by_title:
            matched_announcements.append(item)

    # 挂载 Excel 岗位到公告
    for item in matched_announcements:
        title = item.get("title", "")
        excel_jobs = excel_by_title.get(title, [])
        if excel_jobs:
            item["excel_jobs"] = excel_jobs
            item["excel_job_count"] = len(excel_jobs)

    # ── 第二级：岗位级专业匹配 ──
    matched_jobs = []
    for job in excel_items:
        if match_job_major(job):
            matched_jobs.append(job)

    # 按招聘单位分组统计
    by_employer = {}
    for job in matched_jobs:
        emp = job.get("employer_display", "") or job.get("employer", "未知")
        by_employer.setdefault(emp, []).append(job)

    log.info("筛选完成: 公告 %d/%d, Excel岗位 %d/%d (工科匹配)",
             len(matched_announcements), len(items),
             len(matched_jobs), len(excel_items))
    log.info("工科岗位分布：%s",
             ", ".join(f"{k}({len(v)})" for k, v in sorted(by_employer.items(), key=lambda x: -len(x[1]))[:8]))

    result = {
        "timestamp": now_iso(),
        "input_count": len(items),
        "matched_count": len(matched_announcements),
        "excel_total": excel_data.get("total_jobs", 0),
        "excel_master": excel_data.get("master_jobs", 0),
        "matched_jobs_count": len(matched_jobs),
        "items": matched_announcements,
        "matched_jobs": matched_jobs,
    }

    save_json(Path(out_dir) / "filter-result.json", result)


if __name__ == "__main__":
    run()
