#!/usr/bin/env python3
"""
suggestion_enricher.py — 优化建议引用增强器
============================================
为每条代码优化建议附加最佳实践参考链接（静态 + Web 搜索）。

架构:
  1. 静态引用: 来自 IMPROVEMENT_TEMPLATES 中的 static_references（权威、离线可用）
  2. Web 搜索: 通过 web_researcher 引擎搜索实时最佳实践（可选，按需开启）

输出: 每条 improvement 增加 "references" 字段
"""

import hashlib
import json
import os
import re
import sys
import time

from modules.compat import setup_logger, cfg

log = setup_logger("suggestion_enricher")

# ── Web 搜索引擎 (可选) ──
_web_search_available = False
try:
    from web_researcher import (
        search_tavily, search_bing, search_brave,
        search_ddg_lite,
    )
    _web_search_available = True
except ImportError:
    pass

# ── 模板引用 ──
try:
    from modules.code_analyzer import IMPROVEMENT_TEMPLATES
except ImportError:
    try:
        from code_analyzer import IMPROVEMENT_TEMPLATES
    except ImportError:
        IMPROVEMENT_TEMPLATES = {}

# ── 域名可信度映射 ──
_DOMAIN_CREDIBILITY = {
    # A-tier: 官方文档、标准
    "python.org": "A", "peps.python.org": "A",
    "docs.python.org": "A", "doc.rust-lang.org": "A",
    "go.dev": "A", "pkg.go.dev": "A",
    "developer.mozilla.org": "A", "typescriptlang.org": "A",
    "nodejs.org": "A", "oracle.com": "A",
    "docs.oracle.com": "A", "cppreference.com": "A",
    "gnu.org": "A", "google.github.io": "A",
    "rust-lang.github.io": "A", "doxygen.nl": "A",
    "wiki.sei.cmu.edu": "A", "jsdoc.app": "A",
    "mypy.readthedocs.io": "A", "refactoring.guru": "A",
    "shellcheck.net": "A",
    # B-tier: 知名社区
    "stackoverflow.com": "B", "github.com": "B",
    "en.wikipedia.org": "B", "realpython.com": "B",
    "baeldung.com": "B", "geeksforgeeks.org": "B",
    "dev.to": "B", "medium.com": "B",
    "oreilly.com": "B",
    # C-tier: 博客
    "blog.": "C", "tutorial": "C",
}

# ── 搜索缓存 ──
_search_cache = {}
_CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", ".cache", "enricher")
_CACHE_MAX_AGE = 7 * 86400  # 7 days


def _get_domain(url: str) -> str:
    """提取域名。"""
    m = re.match(r'https?://(?:www\.)?([^/]+)', url)
    return m.group(1).lower() if m else ""


def _assess_credibility(url: str) -> tuple:
    """评估 URL 可信度。返回 (grade, score)。"""
    domain = _get_domain(url)
    for pattern, grade in _DOMAIN_CREDIBILITY.items():
        if pattern in domain:
            scores = {"A": 1.0, "B": 0.8, "C": 0.6}
            return grade, scores.get(grade, 0.4)
    return "D", 0.4


def _load_disk_cache(cache_key: str) -> list | None:
    """从磁盘加载缓存。"""
    path = os.path.join(_CACHE_DIR, f"{cache_key}.json")
    if os.path.exists(path):
        try:
            age = time.time() - os.path.getmtime(path)
            if age < _CACHE_MAX_AGE:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return None


