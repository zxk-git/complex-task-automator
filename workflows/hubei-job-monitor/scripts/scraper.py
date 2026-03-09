#!/usr/bin/env python3
"""
湖北招聘监控 — 网页抓取器
支持多数据源，自动适配不同网站结构。
"""
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import (
    cfg, get_output_dir, setup_logger, save_json, now_iso, get_http_session,
)

log = setup_logger("scraper")


def scrape_list_page(source: dict, session) -> list:
    """抓取列表页，返回公告条目列表"""
    url = source["url"]
    selectors = source.get("selectors", {})
    base_url = source.get("base_url", "")
    url_filter = source.get("url_filter", "")

    log.info("抓取 [%s] %s", source["id"], url)

    try:
        resp = session.get(url, timeout=cfg("http.timeout", 30))
        resp.raise_for_status()
    except Exception as e:
        log.error("抓取失败 [%s]: %s", source["id"], e)
        return []

    # 自动检测编码
    if resp.apparent_encoding:
        resp.encoding = resp.apparent_encoding

    soup = BeautifulSoup(resp.text, "lxml" if "lxml" in sys.modules else "html.parser")

    # 尝试多个选择器
    list_selectors = selectors.get("list", "").split(",")
    items = []
    for sel in list_selectors:
        sel = sel.strip()
        if sel:
            items = soup.select(sel)
            if items:
                break

    if not items:
        # 回退策略：查找所有 <li> 内含 <a> 的元素
        items = [li for li in soup.find_all("li") if li.find("a")]
        log.debug("[%s] 使用回退策略，找到 %d 个元素", source["id"], len(items))

    results = []
    max_items = source.get("max_items", 50)
    for item in items[:max_items]:
        link_el = item.select_one(selectors.get("link", "a"))
        if not link_el:
            continue

        title = link_el.get_text(strip=True)
        href = link_el.get("href", "")

        if not title or len(title) < 4:
            continue

        # 分离标题末尾的日期（如 "xxx公告2026-03-04"）
        date_in_title = re.search(r"(\d{4}-\d{2}-\d{2})$", title)
        if date_in_title:
            title = title[:date_in_title.start()].strip()

        # 拼接完整 URL（相对路径基于实际页面 URL）
        if href and not href.startswith("http"):
            href = urljoin(url, href)

        # URL 过滤（只保留匹配的链接）
        if url_filter and href and url_filter not in href:
            continue

        # 提取日期
        date_text = ""
        date_selectors = selectors.get("date", "").split(",")
        for ds in date_selectors:
            ds = ds.strip()
            if ds:
                date_el = item.select_one(ds)
                if date_el:
                    date_text = date_el.get_text(strip=True)
                    break

        if not date_text:
            # 从文本中提取日期模式
            text = item.get_text()
            date_match = re.search(r"(\d{4}[-/.]\d{1,2}[-/.]\d{1,2})", text)
            if date_match:
                date_text = date_match.group(1)

        results.append({
            "source_id": source["id"],
            "source_name": source["name"],
            "title": title,
            "url": href,
            "date": date_text,
        })

    log.info("[%s] 抓取到 %d 条公告", source["id"], len(results))
    return results


def scrape_detail_page(url: str, session) -> dict:
    """抓取公告详情页，提取正文和附件链接"""
    try:
        resp = session.get(url, timeout=cfg("http.timeout", 30))
        resp.raise_for_status()
        if resp.apparent_encoding:
            resp.encoding = resp.apparent_encoding
    except Exception as e:
        log.debug("详情页抓取失败: %s — %s", url, e)
        return {"text": "", "attachments": []}

    soup = BeautifulSoup(resp.text, "lxml" if "lxml" in sys.modules else "html.parser")

    # 提取正文
    content_el = (
        soup.select_one(".article-content, .TRS_Editor, .content, .news-content, #zoom, .detail-content, .main-content")
        or soup.select_one("article")
        or soup.find("div", class_=re.compile(r"content|article|detail|text|body", re.I))
    )
    text = content_el.get_text(separator="\n", strip=True) if content_el else ""

    # 提取附件（Excel / PDF）
    attachments = []
    for a in soup.find_all("a", href=True):
        href = a["href"].lower()
        if any(ext in href for ext in [".xls", ".xlsx", ".pdf", ".doc", ".docx"]):
            full_url = urljoin(url, a["href"])
            attachments.append({
                "name": a.get_text(strip=True) or Path(full_url).name,
                "url": full_url,
                "type": Path(full_url).suffix.lstrip(".").lower(),
            })

    return {"text": text[:5000], "attachments": attachments}


def run():
    sources = cfg("sources", [])
    enabled_sources = [s for s in sources if s.get("enabled", True)]

    if not enabled_sources:
        log.warning("没有启用的数据源")
        save_json(Path(get_output_dir()) / "scrape-result.json", {
            "timestamp": now_iso(),
            "sources_checked": 0,
            "total_items": 0,
            "items": [],
        })
        return

    session = get_http_session()
    all_items = []

    for source in enabled_sources:
        source_type = source.get("type", "list_page")

        if source_type == "list_page":
            items = scrape_list_page(source, session)
        else:
            log.warning("不支持的数据源类型: %s", source_type)
            items = []

        # 对每条公告抓取详情（根据 detail_mode 策略）
        detail_mode = source.get("detail_mode", "all")
        edu_keywords = cfg("filter.education_keywords", ["硕士", "研究生"])

        for item in items:
            should_fetch = False
            if detail_mode == "all":
                should_fetch = bool(item.get("url"))
            elif detail_mode == "title_match":
                title = item.get("title", "")
                should_fetch = any(kw in title for kw in edu_keywords) or "人才引进" in title
            # detail_mode == "none" → never fetch

            if should_fetch:
                detail = scrape_detail_page(item["url"], session)
                item["detail_text"] = detail["text"]
                item["attachments"] = detail["attachments"]
            else:
                item["detail_text"] = ""
                item["attachments"] = []

        all_items.extend(items)

    # 保存结果
    result = {
        "timestamp": now_iso(),
        "sources_checked": len(enabled_sources),
        "total_items": len(all_items),
        "items": all_items,
    }

    out_file = Path(get_output_dir()) / "scrape-result.json"
    save_json(out_file, result)
    log.info("抓取完成: %d 个数据源, %d 条公告", len(enabled_sources), len(all_items))


if __name__ == "__main__":
    run()
