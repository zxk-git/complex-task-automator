#!/usr/bin/env python3
"""
consistency_checker.py — 跨章节一致性检测模块
===============================================
检测教程系列中跨章节不一致的问题:
  1. 术语一致性: 同一概念使用不同写法 (e.g. "OpenClaw" vs "openclaw")
  2. URL 一致性: 同一资源使用不同 URL
  3. 命令一致性: 同一操作使用不同指令写法
  4. 交叉引用: 引用的章节/段落是否真实存在
  5. 重复内容: 跨章节大段重复检测

输出: {OUTPUT_DIR}/consistency-report.json
"""

from collections import defaultdict, Counter
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import sys

from modules.compat import setup_logger, cfg, load_json, save_json, word_count, PROJECT_DIR, OUTPUT_DIR

log = setup_logger("consistency_checker")


# ═══════════════════════════════════════════════════════
# 术语一致性规则
# ═══════════════════════════════════════════════════════

# 标准术语 → 变体正则 (不含标准写法)
TERMINOLOGY_RULES = {
    "OpenClaw": [
        r"\bopen[\s_-]?claw\b",         # open claw, open-claw, open_claw
        r"\bOpen[\s_-]Claw\b",          # Open Claw, Open-Claw
        r"\bOPENCLAW\b",                # OPENCLAW
        r"\bopen\s+Claw\b",             # open Claw
    ],
    "ClawHub": [
        r"\bclaw[\s_-]?hub\b",          # claw hub, claw-hub
        r"\bClaw[\s_-]Hub\b",           # Claw Hub, Claw-Hub
        r"\bCLAWHUB\b",                 # CLAWHUB
    ],
    "config.yaml": [
        r"\bconfig\.yml\b",             # 应该统一用 .yaml
    ],
}

# URL 标准化规则 (canonical → variants)
URL_CANONICAL = {
    "https://github.com/anthropics/openclaw": [
        "https://github.com/openclaw/openclaw",
        "https://github.com/openClaw/openclaw",
    ],
    "https://docs.openclaw.com": [
        "https://doc.openclaw.com",
        "http://docs.openclaw.com",    # http vs https
    ],
    "https://hub.openclaw.com": [
        "https://clawhub.com",
        "http://hub.openclaw.com",
    ],
}


# ═══════════════════════════════════════════════════════
# 内容指纹 (用于重复检测)
# ═══════════════════════════════════════════════════════

def _compute_paragraph_hashes(text: str, min_words: int = 30) -> list:
    """
    将文本按段落切分，计算每段的指纹 hash。
    仅保留超过 min_words 字的段落。
    返回 list[dict]: {hash, text_preview, word_count, start_line}
    """
    paragraphs = []
    current = []
    start_line = 1
    in_code = False

    for i, line in enumerate(text.split("\n"), 1):
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue

        if line.strip():
            if not current:
                start_line = i
            current.append(line)
        else:
            if current:
                para_text = "\n".join(current)
                wc = word_count(para_text)
                if wc >= min_words:
                    # 标准化后取 hash
                    normalized = re.sub(r'\s+', ' ', para_text.strip().lower())
                    h = hashlib.md5(normalized.encode()).hexdigest()[:12]
                    paragraphs.append({
                        "hash": h,
                        "text_preview": para_text[:120],
                        "word_count": wc,
                        "start_line": start_line,
                    })
                current = []

    # 最后一个段落
    if current:
        para_text = "\n".join(current)
        wc = word_count(para_text)
        if wc >= min_words:
            normalized = re.sub(r'\s+', ' ', para_text.strip().lower())
            h = hashlib.md5(normalized.encode()).hexdigest()[:12]
            paragraphs.append({
                "hash": h,
                "text_preview": para_text[:120],
                "word_count": wc,
                "start_line": start_line,
            })

    return paragraphs


# ═══════════════════════════════════════════════════════
# 单文件分析
# ═══════════════════════════════════════════════════════

