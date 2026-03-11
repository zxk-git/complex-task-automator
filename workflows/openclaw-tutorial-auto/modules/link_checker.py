#!/usr/bin/env python3
"""
link_checker.py — 教程链路断链检测模块
========================================
扫描教程所有 Markdown 文件中的链接：
  - 内部链接 (.md inter-file, #anchor)
  - 外部链接 (HTTP/HTTPS)

检测维度:
  1. 内部 .md 链接: 目标文件是否存在
  2. 锚点链接: 目标 heading / id 是否存在
  3. 外部 URL: HTTP HEAD 探活 (可选, 带超时)
  4. 图片链接: 图片文件是否存在

输出: {OUTPUT_DIR}/link-check-report.json
"""

from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, unquote
import hashlib
import json
import os
import re
import sys
import time

import concurrent.futures

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

log = setup_logger("link_checker")

PROJECT_DIR = cfg("project_dir", os.environ.get(
    "PROJECT_DIR", "/root/.openclaw/workspace/zxk-private/openclaw-tutorial-auto"))
OUTPUT_DIR = cfg("output_dir", os.environ.get(
    "OUTPUT_DIR", "/tmp/openclaw-tutorial-auto-reports"))

# ── 配置常量 ────────────────────────────────────────
HTTP_TIMEOUT = 10          # 外部 URL 探活超时 (秒)
MAX_CONCURRENT_HTTP = 5    # HTTP 并发数
MAX_RETRIES = 1            # HTTP 重试次数
CACHE_FILE = "link-check-cache.json"  # 缓存文件名
CACHE_TTL_HOURS = 24       # 缓存有效期 (小时)


# ═══════════════════════════════════════════════════════
# 链接提取
# ═══════════════════════════════════════════════════════

def _extract_links(text: str, filepath: str) -> list:
    """
    从 Markdown 文本中提取所有链接。
    返回 list[dict]: {type, text, target, line, raw}
    """
    links = []
    lines = text.split("\n")
    in_code_block = False

    for line_num, line in enumerate(lines, 1):
        # 跳过代码块内的链接
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue

        # 标准 Markdown 链接: [text](target)
        for m in re.finditer(r'\[([^\]]*)\]\(([^)]+)\)', line):
            link_text = m.group(1)
            target = m.group(2).strip()

            # 分类
            if target.startswith("http://") or target.startswith("https://"):
                link_type = "external"
            elif target.startswith("#"):
                link_type = "anchor"
            elif target.startswith("mailto:"):
                link_type = "mailto"
                continue  # skip mailto
            else:
                link_type = "internal"

            links.append({
                "type": link_type,
                "text": link_text,
                "target": target,
                "line": line_num,
                "raw": m.group(0),
            })

        # 图片链接: ![alt](src)
        for m in re.finditer(r'!\[([^\]]*)\]\(([^)]+)\)', line):
            target = m.group(2).strip()
            if target.startswith("http://") or target.startswith("https://"):
                link_type = "image_external"
            else:
                link_type = "image_internal"
            links.append({
                "type": link_type,
                "text": m.group(1),
                "target": target,
                "line": line_num,
                "raw": m.group(0),
            })

    return links


def _extract_headings_as_anchors(text: str) -> set:
    """
    从 Markdown 提取所有标题生成的锚点 ID。
    GitHub 风格: 小写, 空格→-, 去除特殊字符, CJK 保留。
    """
    anchors = set()
    for m in re.finditer(r'^(#{1,6})\s+(.+)$', text, re.MULTILINE):
        title = m.group(2).strip()
        # GitHub 风格锚点生成
        anchor = title.lower()
        anchor = re.sub(r'[^\w\u4e00-\u9fff\s-]', '', anchor)
        anchor = anchor.strip().replace(' ', '-')
        # 去除连续 -
        anchor = re.sub(r'-+', '-', anchor)
        anchors.add(anchor)
    return anchors


# ═══════════════════════════════════════════════════════
# 内部链接校验
# ═══════════════════════════════════════════════════════

