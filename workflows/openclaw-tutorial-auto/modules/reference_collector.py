#!/usr/bin/env python3
"""
reference_collector.py — 参考来源收集器 v2
===========================================
基于 Web 搜索 + 静态来源库 双通道为教程章节收集可信参考来源。
集成 web_researcher.py 的多引擎搜索能力（Tavily/Bing/Brave/DDG/百度）。

输入: {OUTPUT_DIR}/scan-report.json
输出: {OUTPUT_DIR}/references.json
"""

from datetime import datetime, timezone
from urllib.parse import urlparse
import json
import os
import re
import sys
import time

# ── 兼容 utils 导入 ────────────────────────────────
_SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

try:
    from utils import setup_logger, cfg, load_json, save_json
except ImportError:
    import logging
    def setup_logger(name):
        """setup_logger 的功能描述。

            Args:
                name: ...
            """
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
        return logging.getLogger(name)
    def cfg(key, default=None):
        """cfg 的功能描述。

            Args:
                key: ...
                default: ...
            """
        return os.environ.get(key.replace(".", "_").upper(), default)
    def save_json(path, data):
        """save_json 的功能描述。

            Args:
                path: ...
                data: ...
            """
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    def load_json(path, default=None):
        """load_json 的功能描述。

            Args:
                path: ...
                default: ...
            """
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default or {}

# ── Web 搜索引擎导入 ────────────────────────────────
_web_search_available = False
try:
    from web_researcher import (
        search_tavily, search_bing, search_brave,
        search_ddg_lite, search_baidu,
        CHAPTER_SEARCH_TOPICS,
    )
    _web_search_available = True
except ImportError:
    CHAPTER_SEARCH_TOPICS = {}

log = setup_logger("reference_collector")

OUTPUT_DIR = cfg("output_dir", os.environ.get(
    "OUTPUT_DIR", "/tmp/openclaw-tutorial-auto-reports"))
RATE_LIMIT = float(cfg("search.rate_limit_seconds", 1))
ENABLE_WEB_SEARCH = cfg("search.enable_live_search", "true").lower() in ("true", "1", "yes")

# ── 可信度量化权重 ──────────────────────────────────
CREDIBILITY_SCORES = {
    "A": 1.0,    # 官方文档、RFC、权威标准
    "B": 0.8,    # 知名社区、经官方认可的教程
    "C": 0.6,    # 博客、StackOverflow、Medium
    "D": 0.4,    # 一般网页结果
}

# ── 域名可信度映射 ────────────────────────────────
TRUSTED_DOMAINS = {
    "docs.openclaw.com": "A",
    "hub.openclaw.com": "A",
    "github.com": "A",
    "docs.docker.com": "A",
    "docs.github.com": "A",
    "modelcontextprotocol.io": "A",
    "open.feishu.cn": "A",
    "playwright.dev": "A",
    "owasp.org": "A",
    "nodejs.org": "A",
    "developer.mozilla.org": "A",
    "www.freedesktop.org": "A",
    "crontab.guru": "B",
    "stackoverflow.com": "B",
    "medium.com": "C",
    "dev.to": "C",
    "www.baidu.com": "D",
}