def _analyze_chapter(filepath: str) -> dict:
    """分析单个章节，提取术语/URL/命令使用情况。"""
    fname = os.path.basename(filepath)
    ch_match = re.match(r"(\d+)", fname)
    ch_num = int(ch_match.group(1)) if ch_match else 0

    with open(filepath, encoding="utf-8") as f:
        text = f.read()

    lines = text.split("\n")

    # 术语使用
    term_usages = defaultdict(list)
    for term, patterns in TERMINOLOGY_RULES.items():
        for pat in patterns:
            for m in re.finditer(pat, text):
                # 获取行号
                pos = m.start()
                line_num = text[:pos].count("\n") + 1
                # 检查是否在代码块内
                code_count = text[:pos].count("```")
                if code_count % 2 == 1:
                    continue  # 代码块内，跳过
                term_usages[term].append({
                    "variant": m.group(),
                    "line": line_num,
                    "context": lines[line_num - 1].strip()[:100],
                })

    # URL 提取
    urls = []
    for m in re.finditer(r'https?://[^\s\)\"\'<>]+', text):
        url = m.group().rstrip(".,;:)")
        pos = m.start()
        line_num = text[:pos].count("\n") + 1
        # 检查代码块
        code_count = text[:pos].count("```")
        if code_count % 2 == 1:
            continue
        urls.append({"url": url, "line": line_num})

    # 命令提取 (openclaw 命令)
    commands = []
    in_code = False
    for i, line in enumerate(lines, 1):
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            m = re.match(r'\s*(openclaw\s+.+)', line)
            if m:
                commands.append({
                    "command": m.group(1).strip(),
                    "line": i,
                })

    # 段落指纹
    paragraph_hashes = _compute_paragraph_hashes(text)

    # 章节交叉引用 (如 "参见第X章" "详见 XX 章节")
    cross_refs = []
    for m in re.finditer(r'(?:参见|详见|见|参考)\s*(?:第\s*)?(\d+)\s*章', text):
        ref_ch = int(m.group(1))
        pos = m.start()
        line_num = text[:pos].count("\n") + 1
        cross_refs.append({
            "ref_chapter": ref_ch,
            "line": line_num,
            "text": m.group(),
        })

    return {
        "file": fname,
        "chapter": ch_num,
        "term_usages": dict(term_usages),
        "urls": urls,
        "commands": commands,
        "paragraph_hashes": paragraph_hashes,
        "cross_refs": cross_refs,
    }


# ═══════════════════════════════════════════════════════
# 跨章节比对
# ═══════════════════════════════════════════════════════

def _check_terminology(chapters_data: list) -> list:
    """跨章节术语一致性检查。"""
    issues = []
    for term, _ in TERMINOLOGY_RULES.items():
        for ch in chapters_data:
            usages = ch["term_usages"].get(term, [])
            for usage in usages:
                issues.append({
                    "type": "terminology",
                    "severity": "minor",
                    "file": ch["file"],
                    "chapter": ch["chapter"],
                    "line": usage["line"],
                    "expected": term,
                    "actual": usage["variant"],
                    "context": usage["context"],
                    "message": f"术语不一致: '{usage['variant']}' 应为 '{term}'",
                })
    return issues


def _check_url_consistency(chapters_data: list) -> list:
    """跨章节 URL 一致性检查。"""
    issues = []
    # 收集所有 URL
    all_urls = defaultdict(list)
    for ch in chapters_data:
        for url_info in ch["urls"]:
            all_urls[url_info["url"]].append({
                "file": ch["file"], "chapter": ch["chapter"],
                "line": url_info["line"],
            })

    # 检查已知变体
    for canonical, variants in URL_CANONICAL.items():
        for variant in variants:
            if variant in all_urls:
                for loc in all_urls[variant]:
                    issues.append({
                        "type": "url_inconsistency",
                        "severity": "major",
                        "file": loc["file"],
                        "chapter": loc["chapter"],
                        "line": loc["line"],
                        "expected": canonical,
                        "actual": variant,
                        "message": f"URL 不一致: '{variant}' 应为 '{canonical}'",
                    })

    # 检测 http vs https 变体
    url_by_domain = defaultdict(set)
    for url in all_urls:
        parsed = re.match(r'(https?)://(.+)', url)
        if parsed:
            url_by_domain[parsed.group(2)].add(parsed.group(1))

    for domain_path, schemes in url_by_domain.items():
        if len(schemes) > 1:
            # 既有 http 又有 https
            http_url = f"http://{domain_path}"
            if http_url in all_urls:
                for loc in all_urls[http_url]:
                    issues.append({
                        "type": "url_scheme",
                        "severity": "minor",
                        "file": loc["file"],
                        "chapter": loc["chapter"],
                        "line": loc["line"],
                        "expected": f"https://{domain_path}",
                        "actual": http_url,
                        "message": f"应使用 HTTPS: '{http_url}'",
                    })

    return issues


def _check_command_consistency(chapters_data: list) -> list:
    """跨章节命令一致性检查。"""
    issues = []
    # 收集所有命令，按基础命令分组
    cmd_groups = defaultdict(list)
    for ch in chapters_data:
        for cmd_info in ch["commands"]:
            # 提取基础命令 (第一个子命令)
            parts = cmd_info["command"].split()
            if len(parts) >= 2:
                base = f"{parts[0]} {parts[1]}"
            else:
                base = parts[0]
            cmd_groups[base].append({
                "full_cmd": cmd_info["command"],
                "file": ch["file"],
                "chapter": ch["chapter"],
                "line": cmd_info["line"],
            })

    # 检查同一基础命令的不同写法
    for base, usages in cmd_groups.items():
        full_cmds = set(u["full_cmd"] for u in usages)
        # 如果同一基础命令有多种写法，可能是不一致
        # 但也可能是故意的 (不同参数)，这里只标记可参考
        # 暂不生成 issue，留作信息

    return issues


def _check_cross_references(chapters_data: list) -> list:
    """交叉引用验证: "见第X章" 对应章节是否真实存在。"""
    issues = []
    existing_chapters = {ch["chapter"] for ch in chapters_data}

    for ch in chapters_data:
        for ref in ch["cross_refs"]:
            if ref["ref_chapter"] not in existing_chapters:
                issues.append({
                    "type": "broken_cross_ref",
                    "severity": "major",
                    "file": ch["file"],
                    "chapter": ch["chapter"],
                    "line": ref["line"],
                    "expected": f"第{ref['ref_chapter']}章",
                    "actual": ref["text"],
                    "message": f"交叉引用指向不存在的章节: {ref['text']}",
                })

    return issues


