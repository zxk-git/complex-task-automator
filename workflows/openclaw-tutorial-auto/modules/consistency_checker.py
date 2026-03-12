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
        r"\bClawdHub\b",                # ClawdHub (拼写错误)
    ],
    "config.yaml": [
        r"\bconfig\.yml\b",             # 应该统一用 .yaml
    ],
    "openclaw.json": [
        r"\bopenclaw\.yml\b",
        r"\bopenclaw\.yaml\b",
    ],
    "SKILL.md": [
        r"\bskill\.md\b",              # 大小写不一致
        r"\bSkill\.md\b",
    ],
    "_meta.json": [
        r"\bmeta\.json\b",             # 缺少下划线前缀
    ],
}

# URL 标准化规则 (canonical → variants)
URL_CANONICAL = {
    "https://github.com/openclaw/openclaw": [
        "https://github.com/anthropics/openclaw",
        "https://github.com/openClaw/openclaw",
    ],
    "https://docs.openclaw.ai": [
        "https://docs.openclaw.com",
        "https://doc.openclaw.com",
        "https://doc.openclaw.ai",
        "http://docs.openclaw.com",
        "http://docs.openclaw.ai",
    ],
    "https://hub.openclaw.ai": [
        "https://hub.openclaw.com",
        "https://clawhub.com",
        "http://hub.openclaw.com",
        "http://hub.openclaw.ai",
    ],
    "https://openclaw.ai": [
        "https://openclaw.com",
        "http://openclaw.ai",
        "http://openclaw.com",
    ],
}


# ═══════════════════════════════════════════════════════
# 内容指纹 (用于重复检测)
# ═══════════════════════════════════════════════════════

