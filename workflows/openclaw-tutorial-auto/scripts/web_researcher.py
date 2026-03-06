#!/usr/bin/env python3
"""
web_researcher.py — 网络信息搜集与结构化整理
支持 Tavily（主）+ DuckDuckGo Lite（降级）双通道搜索
为每章收集最新资料、新命令、最佳实践、安全建议等

用法:
  python web_researcher.py                         # 搜索所有已完成章节的最新信息
  python web_researcher.py --chapter 5             # 搜索指定章节
  python web_researcher.py --focus "security tips" # 额外关键词焦点
"""
import json, os, re, subprocess, sys, time
from pathlib import Path
from datetime import datetime

from utils import (
    get_project_dir,
    get_output_dir,
    read_chapter,
    find_completed_numbers,
    save_json,
    load_json,
    setup_logger,
    cfg,
    cleanup_old_caches,
)

# ── 日志 ──────────────────────────────────────────────
log = setup_logger("web_researcher")

# ── 配置项 ────────────────────────────────────────────
TAVILY_SCRIPT = cfg(
    "search.tavily_script",
    "/root/.openclaw/workspace/skills/tavily-search/scripts/search.mjs",
)
RATE_LIMIT_SECONDS = cfg("search.rate_limit_seconds", 1)
CACHE_MAX_DAYS = cfg("search.cache_max_days", 7)

RESEARCH_CACHE_DIR = os.path.join(get_output_dir(), "research-cache")

# 每章的搜索关键词映射
CHAPTER_SEARCH_TOPICS = {
    1:  ["OpenClaw install setup 2026", "OpenClaw 安装教程最新", "OpenClaw getting started guide"],
    2:  ["OpenClaw deploy environment init", "OpenClaw gateway configuration 2026", "openclaw.json settings"],
    3:  ["OpenClaw Skills plugin development", "OpenClaw SKILL.md format", "OpenClaw skill tutorial"],
    4:  ["OpenClaw skills install management", "OpenClaw ClawHub marketplace", "openclaw skill list"],
    5:  ["OpenClaw ClawHub platform skills distribution", "OpenClaw skill sharing community"],
    6:  ["OpenClaw automation scripting cron", "OpenClaw agentTurn cron job", "OpenClaw task scheduling"],
    7:  ["OpenClaw feishu lark integration bot", "OpenClaw messaging automation feishu"],
    8:  ["OpenClaw multi agent gateway", "OpenClaw agent management configuration"],
    9:  ["OpenClaw troubleshooting logs debug", "OpenClaw doctor diagnostics", "OpenClaw common errors fix"],
    10: ["OpenClaw CI/CD integration git sync", "OpenClaw workspace git management"],
    11: ["OpenClaw third party integration API", "OpenClaw Google GitHub Notion MCP"],
    12: ["OpenClaw best practices use cases 2026", "OpenClaw FAQ common questions", "AI agent automation examples"],
    13: ["OpenClaw tutorial maintenance versioning", "OpenClaw community contribution guide"],
}


# ═══════════════════════════════════════════════════════
# 搜索通道
# ═══════════════════════════════════════════════════════

def search_tavily(query: str, n: int = 5, deep: bool = False, topic: str = "general") -> dict:
    """调用 Tavily 搜索（node 脚本）"""
    if not Path(TAVILY_SCRIPT).is_file():
        log.error("Tavily 脚本不存在: %s — 请检查 config.yaml search.tavily_script", TAVILY_SCRIPT)
        return {"source": "tavily", "query": query, "data": "", "ok": False, "error": "script not found"}

    cmd = ["node", TAVILY_SCRIPT, query, "-n", str(n)]
    if deep:
        cmd.append("--deep")
    if topic != "general":
        cmd.extend(["--topic", topic])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0 and result.stdout.strip():
            return {"source": "tavily", "query": query, "data": result.stdout.strip(), "ok": True}
    except Exception as e:
        log.warning("Tavily 调用异常: %s", e)
        return {"source": "tavily", "query": query, "data": "", "ok": False, "error": str(e)}
    return {"source": "tavily", "query": query, "data": "", "ok": False}