def _check_content_duplication(chapters_data: list) -> list:
    """跨章节重复内容检测。"""
    issues = []
    # 收集所有段落 hash
    hash_locations = defaultdict(list)
    for ch in chapters_data:
        for para in ch["paragraph_hashes"]:
            hash_locations[para["hash"]].append({
                "file": ch["file"],
                "chapter": ch["chapter"],
                "line": para["start_line"],
                "preview": para["text_preview"],
                "word_count": para["word_count"],
            })

    # 找重复段落 (出现在 2+ 个不同章节)
    for h, locations in hash_locations.items():
        # 按文件去重
        chapters_involved = set(loc["file"] for loc in locations)
        if len(chapters_involved) >= 2:
            # 保留第一处作为"原件"，其余为重复
            primary = locations[0]
            for dup in locations[1:]:
                if dup["file"] != primary["file"]:
                    issues.append({
                        "type": "content_duplication",
                        "severity": "minor",
                        "file": dup["file"],
                        "chapter": dup["chapter"],
                        "line": dup["line"],
                        "original_file": primary["file"],
                        "original_line": primary["line"],
                        "preview": dup["preview"][:80],
                        "word_count": dup["word_count"],
                        "message": (
                            f"与 {primary['file']} 第{primary['line']}行重复 "
                            f"(~{dup['word_count']}字)"
                        ),
                    })

    return issues


# ═══════════════════════════════════════════════════════
# 全量检查入口
# ═══════════════════════════════════════════════════════

def check_all(project_dir: str = None, scan_report: dict = None) -> dict:
    """
    对教程仓库执行全面的跨章节一致性检测。

    Returns:
        dict: 一致性报告
    """
    project_dir = project_dir or PROJECT_DIR
    log.info(f"跨章节一致性检测: {project_dir}")

    # 发现 Markdown 文件
    md_files = sorted(
        f for f in os.listdir(project_dir)
        if re.match(r"\d+.*\.md$", f) and not f.endswith(".bak")
    )

    # 分析每个章节
    chapters_data = []
    for fname in md_files:
        filepath = os.path.join(project_dir, fname)
        try:
            data = _analyze_chapter(filepath)
            chapters_data.append(data)
        except Exception as e:
            log.error(f"  分析失败: {fname} — {e}")

    log.info(f"  分析了 {len(chapters_data)} 个章节")

    # 执行各维度检查
    all_issues = []

    term_issues = _check_terminology(chapters_data)
    all_issues.extend(term_issues)
    log.info(f"  术语一致性: {len(term_issues)} 个问题")

    url_issues = _check_url_consistency(chapters_data)
    all_issues.extend(url_issues)
    log.info(f"  URL 一致性: {len(url_issues)} 个问题")

    cmd_issues = _check_command_consistency(chapters_data)
    all_issues.extend(cmd_issues)
    log.info(f"  命令一致性: {len(cmd_issues)} 个问题")

    cross_ref_issues = _check_cross_references(chapters_data)
    all_issues.extend(cross_ref_issues)
    log.info(f"  交叉引用: {len(cross_ref_issues)} 个问题")

    dup_issues = _check_content_duplication(chapters_data)
    all_issues.extend(dup_issues)
    log.info(f"  重复内容: {len(dup_issues)} 个问题")

    # 按严重程度排序
    severity_order = {"critical": 0, "major": 1, "minor": 2, "info": 3}
    all_issues.sort(key=lambda x: severity_order.get(x.get("severity", ""), 99))

    # 按类型统计
    type_counts = Counter(i["type"] for i in all_issues)
    severity_counts = Counter(i["severity"] for i in all_issues)

    # 按章节统计
    chapter_issue_counts = defaultdict(int)
    for issue in all_issues:
        chapter_issue_counts[issue.get("file", "unknown")] += 1

    report = {
        "check_time": datetime.now(tz=timezone.utc).isoformat(),
        "project_dir": project_dir,
        "total_chapters_analyzed": len(chapters_data),
        "total_issues": len(all_issues),
        "issues_by_type": dict(type_counts),
        "issues_by_severity": dict(severity_counts),
        "issues_by_chapter": dict(chapter_issue_counts),
        "issues": all_issues,
        "consistency_score": round(
            max(0, 100 - severity_counts.get("critical", 0) * 10
                      - severity_counts.get("major", 0) * 3
                      - severity_counts.get("minor", 0) * 0.5),
            1
        ),
    }

    return report


def run():
    """主入口。"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    report = check_all()

    out_path = os.path.join(OUTPUT_DIR, "consistency-report.json")
    save_json(out_path, report)
    log.info(f"一致性报告已保存: {out_path}")
    log.info(f"  总问题: {report['total_issues']}")
    log.info(f"  一致性分: {report['consistency_score']}")

    return report


if __name__ == "__main__":
    run()