# ── 预定义参考来源库（种子数据 / 离线回退） ────────
BASE_REFERENCES = {
    "openclaw_core": [
        {
            "title": "OpenClaw 官方文档",
            "url": "https://docs.openclaw.com",
            "category": "official_doc",
            "credibility": "A",
            "topics": ["安装", "配置", "命令", "架构"],
        },
        {
            "title": "OpenClaw GitHub 仓库",
            "url": "https://github.com/anthropics/openclaw",
            "category": "official_doc",
            "credibility": "A",
            "topics": ["源码", "Issues", "Release", "Contributing"],
        },
        {
            "title": "ClawHub Skills 平台",
            "url": "https://hub.openclaw.com",
            "category": "official_doc",
            "credibility": "A",
            "topics": ["Skills", "市场", "安装"],
        },
    ],
    "deployment": [
        {
            "title": "Docker 官方文档",
            "url": "https://docs.docker.com",
            "category": "official_doc",
            "credibility": "A",
            "topics": ["Docker", "容器", "部署"],
        },
        {
            "title": "systemd 管理文档",
            "url": "https://www.freedesktop.org/wiki/Software/systemd/",
            "category": "official_doc",
            "credibility": "A",
            "topics": ["systemd", "服务管理", "后台运行"],
        },
    ],
    "mcp": [
        {
            "title": "Model Context Protocol 规范",
            "url": "https://modelcontextprotocol.io",
            "category": "official_doc",
            "credibility": "A",
            "topics": ["MCP", "协议", "工具集成"],
        },
        {
            "title": "MCP GitHub 仓库",
            "url": "https://github.com/modelcontextprotocol",
            "category": "official_doc",
            "credibility": "A",
            "topics": ["MCP", "SDK", "实现"],
        },
    ],
    "feishu": [
        {
            "title": "飞书开放平台文档",
            "url": "https://open.feishu.cn/document",
            "category": "official_doc",
            "credibility": "A",
            "topics": ["飞书", "机器人", "消息", "API"],
        },
    ],
    "automation": [
        {
            "title": "Cron 表达式文档",
            "url": "https://crontab.guru",
            "category": "reference",
            "credibility": "B",
            "topics": ["Cron", "定时", "调度"],
        },
        {
            "title": "GitHub Actions 文档",
            "url": "https://docs.github.com/en/actions",
            "category": "official_doc",
            "credibility": "A",
            "topics": ["CI/CD", "自动化", "GitHub"],
        },
    ],
    "security": [
        {
            "title": "OWASP 安全指南",
            "url": "https://owasp.org/www-project-top-ten/",
            "category": "reference",
            "credibility": "A",
            "topics": ["安全", "权限", "认证"],
        },
    ],
    "browser_automation": [
        {
            "title": "Playwright 官方文档",
            "url": "https://playwright.dev/docs/intro",
            "category": "official_doc",
            "credibility": "A",
            "topics": ["浏览器", "自动化", "Headless"],
        },
    ],
}

# ── 章节→主题映射 ────────────────────────────────────
CHAPTER_TOPIC_MAP = {
    1: ["openclaw_core", "deployment"],
    2: ["openclaw_core", "deployment"],
    3: ["openclaw_core"],
    4: ["openclaw_core"],
    5: ["openclaw_core"],
    6: ["openclaw_core", "automation"],
    7: ["feishu"],
    8: ["openclaw_core", "deployment"],
    9: ["openclaw_core"],
    10: ["automation"],
    11: ["openclaw_core"],
    12: ["openclaw_core"],
    13: ["automation"],
    14: ["security"],
    15: ["openclaw_core"],
    16: ["mcp"],
    17: ["browser_automation"],
    18: ["deployment"],
    19: ["deployment", "security"],
    20: ["openclaw_core"],
    21: ["feishu"],
}


# ═══════════════════════════════════════════════════════
# URL 可信度评估
# ═══════════════════════════════════════════════════════

def _assess_credibility(url: str) -> str:
    """根据域名判定来源可信等级。"""
    try:
        domain = urlparse(url).netloc.lower()
        # 精确匹配
        if domain in TRUSTED_DOMAINS:
            return TRUSTED_DOMAINS[domain]
        # 子域名匹配 (e.g. api.github.com → github.com)
        for trusted, grade in TRUSTED_DOMAINS.items():
            if domain.endswith("." + trusted) or domain == trusted:
                return grade
        # github.com 子路径通常可信
        if "github.com" in domain:
            return "A"
    except Exception:
        pass
    return "D"


def _credibility_score(grade: str) -> float:
    """可信等级转数值分。"""
    return CREDIBILITY_SCORES.get(grade, 0.4)


# ═══════════════════════════════════════════════════════
# Web 搜索集成
# ═══════════════════════════════════════════════════════