def _save_disk_cache(cache_key: str, data: list):
    """保存到磁盘缓存。"""
    os.makedirs(_CACHE_DIR, exist_ok=True)
    path = os.path.join(_CACHE_DIR, f"{cache_key}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def _web_search_for_suggestion(query: str, max_results: int = 5) -> list:
    """
    通过搜索引擎查找最佳实践参考。
    降级链: tavily → bing → brave → ddg
    """
    if not _web_search_available:
        return []

    refs = []
    engines = [
        ("tavily", lambda q: search_tavily(q, n=max_results)),
        ("bing", search_bing),
        ("brave", search_brave),
        ("ddg", search_ddg_lite),
    ]

    for engine_name, search_fn in engines:
        try:
            result = search_fn(query)
            if not result.get("ok"):
                continue

            # Tavily 返回 data (文本)，需要提取 URL
            if engine_name == "tavily" and "data" in result:
                urls = re.findall(r'https?://[^\s\'"<>]+', result["data"])
                for url in urls[:max_results]:
                    cred, score = _assess_credibility(url)
                    refs.append({
                        "title": _get_domain(url),
                        "url": url.rstrip("/"),
                        "credibility": cred,
                        "credibility_score": score,
                        "source_engine": engine_name,
                    })
            # Bing/Brave/DDG 返回 results[{title, url}]
            elif "results" in result:
                for r in result["results"][:max_results]:
                    url = r.get("url", "")
                    if not url:
                        continue
                    cred, score = _assess_credibility(url)
                    refs.append({
                        "title": r.get("title", _get_domain(url)),
                        "url": url.rstrip("/"),
                        "credibility": cred,
                        "credibility_score": score,
                        "source_engine": engine_name,
                    })

            if refs:
                break  # 找到结果就不降级
        except Exception as e:
            log.debug(f"搜索引擎 {engine_name} 失败: {e}")
            continue

    return refs


def _dedupe_and_rank(refs: list, max_refs: int = 5) -> list:
    """去重并按可信度排序。"""
    seen = set()
    unique = []
    for r in refs:
        url = r.get("url", "").rstrip("/").lower()
        if url and url not in seen:
            seen.add(url)
            unique.append(r)
    # A > B > C > D，同级按是否来自静态优先
    score_map = {"A": 1.0, "B": 0.8, "C": 0.6, "D": 0.4}
    unique.sort(key=lambda x: (
        -score_map.get(x.get("credibility", "D"), 0.4),
        0 if x.get("source_engine") is None else 1,  # 静态引用优先
    ))
    return unique[:max_refs]


def _collect_refs_for_template(tmpl_key: str, language: str,
                                use_web_search: bool = True) -> list:
    """收集某模板的所有参考链接。"""
    tmpl = IMPROVEMENT_TEMPLATES.get(tmpl_key, {})

    # 1. 静态引用
    refs = []
    for sr in tmpl.get("static_references", []):
        refs.append({
            "title": sr["title"],
            "url": sr["url"],
            "credibility": sr.get("credibility", "B"),
            "credibility_score": {"A": 1.0, "B": 0.8, "C": 0.6}.get(
                sr.get("credibility", "B"), 0.4),
        })

    # 2. Web 搜索 (可选)
    if use_web_search and _web_search_available:
        queries = tmpl.get("search_queries", [])
        if queries:
            query = queries[0].format(language=language, year="2026")
            # 缓存 key = template_key + language
            cache_key = hashlib.md5(f"{tmpl_key}:{language}:{query}".encode()).hexdigest()[:12]

            # 内存缓存
            if cache_key in _search_cache:
                refs.extend(_search_cache[cache_key])
            else:
                # 磁盘缓存
                cached = _load_disk_cache(cache_key)
                if cached is not None:
                    _search_cache[cache_key] = cached
                    refs.extend(cached)
                else:
                    web_refs = _web_search_for_suggestion(query)
                    _search_cache[cache_key] = web_refs
                    _save_disk_cache(cache_key, web_refs)
                    refs.extend(web_refs)
                    # Rate limit
                    time.sleep(float(cfg("search.rate_limit_seconds", "1")))

    return _dedupe_and_rank(refs)


def enrich_suggestions(analysis_report: dict,
                       use_web_search: bool = True,
                       max_refs_per_suggestion: int = 3) -> dict:
    """
    为分析报告中的每条建议附加参考链接。

    Args:
        analysis_report: code_analyzer.analyze_all() 的输出
        use_web_search: 是否启用 Web 搜索 (默认 True)
        max_refs_per_suggestion: 每条建议最多附加引用数

    Returns:
        增强后的 analysis_report (原地修改 + 返回)
    """
    improvements = analysis_report.get("improvements", [])
    if not improvements:
        log.info("无优化建议，跳过引用增强")
        return analysis_report

    # 按 template_key + language 缓存，避免重复搜索
    ref_cache = {}
    total_refs = 0
    web_refs = 0

    log.info(f"开始引用增强: {len(improvements)} 条建议, "
             f"web_search={'ON' if use_web_search and _web_search_available else 'OFF'}")

    for imp in improvements:
        tmpl_key = imp.get("type", "")
        lang = imp.get("language", "")
        if not lang:
            # 从文件扩展名推断
            fpath = imp.get("file", "")
            ext_map = {".py": "python", ".js": "javascript", ".ts": "typescript",
                       ".go": "go", ".sh": "shell", ".rs": "rust",
                       ".c": "c", ".h": "c", ".cpp": "cpp", ".java": "java"}
            ext = os.path.splitext(fpath)[1].lower()
            lang = ext_map.get(ext, "")

        cache_key = f"{tmpl_key}:{lang}"
        if cache_key not in ref_cache:
            refs = _collect_refs_for_template(tmpl_key, lang, use_web_search)
            ref_cache[cache_key] = refs

        imp_refs = ref_cache[cache_key][:max_refs_per_suggestion]
        imp["references"] = imp_refs
        total_refs += len(imp_refs)
        web_refs += sum(1 for r in imp_refs if r.get("source_engine"))

    # 汇总统计 (包含去重计数)
    all_urls = set()
    for imp in improvements:
        for r in imp.get("references", []):
            all_urls.add(r.get("url", "").rstrip("/").lower())
    unique_count = len(all_urls)

    analysis_report["enrichment"] = {
        "total_references": total_refs,
        "unique_references": unique_count,
        "web_search_refs": web_refs,
        "static_refs": total_refs - web_refs,
        "web_search_enabled": use_web_search and _web_search_available,
        "unique_templates_enriched": len(ref_cache),
    }

    log.info(f"引用增强完成: {unique_count} 条唯一引用 ({total_refs} 次附加) "
             f"(静态:{total_refs - web_refs}, Web:{web_refs}), "
             f"覆盖 {len(ref_cache)} 种建议类型")

    return analysis_report


# ── CLI 测试 ──
if __name__ == "__main__":
    import pprint

    # 模拟一个分析报告
    test_report = {
        "improvements": [
            {"type": "add_docstring", "file": "test.py", "description": "为 test.py::main 添加 docstring"},
            {"type": "add_doxygen", "file": "server.c", "description": "为 handle_request 添加 Doxygen"},
            {"type": "add_javadoc", "file": "App.java", "description": "为 App.main 添加 Javadoc"},
            {"type": "add_go_doc", "file": "main.go", "description": "为 NewServer 添加文档注释"},
            {"type": "reduce_complexity", "file": "big.py", "description": "简化 big.py::process (CC=15)"},
        ],
    }

    enriched = enrich_suggestions(test_report, use_web_search=False)
    for imp in enriched["improvements"]:
        print(f"\n{'='*60}")
        print(f"  {imp['type']}: {imp['description']}")
        for ref in imp.get("references", []):
            print(f"    📎 [{ref['credibility']}] {ref['title']}")
            print(f"       {ref['url']}")
    print(f"\n统计: {enriched.get('enrichment', {})}")