def search_ddg_lite(query: str) -> dict:
    """DuckDuckGo Lite 降级搜索"""
    try:
        import urllib.parse
        encoded = urllib.parse.quote_plus(query)
        result = subprocess.run(
            ["curl", "-sL", "-A", "Mozilla/5.0", f"https://lite.duckduckgo.com/lite/?q={encoded}"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            links = re.findall(r'<a[^>]+href="(https?://[^"]+)"[^>]*>([^<]+)</a>', result.stdout)
            items = []
            seen = set()
            for url, title in links:
                title = title.strip()
                if title and url not in seen and "duckduckgo" not in url.lower():
                    seen.add(url)
                    items.append({"title": title, "url": url})
                    if len(items) >= 8:
                        break
            return {"source": "ddg", "query": query, "results": items, "ok": len(items) > 0}
    except Exception as e:
        log.warning("DDG 调用异常: %s", e)
        return {"source": "ddg", "query": query, "results": [], "ok": False, "error": str(e)}
    return {"source": "ddg", "query": query, "results": [], "ok": False}


# ═══════════════════════════════════════════════════════
# 缓存（使用 load_json / save_json）
# ═══════════════════════════════════════════════════════

def _cache_path(chapter_num: int) -> Path:
    date_str = datetime.now().strftime("%Y-%m-%d")
    return Path(RESEARCH_CACHE_DIR) / f"ch{chapter_num:02d}-{date_str}.json"


def load_cache(chapter_num: int) -> dict | None:
    """加载当天的搜索缓存（避免重复搜索）"""
    return load_json(_cache_path(chapter_num), default=None)


def save_cache(chapter_num: int, data: dict):
    """保存搜索缓存"""
    save_json(_cache_path(chapter_num), data)


# ═══════════════════════════════════════════════════════
# 章节研究
# ═══════════════════════════════════════════════════════

def research_chapter(chapter_num: int, extra_focus: str = "") -> dict:
    """对单个章节进行网络信息搜集"""
    # 检查缓存
    cached = load_cache(chapter_num)
    if cached:
        log.info("使用今日缓存 (ch%02d)", chapter_num)
        return cached

    queries = list(CHAPTER_SEARCH_TOPICS.get(chapter_num, [f"OpenClaw chapter {chapter_num}"]))
    if extra_focus:
        queries.append(f"OpenClaw {extra_focus}")

    news_queries = [f"OpenClaw update news 2026", f"OpenClaw latest features {chapter_num}"]

    all_findings = []
    search_log = []

    # 主搜索 (Tavily → DDG fallback)
    for q in queries[:3]:
        log.info("Tavily: %s", q)
        result = search_tavily(q, n=5)
        search_log.append({"query": q, "source": result["source"], "ok": result["ok"]})
        if result["ok"]:
            all_findings.append({
                "query": q,
                "source": "tavily",
                "content": result["data"][:2000],
            })
        else:
            log.info("DDG fallback: %s", q)
            ddg = search_ddg_lite(q)
            search_log.append({"query": q, "source": "ddg", "ok": ddg["ok"]})
            if ddg["ok"]:
                all_findings.append({
                    "query": q,
                    "source": "ddg",
                    "results": ddg["results"][:5],
                })
        time.sleep(RATE_LIMIT_SECONDS)

    # News 搜索
    for q in news_queries[:1]:
        log.info("News: %s", q)
        result = search_tavily(q, n=3, topic="news")
        search_log.append({"query": q, "source": "tavily-news", "ok": result["ok"]})
        if result["ok"]:
            all_findings.append({
                "query": q,
                "source": "tavily-news",
                "content": result["data"][:1500],
            })
        time.sleep(RATE_LIMIT_SECONDS)

    research_data = {
        "chapter": chapter_num,
        "timestamp": datetime.now().isoformat(),
        "findings_count": len(all_findings),
        "findings": all_findings,
        "search_log": search_log,
    }

    save_cache(chapter_num, research_data)
    return research_data


# ═══════════════════════════════════════════════════════
# 全量研究
# ═══════════════════════════════════════════════════════

def research_all_chapters(extra_focus: str = "") -> dict:
    """对所有已完成章节进行搜索研究"""
    out = Path(get_output_dir())
    out.mkdir(parents=True, exist_ok=True)

    # 清理过期缓存
    removed = cleanup_old_caches(RESEARCH_CACHE_DIR, max_days=CACHE_MAX_DAYS)
    if removed:
        log.info("已清理 %d 个过期缓存文件", removed)

    completed = find_completed_numbers()
    all_research = {}

    for ch_num in sorted(completed):
        ch_info = read_chapter(ch_num)
        if ch_info:
            log.info("第 %d 章: %s", ch_num, ch_info["file"])
            research = research_chapter(ch_num, extra_focus)
            all_research[ch_num] = {
                "current_state": {
                    "file": ch_info["file"],
                    "word_count": ch_info["word_count"],
                    "code_blocks": ch_info["code_blocks"],
                    "headings_count": len(ch_info["headings"]),
                },
                "research": research,
            }
        else:
            log.warning("第 %d 章: 文件不存在，跳过", ch_num)

    summary = {
        "timestamp": datetime.now().isoformat(),
        "total_chapters_researched": len(all_research),
        "chapters": all_research,
    }

    save_json(out / "web-research-summary.json", summary)
    log.info("研究完成: %d 章", len(all_research))
    return summary


# ═══════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════

def run():
    import argparse
    parser = argparse.ArgumentParser(description="网络信息搜集工具")
    parser.add_argument("--chapter", type=int, default=0, help="指定章节号 (0=全部)")
    parser.add_argument("--focus", type=str, default="", help="额外关注关键词")
    args = parser.parse_args()

    print("╔══════════════════════════════════════════════════════╗")
    print("║  🌐 网络信息搜集器 — Web Researcher                  ║")
    print("╚══════════════════════════════════════════════════════╝")

    if args.chapter > 0:
        result = research_chapter(args.chapter, args.focus)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        result = research_all_chapters(args.focus)
        print(f"\n📊 共搜集 {result['total_chapters_researched']} 章的最新信息")

    return result


if __name__ == "__main__":
    run()