def _web_search_for_chapter(chapter_num: int, title: str) -> list:
    """
    使用 web_researcher 的多引擎搜索为章节找到额外参考来源。
    返回标准化来源列表。
    """
    if not _web_search_available or not ENABLE_WEB_SEARCH:
        return []

    # 生成搜索关键词
    queries = list(CHAPTER_SEARCH_TOPICS.get(chapter_num, []))
    if title:
        queries.insert(0, f"OpenClaw {title} tutorial reference")
    if not queries:
        queries = [f"OpenClaw chapter {chapter_num} tutorial 2026"]

    results = []
    seen_urls = set()

    # 搜索引擎优先级
    engines = [
        ("tavily", lambda q: search_tavily(q, n=3)),
        ("bing", search_bing),
        ("brave", search_brave),
    ]

    for query in queries[:2]:  # 至多 2 个查询
        for eng_name, eng_fn in engines:
            try:
                res = eng_fn(query)
                if not res.get("ok", False):
                    continue

                # Tavily 返回纯文本 data, 其他返回 results 列表
                if eng_name == "tavily" and res.get("data"):
                    # 从 Tavily 文本中提取 URL
                    urls = re.findall(r"https?://[^\s\)\"'<>]+", res["data"])
                    for url in urls[:5]:
                        url = url.rstrip(".,;:)")
                        if url not in seen_urls and _is_valid_ref_url(url):
                            seen_urls.add(url)
                            cred = _assess_credibility(url)
                            results.append({
                                "title": _extract_domain_title(url),
                                "url": url,
                                "category": "web_search",
                                "credibility": cred,
                                "credibility_score": _credibility_score(cred),
                                "source_engine": eng_name,
                                "topics": [],
                            })
                elif res.get("results"):
                    for item in res["results"][:5]:
                        url = item.get("url", "")
                        title_text = item.get("title", "")
                        if url and url not in seen_urls and _is_valid_ref_url(url):
                            seen_urls.add(url)
                            cred = _assess_credibility(url)
                            results.append({
                                "title": title_text or _extract_domain_title(url),
                                "url": url,
                                "category": "web_search",
                                "credibility": cred,
                                "credibility_score": _credibility_score(cred),
                                "source_engine": eng_name,
                                "topics": [],
                            })

                if results:
                    break  # 找到结果则不继续降级
            except Exception as e:
                log.debug(f"搜索失败 ({eng_name}): {e}")
                continue

        if len(results) >= 5:
            break
        time.sleep(RATE_LIMIT)

    # 按可信度排序
    results.sort(key=lambda r: -r.get("credibility_score", 0))
    return results[:8]


def _is_valid_ref_url(url: str) -> bool:
    """过滤无效/不适合作参考的URL。"""
    blacklist = [
        "google.com/search", "bing.com/search", "baidu.com/s",
        "duckduckgo.com", "brave.com/search", "twitter.com",
        "facebook.com", "instagram.com", "tiktok.com",
    ]
    url_lower = url.lower()
    return (
        url_lower.startswith("http")
        and not any(bl in url_lower for bl in blacklist)
        and len(url) < 300
    )


def _extract_domain_title(url: str) -> str:
    """从URL提取可读的默认标题。"""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.replace("www.", "")
        path = parsed.path.strip("/")
        if path:
            # 取最后一段路径作为标题
            slug = path.split("/")[-1].replace("-", " ").replace("_", " ")
            if slug and not slug.startswith("index"):
                return f"{domain} — {slug[:60]}"
        return domain
    except Exception:
        return url[:80]


# ═══════════════════════════════════════════════════════
# 章节来源收集
# ═══════════════════════════════════════════════════════

def collect_for_chapter(chapter_num: int, chapter_data: dict = None,
                        use_web_search: bool = False) -> dict:
    """
    为单个章节收集参考来源。

    双通道策略:
    1. 静态来源库 (BASE_REFERENCES) — 即时可用
    2. Web 搜索 (web_researcher) — 可选，提供最新动态来源
    """
    topics = CHAPTER_TOPIC_MAP.get(chapter_num, ["openclaw_core"])
    refs = []
    seen_urls = set()

    # === 通道 1: 静态来源库 ===
    for topic in topics:
        for ref in BASE_REFERENCES.get(topic, []):
            if ref["url"] not in seen_urls:
                ref_copy = dict(ref)
                ref_copy["credibility_score"] = _credibility_score(ref.get("credibility", "B"))
                refs.append(ref_copy)
                seen_urls.add(ref["url"])

    # 始终包含 OpenClaw 核心来源
    for ref in BASE_REFERENCES.get("openclaw_core", []):
        if ref["url"] not in seen_urls:
            ref_copy = dict(ref)
            ref_copy["credibility_score"] = _credibility_score(ref.get("credibility", "B"))
            refs.append(ref_copy)
            seen_urls.add(ref["url"])

    # === 通道 2: Web 搜索 (动态) ===
    web_refs = []
    if use_web_search:
        title = chapter_data.get("title", "") if chapter_data else ""
        web_refs = _web_search_for_chapter(chapter_num, title)
        for ref in web_refs:
            if ref["url"] not in seen_urls:
                refs.append(ref)
                seen_urls.add(ref["url"])

    # === 检查已有来源，避免推荐重复的 ===
    existing_links = set()
    if chapter_data:
        content = chapter_data.get("content", {})
        ext_links = content.get("links_external", 0)
        # 这里无法获取具体URL，但可以标注已有来源数
        existing_count = ext_links
    else:
        existing_count = 0

    # 按可信度排序
    refs.sort(key=lambda r: -r.get("credibility_score", 0))

    # 生成搜索关键词
    title = chapter_data.get("title", "") if chapter_data else ""
    search_queries = _generate_search_queries(chapter_num, title)

    # 生成 Markdown 参考来源块
    md_block = _format_references_markdown(refs)

    return {
        "chapter": chapter_num,
        "title": title,
        "references": refs,
        "static_count": len(refs) - len(web_refs),
        "web_search_count": len(web_refs),
        "existing_external_links": existing_count,
        "search_queries": search_queries,
        "recommended_references_block": md_block,
    }