def _check_internal_link(link: dict, project_dir: str,
                         file_anchors_cache: dict) -> dict:
    """
    校验内部 .md 链接。
    检查: 文件存在 + 锚点存在(如有)。
    """
    target = link["target"]
    # 分离文件路径和锚点
    if "#" in target:
        file_part, anchor_part = target.split("#", 1)
    else:
        file_part = target
        anchor_part = None

    file_part = unquote(file_part)
    result = {
        **link,
        "status": "ok",
        "issues": [],
    }

    # 文件存在性
    if file_part:
        target_path = os.path.join(project_dir, file_part)
        if not os.path.exists(target_path):
            result["status"] = "broken"
            result["issues"].append(f"文件不存在: {file_part}")
            return result

        # 如果有锚点，检查锚点
        if anchor_part:
            anchors = file_anchors_cache.get(file_part)
            if anchors is None:
                # 加载并缓存
                try:
                    with open(target_path, encoding="utf-8") as f:
                        content = f.read()
                    anchors = _extract_headings_as_anchors(content)
                    file_anchors_cache[file_part] = anchors
                except Exception:
                    anchors = set()
                    file_anchors_cache[file_part] = anchors

            if anchor_part.lower() not in anchors:
                result["status"] = "broken_anchor"
                result["issues"].append(f"锚点不存在: #{anchor_part}")
    else:
        # 纯锚点链接 (#section) — 需要在源文件中检查
        # 此时 anchor_part 已有值
        pass  # 由 anchor 检查单独处理

    return result


def _check_anchor_link(link: dict, source_anchors: set) -> dict:
    """校验纯锚点链接 (#section)。"""
    anchor = link["target"].lstrip("#")
    result = {
        **link,
        "status": "ok",
        "issues": [],
    }
    if anchor.lower() not in source_anchors:
        result["status"] = "broken_anchor"
        result["issues"].append(f"锚点不存在: #{anchor}")
    return result


# ═══════════════════════════════════════════════════════
# 外部 URL 探活
# ═══════════════════════════════════════════════════════

