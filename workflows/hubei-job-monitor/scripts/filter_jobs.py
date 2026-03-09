#!/usr/bin/env python3
"""
湖北招聘监控 — 硕士岗位筛选
从 scrape-result.json 中筛选匹配学历要求的公告。
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

    # 排除检查
    for kw in exclude:
        if kw in title:
            return False

    # 标题匹配（高优先级）
    for kw in keywords:
        if kw in title:
            return True

    # 正文匹配
    for kw in keywords:
        if kw in text:
            return True

    # 特征模式匹配：学历要求字段中出现硕士/研究生
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
    """地域过滤（如果配置了地域关键词）"""
    keywords = cfg("filter.region_keywords", [])
    if not keywords:
        return True  # 未配置则不过滤

    title = item.get("title", "")
    text = item.get("detail_text", "")[:500]
    combined = f"{title} {text}"

    return any(kw in combined for kw in keywords)


def matches_major(item: dict) -> bool:
    """专业过滤（如果配置了专业关键词）"""
    keywords = cfg("filter.major_keywords", [])
    if not keywords:
        return True

    text = item.get("detail_text", "")
    return any(kw in text for kw in keywords)


def run():
    out_dir = get_output_dir()
    scrape_file = Path(out_dir) / "scrape-result.json"
    scrape_data = load_json(scrape_file, {"items": []})

    items = scrape_data.get("items", [])
    if not items:
        log.info("无公告需要筛选")
        save_json(Path(out_dir) / "filter-result.json", {
            "timestamp": now_iso(),
            "input_count": 0,
            "matched_count": 0,
            "items": [],
        })
        return

    matched = []
    for item in items:
        if matches_education(item) and matches_region(item) and matches_major(item):
            matched.append(item)

    result = {
        "timestamp": now_iso(),
        "input_count": len(items),
        "matched_count": len(matched),
        "items": matched,
    }

    save_json(Path(out_dir) / "filter-result.json", result)
    log.info("筛选完成: %d/%d 条匹配硕士要求", len(matched), len(items))


if __name__ == "__main__":
    run()