def _generate_search_queries(chapter_num: int, title: str) -> list:
    """根据章节标题生成搜索关键词。"""
    queries = []
    if title:
        queries.append(f"OpenClaw {title}")
        queries.append(f"OpenClaw {title} 教程")
        queries.append(f"OpenClaw {title} best practice 2026")
    queries.append(f"OpenClaw tutorial chapter {chapter_num}")
    # 附加来自 web_researcher 的关键词
    for q in CHAPTER_SEARCH_TOPICS.get(chapter_num, []):
        if q not in queries:
            queries.append(q)
    return queries[:6]


def _format_references_markdown(refs: list) -> str:
    """格式化参考来源为 Markdown 表格（含可信度）。"""
    lines = [
        "## 参考来源",
        "",
        "| 来源 | 链接 | 可信度 | 说明 |",
        "|------|------|--------|------|",
    ]
    for ref in refs[:10]:  # 最多 10 条
        title = ref.get("title", "")
        url = ref.get("url", "")
        cred = ref.get("credibility", "D")
        topics = ", ".join(ref.get("topics", [])[:3])
        source = ref.get("source_engine", "")
        desc = topics if topics else (f"via {source}" if source else "")
        lines.append(f"| {title} | {url} | {cred} | {desc} |")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════
# 全量收集
# ═══════════════════════════════════════════════════════

def collect_all(scan_report: dict = None, use_web_search: bool = False) -> dict:
    """为所有章节收集参考来源。

    Args:
        scan_report: 扫描报告数据
        use_web_search: 是否启用 Web 搜索（默认 False，pipeline 中按需开启）
    """
    if scan_report is None:
        scan_path = os.path.join(OUTPUT_DIR, "scan-report.json")
        scan_report = load_json(scan_path)

    chapters = scan_report.get("chapters", []) if scan_report else []
    log.info(f"收集 {len(chapters)} 个章节的参考来源...")
    if use_web_search and _web_search_available:
        log.info("  Web 搜索: 已启用")
    elif use_web_search and not _web_search_available:
        log.warning("  Web 搜索: web_researcher.py 不可用，回退到静态来源")
        use_web_search = False

    results = []
    total_static = 0
    total_web = 0

    for ch in chapters:
        if "error" in ch:
            continue
        ch_num = ch.get("number", 0)

        # 只对缺少参考来源的章节执行 web 搜索
        has_refs = ch.get("content", {}).get("has_references", False)
        ch_use_web = use_web_search and not has_refs

        result = collect_for_chapter(ch_num, ch, use_web_search=ch_use_web)
        results.append(result)
        total_static += result.get("static_count", 0)
        total_web += result.get("web_search_count", 0)

        status = "已有" if has_refs else ("Web搜索" if ch_use_web else "需添加")
        log.info(f"  [{ch_num:02d}] {len(result['references'])} 条来源 ({status})")

    # 补充缺失章节的来源
    missing = scan_report.get("missing_chapters", []) if scan_report else []
    for ch_num in missing:
        result = collect_for_chapter(ch_num, use_web_search=use_web_search)
        results.append(result)

    report = {
        "collect_time": datetime.now(tz=timezone.utc).isoformat(),
        "total_chapters": len(results),
        "web_search_enabled": use_web_search,
        "static_refs": total_static,
        "web_search_refs": total_web,
        "chapters": results,
        "total_unique_refs": len(set(
            ref["url"] for r in results for ref in r.get("references", [])
        )),
    }

    return report


def run():
    """主入口。"""
    import argparse
    parser = argparse.ArgumentParser(description="参考来源收集器")
    parser.add_argument("--web-search", action="store_true", help="启用 Web 搜索")
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    report = collect_all(use_web_search=args.web_search)

    out_path = os.path.join(OUTPUT_DIR, "references.json")
    save_json(out_path, report)
    log.info(f"参考来源报告已保存: {out_path}")
    log.info(f"  总独立来源: {report['total_unique_refs']}")
    log.info(f"  静态来源: {report['static_refs']} | Web搜索: {report['web_search_refs']}")

    return report


if __name__ == "__main__":
    run()