def _check_external_url(url: str, timeout: int = HTTP_TIMEOUT,
                        retries: int = MAX_RETRIES) -> dict:
    """
    HTTP HEAD 探活外部 URL。
    返回 {url, status, http_code, latency_ms, error}。
    """
    import urllib.request
    import urllib.error

    result = {"url": url, "status": "unknown", "http_code": 0,
              "latency_ms": 0, "error": None}

    for attempt in range(1 + retries):
        start = time.time()
        try:
            req = urllib.request.Request(
                url, method="HEAD",
                headers={
                    "User-Agent": "Mozilla/5.0 (OpenClaw-LinkChecker/1.0)",
                    "Accept": "*/*",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result["http_code"] = resp.status
                result["latency_ms"] = round((time.time() - start) * 1000)
                if 200 <= resp.status < 400:
                    result["status"] = "ok"
                elif resp.status == 403:
                    result["status"] = "forbidden"
                elif resp.status == 404:
                    result["status"] = "not_found"
                else:
                    result["status"] = "error"
                return result
        except urllib.error.HTTPError as e:
            result["http_code"] = e.code
            result["latency_ms"] = round((time.time() - start) * 1000)
            if e.code == 403:
                # 许多站点拦截 HEAD, 认为可达
                result["status"] = "forbidden_but_reachable"
                return result
            elif e.code == 404:
                result["status"] = "not_found"
                return result
            elif e.code == 405:
                # Method Not Allowed — 尝试 GET
                try:
                    req2 = urllib.request.Request(
                        url, headers={
                            "User-Agent": "Mozilla/5.0 (OpenClaw-LinkChecker/1.0)",
                        },
                    )
                    with urllib.request.urlopen(req2, timeout=timeout) as resp2:
                        result["http_code"] = resp2.status
                        result["status"] = "ok" if 200 <= resp2.status < 400 else "error"
                        result["latency_ms"] = round((time.time() - start) * 1000)
                        return result
                except Exception:
                    result["status"] = "method_not_allowed"
                    return result
            else:
                result["error"] = f"HTTP {e.code}"
        except urllib.error.URLError as e:
            result["error"] = str(e.reason)
            result["latency_ms"] = round((time.time() - start) * 1000)
            result["status"] = "unreachable"
        except Exception as e:
            result["error"] = str(e)
            result["latency_ms"] = round((time.time() - start) * 1000)
            result["status"] = "error"

        # 重试前等待
        if attempt < retries:
            time.sleep(1)

    return result


def _load_url_cache(cache_path: str) -> dict:
    """加载 URL 探活缓存。"""
    if not os.path.exists(cache_path):
        return {}
    try:
        data = load_json(cache_path, {})
        now = time.time()
        # 过滤过期条目
        return {
            url: entry for url, entry in data.items()
            if now - entry.get("checked_at", 0) < CACHE_TTL_HOURS * 3600
        }
    except Exception:
        return {}


def _save_url_cache(cache_path: str, cache: dict):
    """保存 URL 探活缓存。"""
    save_json(cache_path, cache)


# ═══════════════════════════════════════════════════════
# 章节级别检查
# ═══════════════════════════════════════════════════════

def check_chapter(filepath: str, project_dir: str,
                  file_anchors_cache: dict,
                  check_external: bool = False,
                  url_cache: dict = None) -> dict:
    """
    检查单个章节文件中的所有链接。

    Args:
        filepath: 章节文件路径
        project_dir: 项目根目录
        file_anchors_cache: 文件锚点缓存 (共享, 跨章节)
        check_external: 是否检查外部 URL
        url_cache: URL 探活缓存

    Returns:
        dict: 检查结果
    """
    fname = os.path.basename(filepath)
    try:
        with open(filepath, encoding="utf-8") as f:
            text = f.read()
    except Exception as e:
        return {"file": fname, "error": str(e), "links": [], "broken": []}

    links = _extract_links(text, filepath)
    source_anchors = _extract_headings_as_anchors(text)
    # 缓存本文件锚点
    file_anchors_cache[fname] = source_anchors

    results = []
    broken = []
    external_urls_to_check = []

    for link in links:
        if link["type"] == "internal" or link["type"] == "image_internal":
            result = _check_internal_link(link, project_dir, file_anchors_cache)
            results.append(result)
            if result["status"] != "ok":
                broken.append(result)

        elif link["type"] == "anchor":
            result = _check_anchor_link(link, source_anchors)
            results.append(result)
            if result["status"] != "ok":
                broken.append(result)

        elif link["type"] in ("external", "image_external"):
            if check_external:
                external_urls_to_check.append(link)
            else:
                results.append({**link, "status": "skipped", "issues": []})

    # 批量检查外部 URL
    if external_urls_to_check and check_external:
        seen_urls = {}
        for link in external_urls_to_check:
            url = link["target"]
            if url in seen_urls:
                # 复用同 URL 结果
                result = {**link, **seen_urls[url]}
                results.append(result)
                if result["status"] not in ("ok", "forbidden_but_reachable", "skipped"):
                    broken.append(result)
                continue

            # 检查缓存
            if url_cache and url in url_cache:
                cached = url_cache[url]
                r = {
                    **link,
                    "status": cached["status"],
                    "http_code": cached.get("http_code", 0),
                    "issues": cached.get("issues", []),
                    "cached": True,
                }
                results.append(r)
                seen_urls[url] = {"status": r["status"], "http_code": r.get("http_code", 0), "issues": r["issues"]}
                if r["status"] not in ("ok", "forbidden_but_reachable", "skipped"):
                    broken.append(r)
                continue

            # 实际探活
            check_result = _check_external_url(url)
            issues = []
            if check_result["status"] == "not_found":
                issues.append(f"404 Not Found")
            elif check_result["status"] == "unreachable":
                issues.append(f"无法访问: {check_result.get('error', '')}")
            elif check_result["status"] == "error":
                issues.append(f"错误: {check_result.get('error', '')}")

            r = {
                **link,
                "status": check_result["status"],
                "http_code": check_result.get("http_code", 0),
                "latency_ms": check_result.get("latency_ms", 0),
                "issues": issues,
            }
            results.append(r)
            seen_urls[url] = {"status": r["status"], "http_code": r.get("http_code", 0), "issues": issues}

            # 更新缓存
            if url_cache is not None:
                url_cache[url] = {
                    "status": check_result["status"],
                    "http_code": check_result.get("http_code", 0),
                    "latency_ms": check_result.get("latency_ms", 0),
                    "issues": issues,
                    "checked_at": time.time(),
                }

            if r["status"] not in ("ok", "forbidden_but_reachable", "skipped"):
                broken.append(r)

    # 统计
    ch_match = re.match(r"(\d+)", fname)
    ch_num = int(ch_match.group(1)) if ch_match else 0

    return {
        "file": fname,
        "chapter": ch_num,
        "total_links": len(links),
        "internal": sum(1 for l in links if l["type"] in ("internal", "image_internal")),
        "external": sum(1 for l in links if l["type"] in ("external", "image_external")),
        "anchors": sum(1 for l in links if l["type"] == "anchor"),
        "broken_count": len(broken),
        "broken": broken,
        "all_links": results,
    }


# ═══════════════════════════════════════════════════════
# 全量检查入口
# ═══════════════════════════════════════════════════════

def check_all(project_dir: str = None, check_external: bool = False,
              scan_report: dict = None) -> dict:
    """
    检查教程仓库所有链接。

    Args:
        project_dir: 项目目录
        check_external: 是否检查外部 URL (默认 False, 耗时)
        scan_report: 可选, 传入扫描报告以复用文件列表

    Returns:
        dict: 完整检查报告
    """
    project_dir = project_dir or PROJECT_DIR
    log.info(f"断链检测: {project_dir}")
    log.info(f"  外部URL检查: {'启用' if check_external else '禁用'}")

    # 发现 Markdown 文件
    md_files = sorted(
        f for f in os.listdir(project_dir)
        if f.endswith(".md") and not f.endswith(".bak")
    )

    # 共享缓存
    file_anchors_cache = {}
    url_cache_path = os.path.join(OUTPUT_DIR, CACHE_FILE)
    url_cache = _load_url_cache(url_cache_path) if check_external else None

    results = []
    total_broken = 0

    for fname in md_files:
        filepath = os.path.join(project_dir, fname)
        result = check_chapter(
            filepath, project_dir, file_anchors_cache,
            check_external=check_external, url_cache=url_cache,
        )
        results.append(result)
        total_broken += result["broken_count"]

        status_icon = "✅" if result["broken_count"] == 0 else "❌"
        log.info(f"  {status_icon} {fname}: "
                  f"{result['total_links']} links, "
                  f"{result['broken_count']} broken")

    # 保存 URL 缓存
    if url_cache:
        _save_url_cache(url_cache_path, url_cache)

    # 全局碎链汇总
    all_broken = []
    for r in results:
        for b in r.get("broken", []):
            all_broken.append({
                "file": r["file"],
                "chapter": r.get("chapter", 0),
                **b,
            })

    # 按严重程度排序: broken > broken_anchor > not_found > unreachable > error
    severity_order = {
        "broken": 0, "not_found": 1, "broken_anchor": 2,
        "unreachable": 3, "error": 4,
    }
    all_broken.sort(key=lambda x: severity_order.get(x.get("status", ""), 99))

    report = {
        "check_time": datetime.now(tz=timezone.utc).isoformat(),
        "project_dir": project_dir,
        "check_external": check_external,
        "total_files": len(results),
        "total_links": sum(r["total_links"] for r in results),
        "total_internal": sum(r["internal"] for r in results),
        "total_external": sum(r["external"] for r in results),
        "total_anchors": sum(r["anchors"] for r in results),
        "total_broken": total_broken,
        "broken_summary": all_broken,
        "chapters": results,
        "health_score": round(
            100 * (1 - total_broken / max(sum(r["total_links"] for r in results), 1)),
            1
        ),
    }

    return report


def run():
    """主入口。"""
    import argparse
    parser = argparse.ArgumentParser(description="教程断链检测")
    parser.add_argument("--check-external", action="store_true",
                        help="启用外部 URL 探活 (耗时)")
    parser.add_argument("--project-dir", type=str, default=None,
                        help="项目目录")
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    report = check_all(
        project_dir=args.project_dir,
        check_external=args.check_external,
    )

    out_path = os.path.join(OUTPUT_DIR, "link-check-report.json")
    save_json(out_path, report)
    log.info(f"断链检测报告已保存: {out_path}")
    log.info(f"  总链接: {report['total_links']}")
    log.info(f"  断链数: {report['total_broken']}")
    log.info(f"  健康分: {report['health_score']}")

    return report


if __name__ == "__main__":
    run()
