#!/usr/bin/env python3
"""
formatter.py — 文档格式统一器
================================
扫描并统一整个教程仓库的 Markdown 格式。
属于优化流水线的最后阶段。

输入: 章节文件
输出: 格式化后的章节文件 + {OUTPUT_DIR}/format-result.json
"""

from datetime import datetime, timezone
import json
import os
import re
import sys

from modules.compat import (
    setup_logger, cfg, save_json, word_count,
    read_file_safe, PROJECT_DIR, OUTPUT_DIR, DRY_RUN,
)

_read_file = read_file_safe

log = setup_logger("formatter")


def format_chapter(filepath: str) -> dict:
    """格式化单个章节文件。"""
    text = _read_file(filepath)
    fname = os.path.basename(filepath)
    original = text
    fixes = []

    # ── 1. 修复 4 反引号为 3 反引号 ──
    quad_backtick = re.findall(r"````", text)
    if quad_backtick:
        text = text.replace("````", "```")
        fixes.append({"type": "quad_backtick", "count": len(quad_backtick) // 2,
                       "fix": "replaced ```` with ```"})

    # ── 1b. 修复代码块关闭标记损坏 ──
    lines_raw = text.split("\n")
    new_raw = []
    in_code = False
    close_fixes = 0
    for ln in lines_raw:
        stripped = ln.strip()
        if stripped.startswith("```"):
            lang = stripped[3:].strip()
            if not in_code:
                in_code = True
                new_raw.append(ln)
            elif lang:
                new_raw.append("```")
                close_fixes += 1
                in_code = False
            else:
                new_raw.append(ln)
                in_code = False
        else:
            new_raw.append(ln)
    if close_fixes:
        text = "\n".join(new_raw)
        fixes.append({"type": "broken_code_closing", "count": close_fixes,
                       "fix": f"fixed {close_fixes} broken code block closing tags"})

    # ── 2. 标题前空行标准化 ──
    # H2+ 标题前应有空行
    lines = text.split("\n")
    new_lines = []
    for i, line in enumerate(lines):
        if re.match(r"^#{2,6}\s+", line) and i > 0:
            # 确保标题前有空行
            if new_lines and new_lines[-1].strip() != "":
                new_lines.append("")
                fixes.append({"type": "heading_spacing", "line": i + 1,
                               "fix": f"added blank line before heading"})
        new_lines.append(line)
    text = "\n".join(new_lines)

    # ── 3. 多余空行压缩 (>3个连续空行 → 2个) ──
    original_lines = len(text.split("\n"))
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    if len(text.split("\n")) != original_lines:
        fixes.append({"type": "excess_blank_lines",
                       "fix": "compressed excessive blank lines"})

    # ── 4. 行尾空白清理 ──
    cleaned = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
    if cleaned != text:
        trailing_count = sum(
            1 for a, b in zip(text.split("\n"), cleaned.split("\n")) if a != b
        )
        text = cleaned
        fixes.append({"type": "trailing_whitespace", "count": trailing_count,
                       "fix": f"removed trailing whitespace from {trailing_count} lines"})

    # ── 5. 确保文件以单个换行符结尾 ──
    if not text.endswith("\n"):
        text += "\n"
        fixes.append({"type": "eof_newline", "fix": "added final newline"})
    elif text.endswith("\n\n"):
        text = text.rstrip("\n") + "\n"
        fixes.append({"type": "eof_newline", "fix": "normalized final newlines"})

    # ── 6. 中英文间距 (CJK-Latin spacing) ──
    # 跳过代码块内容，避免误修改代码
    fmt_lines = text.split("\n")
    fmt_new_lines = []
    in_fmt_code = False
    spacing_fix_count = 0
    for fmt_line in fmt_lines:
        if fmt_line.strip().startswith("```"):
            in_fmt_code = not in_fmt_code
            fmt_new_lines.append(fmt_line)
            continue
        if in_fmt_code:
            fmt_new_lines.append(fmt_line)
            continue
        # 保护行内代码
        _inline_codes = []
        def _preserve_ic(m, _codes=_inline_codes):
            _codes.append(m.group(0))
            return f"\x00IC{len(_codes)-1}\x00"
        protected_line = re.sub(r'`[^`]+`', _preserve_ic, fmt_line)
        fixed_line = re.sub(r'([\u4e00-\u9fff])([A-Za-z0-9])', r'\1 \2', protected_line)
        fixed_line = re.sub(r'([A-Za-z0-9])([\u4e00-\u9fff])', r'\1 \2', fixed_line)
        for idx, ic in enumerate(_inline_codes):
            fixed_line = fixed_line.replace(f"\x00IC{idx}\x00", ic)
        if fixed_line != fmt_line:
            spacing_fix_count += 1
        fmt_new_lines.append(fixed_line)
        _inline_codes.clear()
    text = "\n".join(fmt_new_lines)
    if spacing_fix_count:
        fixes.append({"type": "cjk_spacing", "count": spacing_fix_count,
                       "fix": f"added CJK-Latin spaces in {spacing_fix_count} lines (code-aware)"})

    # ── 6b. [已移至 refiner] 旧式提示转 GitHub Alert ──
    # 该功能由 tutorial_refiner.convert_to_github_alerts 统一处理，
    # 此处不再重复执行，避免双重修改和计数不准确。

    # ── 7. 表格对齐检查 ──
    table_issues = _check_table_alignment(text)
    if table_issues:
        fixes.extend(table_issues)

    # ── 8. 链接格式修复 ──
    # 修复 ]( 之间的空格
    if re.search(r"\]\s+\(", text):
        text = re.sub(r"\]\s+\(", "](", text)
        fixes.append({"type": "link_format", "fix": "removed spaces between ] and ("})

    # ── 评分 ──
    score_before = _compute_format_score(original)
    score_after = _compute_format_score(text)

    # ── 写入 ──
    if fixes and not DRY_RUN and text != original:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(text)

    return {
        "file": fname,
        "fixes_applied": fixes,
        "fix_count": len(fixes),
        "format_score_before": score_before,
        "format_score_after": score_after,
        "changed": text != original,
    }