def _compute_paragraph_hashes(text: str, min_words: int = 40) -> list:
    """
    将文本按段落切分，计算每段的指纹 hash。
    仅保留超过 min_words 字的段落，跳过表格段落。
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
                # 跳过表格段落 (>50% 行以 | 开头): 表格结构自然重复，不算真正的内容重复
                table_lines = sum(1 for l in current if l.strip().startswith('|'))
                if table_lines > len(current) * 0.5:
                    current = []
                    continue
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
        table_lines = sum(1 for l in current if l.strip().startswith('|'))
        if table_lines <= len(current) * 0.5:
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
# 代码区间计算（排除行内代码 + 围栏代码块）
# ═══════════════════════════════════════════════════════

def _compute_code_ranges(text: str) -> list[tuple[int, int]]:
    """预计算 text 中所有代码区间 (start, end) 偏移量。

    包括：
    - 围栏代码块 (``` ... ```)
    - 行内代码 (` ... `)
    返回的区间用于快速判断某个位置是否在代码内。
    """
    ranges: list[tuple[int, int]] = []

    # 围栏代码块
    in_fence = False
    fence_start = 0
    for m in re.finditer(r'^(`{3,})[^\S\n]*\S*[^\S\n]*$', text, re.MULTILINE):
        if not in_fence:
            in_fence = True
            fence_start = m.start()
        else:
            ranges.append((fence_start, m.end()))
            in_fence = False
    # 如果最后一个 fence 未闭合，保护到文本末尾
    if in_fence:
        ranges.append((fence_start, len(text)))

    # 行内代码（但不在已有围栏范围内）
    for m in re.finditer(r'`[^`\n]+`', text):
        s, e = m.start(), m.end()
        # 检查是否与围栏区间重叠（已被覆盖则跳过）
        overlap = any(rs <= s < re for rs, re in ranges)
        if not overlap:
            ranges.append((s, e))

    ranges.sort()
    return ranges


def _in_code(pos: int, code_ranges: list[tuple[int, int]]) -> bool:
    """判断偏移量 pos 是否落在任何代码区间内（二分查找）。"""
    lo, hi = 0, len(code_ranges) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        s, e = code_ranges[mid]
        if pos < s:
            hi = mid - 1
        elif pos >= e:
            lo = mid + 1
        else:
            return True
    return False


# 文件名/路径模式：这些即使在散文中也不应被"纠正"
_RE_FILENAME_CONTEXT = re.compile(
    r'(?:~/?\.|/\w+/)\S*$'   # 路径前缀 ~/.xxx 或 /root/...
    r'|(?:\w+\.(?:json|yaml|yml|md|sh|py|ts|js))\b',  # 文件名后缀
    re.IGNORECASE,
)


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
    code_ranges = _compute_code_ranges(text)

    # 术语使用
    term_usages = defaultdict(list)
    for term, patterns in TERMINOLOGY_RULES.items():
        for pat in patterns:
            for m in re.finditer(pat, text):
                pos = m.start()
                # 跳过代码区间（围栏 + 行内）
                if _in_code(pos, code_ranges):
                    continue
                line_num = text[:pos].count("\n") + 1
                ctx_line = lines[line_num - 1]
                # 跳过文件名/路径上下文（如 openclaw.json、~/.openclaw）
                col = pos - text.rfind("\n", 0, pos) - 1
                preceding = ctx_line[:col]
                following = ctx_line[col + len(m.group()):]
                # 路径前缀（~/. 或 /root/.）
                if re.search(r'[~/\\.]\S*$', preceding):
                    continue
                # 文件后缀（.json, .yaml, .md 等）
                if re.match(r'\.\w+\b', following):
                    continue
                term_usages[term].append({
                    "variant": m.group(),
                    "line": line_num,
                    "context": ctx_line.strip()[:100],
                })

    # URL 提取
    urls = []
    for m in re.finditer(r'https?://[^\s\)\"\'<>]+', text):
        url = m.group().rstrip(".,;:)")
        pos = m.start()
        if _in_code(pos, code_ranges):
            continue
        line_num = text[:pos].count("\n") + 1
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

    # 检查同一基础命令的不同参数写法
    # 比如 openclaw skill install xxx vs openclaw skill add xxx
    # 仅记录真正的别名命令 (同一操作的不同写法)
    # 注意: openclaw config set / edit 是不同子命令，不属于别名
    KNOWN_CMD_ALIASES = {
        "openclaw skill": {"install", "add"},
    }
    for base, usages in cmd_groups.items():
        if base in KNOWN_CMD_ALIASES:
            seen_variants = set()
            for u in usages:
                parts = u["full_cmd"].split()
                if len(parts) >= 3 and parts[2] in KNOWN_CMD_ALIASES[base]:
                    seen_variants.add(parts[2])
            if len(seen_variants) > 1:
                for u in usages:
                    parts = u["full_cmd"].split()
                    if len(parts) >= 3 and parts[2] in KNOWN_CMD_ALIASES[base]:
                        issues.append({
                            "type": "command_inconsistency",
                            "severity": "minor",
                            "file": u["file"],
                            "chapter": u["chapter"],
                            "line": u["line"],
                            "expected": f"{base} (统一写法)",
                            "actual": u["full_cmd"],
                            "message": f"命令写法不一致: '{base}' 存在 {seen_variants} 多种变体",
                        })

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
            max(0, min(100, 100 - severity_counts.get("critical", 0) * 10
                      - severity_counts.get("major", 0) * 3
                      - severity_counts.get("minor", 0) * 0.5)),
            1
        ),
    }

    return report


# ═══════════════════════════════════════════════════════
# 自动修复
# ═══════════════════════════════════════════════════════

def auto_fix(project_dir: str = None, consistency_report: dict = None,
             dry_run: bool = False) -> dict:
    """
    根据一致性检测报告自动修复术语和 URL 不一致问题。

    支持修复的类型:
      - terminology: 术语变体→标准写法
      - url_inconsistency: URL 变体→canonical URL
      - url_scheme: http→https

    不修复的类型 (需要人工判断):
      - content_duplication: 重复内容去重
      - broken_cross_ref: 交叉引用修复
      - command_inconsistency: 命令写法统一

    Args:
        project_dir: 项目目录
        consistency_report: 一致性检测报告 (来自 check_all)
        dry_run: 是否只预览不实际写入

    Returns:
        dict: 修复报告
    """
    project_dir = project_dir or PROJECT_DIR
    issues = (consistency_report or {}).get("issues", [])

    if not issues:
        log.info("  无一致性问题需要修复")
        return {"fixed": 0, "skipped": 0, "files_modified": 0}

    # 按文件分组可修复的问题
    fixable_types = {"terminology", "url_inconsistency", "url_scheme"}
    fixes_by_file = defaultdict(list)
    skipped = 0

    for issue in issues:
        if issue.get("type") in fixable_types:
            fixes_by_file[issue["file"]].append(issue)
        else:
            skipped += 1

    log.info(f"  可自动修复: {sum(len(v) for v in fixes_by_file.values())} 个问题")
    log.info(f"  需人工处理: {skipped} 个问题")

    total_fixed = 0
    files_modified = 0
    fix_details = []

    for fname, file_issues in sorted(fixes_by_file.items()):
        filepath = os.path.join(project_dir, fname)
        if not os.path.exists(filepath):
            continue

        with open(filepath, encoding="utf-8") as f:
            text = f.read()

        original = text
        file_fixed = 0

        # 对该文件的所有修复按行号倒序排列 (从后往前替换，避免位移)
        for issue in file_issues:
            old_val = issue.get("actual", "")
            new_val = issue.get("expected", "")
            if not old_val or not new_val or old_val == new_val:
                continue

            issue_type = issue["type"]
            if issue_type == "terminology":
                # 术语替换：需要精准匹配（不在代码块内）
                # 用正则进行单次替换（仅替换代码块外的）
                replaced = _replace_outside_code_blocks(text, old_val, new_val)
                if replaced != text:
                    text = replaced
                    file_fixed += 1

            elif issue_type in ("url_inconsistency", "url_scheme"):
                # URL 替换：精确字符串替换
                if old_val in text:
                    text = text.replace(old_val, new_val)
                    file_fixed += 1

        if text != original:
            if not dry_run:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(text)
            files_modified += 1
            total_fixed += file_fixed
            fix_details.append({
                "file": fname,
                "fixes": file_fixed,
                "dry_run": dry_run,
            })
            log.info(f"  {'[DRY_RUN] ' if dry_run else ''}修复 {fname}: {file_fixed} 处")

    report = {
        "total_fixed": total_fixed,
        "files_modified": files_modified,
        "skipped": skipped,
        "dry_run": dry_run,
        "details": fix_details,
    }
    return report


def _replace_outside_code_blocks(text: str, old: str, new: str) -> str:
    """在代码块外替换文本（保护代码块、行内代码、文件名/路径）。"""
    lines = text.split("\n")
    result = []
    in_code = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            result.append(line)
            continue
        if in_code:
            result.append(line)
            continue
        # 也保护行内代码 `...`
        parts = re.split(r'(`[^`]+`)', line)
        new_parts = []
        for part in parts:
            if part.startswith('`') and part.endswith('`'):
                new_parts.append(part)  # 行内代码不替换
            else:
                # 保护文件名/路径上下文（如 openclaw.json、~/.openclaw/）
                def _safe_replace(m: re.Match) -> str:
                    s = m.start()
                    ctx_before = part[:s]
                    ctx_after = part[s + len(old):]
                    # 如果紧跟 .json/.yaml 等后缀，或前面是路径字符，不替换
                    if re.search(r'[~/\\.]\S*$', ctx_before):
                        return m.group()
                    if re.match(r'\.\w+\b', ctx_after):
                        return m.group()
                    return new
                new_parts.append(re.sub(re.escape(old), _safe_replace, part))
        result.append("".join(new_parts))
    return "\n".join(result)


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