def _check_table_alignment(text: str) -> list:
    """检查表格对齐(仅报告，不修复复杂的表格)。"""
    issues = []
    in_table = False
    table_cols = 0

    for i, line in enumerate(text.split("\n"), 1):
        if re.match(r"^\|.+\|$", line):
            cols = len(line.split("|")) - 2  # 去掉首尾空
            if not in_table:
                in_table = True
                table_cols = cols
            elif cols != table_cols:
                issues.append({
                    "type": "table_alignment",
                    "line": i,
                    "fix": f"table column mismatch: expected {table_cols}, got {cols}",
                })
        else:
            in_table = False
            table_cols = 0

    return issues


def _compute_format_score(text: str) -> float:
    """计算格式规范得分 (0-100)，代码块感知。"""
    score = 100.0
    deductions = 0

    # 标题跳级 (-5 each, 跳过代码块)
    prev_level = 0
    in_code = False
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = re.match(r"^(#{1,6})\s+", line)
        if m:
            level = len(m.group(1))
            if prev_level > 0 and level > prev_level + 1:
                deductions += 5
            prev_level = level

    # 4反引号 (-3 each)
    deductions += len(re.findall(r"````", text)) * 3

    # 代码块关闭标记损坏 (-5 each, 严重)
    in_cb = False
    for ln in text.split("\n"):
        s = ln.strip()
        if s.startswith("```"):
            lang = s[3:].strip()
            if not in_cb:
                in_cb = True
            elif lang:
                deductions += 5  # 关闭标记带语言标签 = 损坏
                in_cb = False
            else:
                in_cb = False

    # 未标注语言的代码块 (-0.5 each, max -10, 调低权重避免技术教程评分过低)
    unlabeled_count = len(re.findall(r"^```\s*$", text, re.MULTILINE))
    deductions += min(unlabeled_count * 0.5, 10)

    # 行尾空白 (-0.5 each, max -5)
    trailing = len(re.findall(r"[ \t]+$", text, re.MULTILINE))
    deductions += min(trailing * 0.5, 5)

    # 连续超过3个空行 (-2 each)
    deductions += len(re.findall(r"\n{4,}", text)) * 2

    # 中英文无空格 (-0.2 each, max -5)
    no_space = len(re.findall(r'[\u4e00-\u9fff][A-Za-z0-9]|[A-Za-z0-9][\u4e00-\u9fff]', text))
    deductions += min(no_space * 0.2, 5)

    score -= deductions
    return max(0, round(score, 1))


def format_all(project_dir: str = None) -> dict:
    """格式化整个仓库。"""
    project_dir = project_dir or PROJECT_DIR
    log.info(f"格式化教程仓库: {project_dir}")

    md_files = sorted(
        f for f in os.listdir(project_dir)
        if re.match(r"\d+.*\.md$", f) and not f.endswith(".bak")
    )

    results = []
    total_fixes = 0

    for fname in md_files:
        filepath = os.path.join(project_dir, fname)
        try:
            result = format_chapter(filepath)
            results.append(result)
            total_fixes += result["fix_count"]
            if result["changed"]:
                log.info(f"  [{fname}] {result['fix_count']} fixes, "
                          f"score: {result['format_score_before']}→{result['format_score_after']}")
            else:
                log.info(f"  [{fname}] OK (score: {result['format_score_after']})")
        except Exception as e:
            log.error(f"  [{fname}] Error: {e}")
            results.append({"file": fname, "error": str(e)})

    # README 和 OUTLINE 也格式化
    for special in ["README.md", "OUTLINE.md"]:
        special_path = os.path.join(project_dir, special)
        if os.path.exists(special_path):
            try:
                result = format_chapter(special_path)
                results.append(result)
                total_fixes += result.get("fix_count", 0)
            except Exception as e:
                log.error(f"  [{special}] Error: {e}")

    avg_score = (
        sum(r.get("format_score_after", 0) for r in results if "error" not in r)
        / max(len([r for r in results if "error" not in r]), 1)
    )

    report = {
        "format_time": datetime.now(tz=timezone.utc).isoformat(),
        "total_files": len(results),
        "total_fixes": total_fixes,
        "files_changed": sum(1 for r in results if r.get("changed", False)),
        "average_format_score": round(avg_score, 1),
        "dry_run": DRY_RUN,
        "results": results,
    }

    return report


def run():
    """主入口。"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    report = format_all()

    out_path = os.path.join(OUTPUT_DIR, "format-result.json")
    save_json(out_path, report)
    log.info(f"格式化结果已保存: {out_path}")
    log.info(f"  修改文件: {report['files_changed']}/{report['total_files']}")
    log.info(f"  总修复: {report['total_fixes']}")
    log.info(f"  平均格式分: {report['average_format_score']}")

    return report


if __name__ == "__main__":
    run()
