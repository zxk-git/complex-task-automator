#!/usr/bin/env python3
"""
tutorial_scanner.py — 教程仓库扫描器
======================================
扫描教程仓库所有 Markdown 文件，提取结构化元数据，生成扫描报告。
属于优化流水线的第一阶段。

输出: {OUTPUT_DIR}/scan-report.json
"""

from datetime import datetime, timezone
from pathlib import Path
import json
import os
import re
import sys

# ── 兼容 utils 导入 ────────────────────────────────
_SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

try:
    from utils import (
        setup_logger, cfg, load_json, save_json,
        parse_outline, find_completed_chapters, word_count,
    )
except ImportError:
    # 最小化回退: 独立运行时使用
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
    def word_count(text):
        """word_count 的功能描述。

            Args:
                text: ...
            """
        cjk = len(re.findall(r'[\u4e00-\u9fff]', text))
        eng = len(re.findall(r'[a-zA-Z]+', text))
        return cjk + eng
    def parse_outline(path):
        """parse_outline 的功能描述。

            Args:
                path: ...
            """
        return []
    def find_completed_chapters(d):
        """find_completed_chapters 的功能描述。

            Args:
                d: ...
            """
        return {}

def _read_file(filepath: str) -> str:
    """直接读取文件内容（不使用 legacy read_chapter）。"""
    with open(filepath, encoding="utf-8") as f:
        return f.read()

log = setup_logger("tutorial_scanner")

# ── 配置 ────────────────────────────────────────────
PROJECT_DIR = cfg("project_dir", os.environ.get(
    "PROJECT_DIR", "/root/.openclaw/workspace/zxk-private/openclaw-tutorial-auto"))
OUTPUT_DIR = cfg("output_dir", os.environ.get(
    "OUTPUT_DIR", "/tmp/openclaw-tutorial-auto-reports"))


def scan_chapter(filepath: str) -> dict:
    """扫描单个章节文件，提取全部元数据。"""
    text = _read_file(filepath)
    lines = text.split("\n")
    fname = os.path.basename(filepath)

    # ── 基础元数据 ──
    match = re.match(r"(\d+)", fname)
    chapter_num = int(match.group(1)) if match else 0

    # 提取 H1 标题
    h1_title = ""
    for line in lines:
        if line.startswith("# ") and not line.startswith("## "):
            h1_title = line.lstrip("# ").strip()
            break

    # ── 标题结构分析 ──
    headings = {"h1": 0, "h2": 0, "h3": 0, "h4": 0, "h5": 0, "h6": 0}
    heading_lines = []
    heading_jumps = []
    prev_level = 0

    for i, line in enumerate(lines, 1):
        m = re.match(r"^(#{1,6})\s+(.+)", line)
        if m:
            level = len(m.group(1))
            headings[f"h{level}"] += 1
            heading_lines.append({"level": level, "line": i, "text": m.group(2).strip()})
            if prev_level > 0 and level > prev_level + 1:
                heading_jumps.append(f"H{prev_level}→H{level} at line {i}")
            prev_level = level

    # ── 目录/导航检测 ──
    has_toc = bool(re.search(r"##\s*📑?\s*本章目录|##\s*目录", text))
    has_nav = bool(re.search(r"\[←\s*上一章|上一章.*\]\(", text))

    # ── 内容质量指标 ──
    code_blocks = re.findall(r"```(\w*)", text)
    code_block_count = len(code_blocks)
    code_langs = [c for c in code_blocks if c]
    unlabeled_code = code_block_count - len(code_langs)

    tables = len(re.findall(r"^\|.+\|$\n\|[-:| ]+\|$", text, re.MULTILINE))
    images = len(re.findall(r"!\[.*?\]\(.*?\)", text))
    links_internal = len(re.findall(r"\[.*?\]\((?!https?://|#)(.*?\.md.*?)\)", text))
    links_external = len(re.findall(r"\[.*?\]\((https?://.*?)\)", text))
    has_faq = bool(re.search(r"##\s*常见问题|##\s*FAQ", text, re.IGNORECASE))
    has_summary = bool(re.search(r"##\s*本章小结|##\s*小结|##\s*Summary", text, re.IGNORECASE))
    has_references = bool(re.search(r"##\s*参考来源|##\s*参考|##\s*References", text, re.IGNORECASE))
    has_cli = bool(re.search(r"openclaw\s+\w+", text))
    blockquotes = len(re.findall(r"^>\s+", text, re.MULTILINE))

    # ── 缺陷检测 ──
    defects = []

    # 占位符
    for i, line in enumerate(lines, 1):
        if re.search(r"TODO|TBD|待补充|待完善|FIXME|xxx|your-.*-here", line, re.IGNORECASE):
            defects.append({"type": "placeholder", "line": i, "text": line.strip()[:80]})

    # 空/短段落 (H2 小节内容不足)
    h2_sections = _extract_h2_sections(lines)
    for sec in h2_sections:
        sec_wc = word_count(sec["content"])
        if sec_wc < 50:
            defects.append({
                "type": "short_section",
                "section": sec["title"],
                "word_count": sec_wc,
                "line": sec["start_line"],
            })

    # 连续密排
    consecutive_no_blank = 0
    for i, line in enumerate(lines, 1):
        if line.strip():
            consecutive_no_blank += 1
            if consecutive_no_blank > 30:
                defects.append({
                    "type": "dense_block",
                    "line": i - 30,
                    "length": consecutive_no_blank,
                })
                consecutive_no_blank = 0  # 只报一次
        else:
            consecutive_no_blank = 0

    # 标题层级跳跃
    for jump in heading_jumps:
        defects.append({"type": "heading_jump", "text": jump})

    # 未标注语言的代码块
    if unlabeled_code > 0:
        defects.append({"type": "unlabeled_code_block", "count": unlabeled_code})

    # ── 质量评分 ──
    score_result = _compute_quality_score(
        word_count(text), headings, code_block_count, tables,
        has_faq, has_summary, has_references, has_cli, has_nav, has_toc,
        defects, links_external, h2_sections,
        images=images, blockquotes=blockquotes, unlabeled_code=unlabeled_code,
    )

    mtime = os.path.getmtime(filepath)
    return {
        "file": fname,
        "number": chapter_num,
        "title": h1_title,
        "word_count": word_count(text),
        "line_count": len(lines),
        "last_modified": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(),
        "structure": {
            **headings,
            "has_toc": has_toc,
            "has_nav": has_nav,
            "heading_jumps": heading_jumps,
            "headings_detail": heading_lines,
        },
        "content": {
            "code_blocks": code_block_count,
            "code_languages": list(set(code_langs)),
            "unlabeled_code_blocks": unlabeled_code,
            "tables": tables,
            "images": images,
            "links_internal": links_internal,
            "links_external": links_external,
            "has_faq": has_faq,
            "has_summary": has_summary,
            "has_references": has_references,
            "has_cli_examples": has_cli,
            "blockquotes": blockquotes,
        },
        "h2_sections": [
            {"title": s["title"], "word_count": word_count(s["content"]), "line": s["start_line"]}
            for s in h2_sections
        ],
        "defects": defects,
        "quality_score": score_result["total"],
        "score_detail": score_result,
    }


def _extract_h2_sections(lines: list) -> list:
    """提取所有 H2 段落及其内容。"""
    sections = []
    current = None
    for i, line in enumerate(lines, 1):
        if re.match(r"^##\s+(?!#)", line):
            if current:
                current["content"] = "\n".join(current["_lines"])
                del current["_lines"]
                sections.append(current)
            current = {
                "title": line.lstrip("#").strip(),
                "start_line": i,
                "_lines": [],
            }
        elif current:
            current["_lines"].append(line)

    if current:
        current["content"] = "\n".join(current["_lines"])
        del current["_lines"]
        sections.append(current)

    return sections


# ── 评分常量（集中管理，禁止散落 magic numbers） ──────
SCORING = {
    # === 维度权重 (严格合计 100) ===
    "dim_content_depth":     25,   # D1: 内容深度
    "dim_structure":         20,   # D2: 结构完整性
    "dim_code_quality":      15,   # D3: 代码质量
    "dim_pedagogy":          15,   # D4: 教学价值
    "dim_references":        10,   # D5: 参考来源
    "dim_readability":       15,   # D6: 可读性

    # === D1 内容深度 — 平滑分档 ===
    "wc_full":   2500,   # 满分字数
    "wc_high":   2000,   # 22 分
    "wc_good":   1500,   # 18 分
    "wc_ok":     1000,   # 13 分
    "wc_low":     500,   # 7 分
    # <500 → 3 分

    # === D2 结构 ===
    "h2_full":        5,    # H2 >= 5 → +6
    "h2_partial":     3,    # H2 >= 3 → +4
    "h1_expected":    1,    # H1 == 1 → +3
    "nav_bonus":      3,
    "toc_bonus":      2,

    # === D3 代码质量 ===
    "code_full":      5,    # >= 5 块 → 满分
    "code_good":      3,    # >= 3 块 → 10 分
    "label_penalty":  1,    # 每个无标签块扣 1

    # === D4 教学价值 ===
    # FAQ/小结/案例/进阶 各独立计分，不重叠

    # === D5 参考来源 ===
    "ref_links_full":  3,   # 外部链接 >= 3 → 满分
    "ref_links_some":  1,   # >= 1 → 部分分

    # === D6 可读性 ===
    "short_section_threshold":   50,   # 字数 < 此值 = 短段落
    "medium_section_threshold": 150,   # 字数 < 此值 = 偏短段落

    # === 缺陷惩罚（按严重程度） ===
    "penalty_critical":  5,   # placeholder (占位符)
    "penalty_major":     3,   # heading_jump, dense_block
    "penalty_minor":     1,   # unlabeled_code_block, short_section
}

DEFECT_SEVERITY = {
    "placeholder":          "critical",
    "heading_jump":         "major",
    "dense_block":          "major",
    "unlabeled_code_block": "minor",
    "short_section":        "minor",
}


def _compute_quality_score(
    wc, headings, code_blocks, tables,
    has_faq, has_summary, has_references, has_cli, has_nav, has_toc,
    defects, ext_links, h2_sections,
    images=0, blockquotes=0, unlabeled_code=0,
) -> dict:
    """
    基于 6 个评估维度计算章节质量分数 (0-100)。

    返回 dict:
        total: float          — 总分 (0-100)
        dimensions: dict      — 各维度得分
        penalties: dict       — 扣分明细
        grade: str            — 等级 (A/B/C/D/F)
    """
    S = SCORING
    dims = {}

    # ── D1: 内容深度 (25 分) ──────────────────────────
    max_d1 = S["dim_content_depth"]
    if wc >= S["wc_full"]:
        d1 = max_d1
    elif wc >= S["wc_high"]:
        d1 = 22
    elif wc >= S["wc_good"]:
        d1 = 18
    elif wc >= S["wc_ok"]:
        d1 = 13
    elif wc >= S["wc_low"]:
        d1 = 7
    else:
        d1 = max(1, round(wc / S["wc_low"] * 7))
    dims["content_depth"] = min(d1, max_d1)

    # ── D2: 结构完整性 (20 分) ────────────────────────
    max_d2 = S["dim_structure"]
    d2 = 0
    # H1 标题
    if headings.get("h1", 0) == S["h1_expected"]:
        d2 += 3
    # H2 数量
    h2 = headings.get("h2", 0)
    if h2 >= S["h2_full"]:
        d2 += 6
    elif h2 >= S["h2_partial"]:
        d2 += 4
    elif h2 >= 1:
        d2 += 2
    # 导航
    if has_nav:
        d2 += S["nav_bonus"]
    # 目录
    if has_toc:
        d2 += S["toc_bonus"]
    # H3 子结构 (最多 +4)
    d2 += min(4, headings.get("h3", 0))
    # 引用块 (增加可读性层次)
    if blockquotes >= 1:
        d2 += 2
    dims["structure"] = min(d2, max_d2)

    # ── D3: 代码质量 (15 分) ──────────────────────────
    max_d3 = S["dim_code_quality"]
    d3 = 0
    if code_blocks >= S["code_full"]:
        d3 += 10
    elif code_blocks >= S["code_good"]:
        d3 += 7
    elif code_blocks >= 1:
        d3 += 3
    # CLI 示例
    if has_cli:
        d3 += 3
    # 语言标签覆盖率
    labeled = code_blocks - unlabeled_code
    if code_blocks > 0:
        label_ratio = labeled / code_blocks
        d3 += round(2 * label_ratio)  # 0-2 分
    dims["code_quality"] = min(d3, max_d3)

    # ── D4: 教学价值 (15 分) ──────────────────────────
    # 注意：FAQ 只在此维度计分，不在 D2 重复
    max_d4 = S["dim_pedagogy"]
    d4 = 0
    if has_faq:
        d4 += 4
    if has_summary:
        d4 += 3
    # 实战/案例/示例段落
    practical_kw = ("实战", "案例", "示例", "实践", "练习", "动手")
    if any(any(kw in s.get("title", "") for kw in practical_kw) for s in h2_sections):
        d4 += 4
    # 进阶/高级段落
    advanced_kw = ("高级", "进阶", "深入", "原理", "架构")
    if any(any(kw in s.get("title", "") for kw in advanced_kw) for s in h2_sections):
        d4 += 3
    # 注意事项段落
    caution_kw = ("注意", "常见错误", "踩坑", "陷阱", "最佳实践")
    if any(any(kw in s.get("title", "") for kw in caution_kw) for s in h2_sections):
        d4 += 1
    dims["pedagogy"] = min(d4, max_d4)

    # ── D5: 参考来源 (10 分) ──────────────────────────
    max_d5 = S["dim_references"]
    d5 = 0
    if has_references:
        d5 += 4
    if ext_links >= S["ref_links_full"]:
        d5 += 6
    elif ext_links >= S["ref_links_some"]:
        d5 += 3
    dims["references"] = min(d5, max_d5)

    # ── D6: 可读性 (15 分) ────────────────────────────
    max_d6 = S["dim_readability"]
    d6 = 0
    # 表格
    if tables >= 2:
        d6 += 4
    elif tables >= 1:
        d6 += 2
    # 图片
    if images >= 1:
        d6 += 2
    # 段落长度适中 — 无短段落 +5, <=2 个短段落 +3
    short_secs = [s for s in h2_sections
                  if word_count(s.get("content", "")) < S["short_section_threshold"]]
    if len(short_secs) == 0:
        d6 += 5
    elif len(short_secs) <= 2:
        d6 += 3
    # H3 细分结构
    d6 += min(2, headings.get("h3", 0))
    # 引用块
    if blockquotes >= 2:
        d6 += 2
    elif blockquotes >= 1:
        d6 += 1
    dims["readability"] = min(d6, max_d6)

    # ── 缺陷惩罚 ─────────────────────────────────────
    penalties = {"critical": 0, "major": 0, "minor": 0, "total": 0}
    for d in defects:
        severity = DEFECT_SEVERITY.get(d.get("type", ""), "minor")
        cost = S[f"penalty_{severity}"]
        penalties[severity] += cost
    penalties["total"] = penalties["critical"] + penalties["major"] + penalties["minor"]

    # ── 合计 ──────────────────────────────────────────
    raw = sum(dims.values())
    total = max(0, min(100, round(raw - penalties["total"], 1)))

    # ── 等级 ──────────────────────────────────────────
    if total >= 90:
        grade = "A"
    elif total >= 75:
        grade = "B"
    elif total >= 60:
        grade = "C"
    elif total >= 40:
        grade = "D"
    else:
        grade = "F"

    return {
        "total": total,
        "dimensions": dims,
        "penalties": penalties,
        "grade": grade,
    }


def scan_repository(project_dir: str = None) -> dict:
    """扫描整个教程仓库，生成完整报告。"""
    project_dir = project_dir or PROJECT_DIR
    log.info(f"扫描教程仓库: {project_dir}")

    chapters = []
    md_files = sorted(
        f for f in os.listdir(project_dir)
        if re.match(r"\d+.*\.md$", f) and not f.endswith(".bak")
    )

    for fname in md_files:
        filepath = os.path.join(project_dir, fname)
        try:
            ch = scan_chapter(filepath)
            chapters.append(ch)
            log.info(f"  [{ch['number']:02d}] {ch['title'][:30]}... "
                      f"score={ch['quality_score']} words={ch['word_count']}")
        except Exception as e:
            log.error(f"  扫描失败: {fname} — {e}")
            chapters.append({"file": fname, "error": str(e)})

    # 检测缺失章节
    completed_nums = {ch["number"] for ch in chapters if "error" not in ch}
    expected = int(cfg("expected_chapters", "21"))
    missing = sorted(set(range(1, expected + 1)) - completed_nums)

    # 全局问题检测
    global_issues = []
    if missing:
        global_issues.append(f"缺失 {len(missing)} 个章节: {missing}")
    total_words = sum(ch.get("word_count", 0) for ch in chapters if "error" not in ch)
    if total_words < expected * 1000:
        global_issues.append(f"总字数 {total_words} 偏低 (期望 ≥ {expected * 1000})")
    low_score = [ch for ch in chapters if ch.get("quality_score", 0) < 60]
    if low_score:
        global_issues.append(f"{len(low_score)} 个章节质量分 < 60")

    # 汇总统计
    avg_score = (
        sum(ch.get("quality_score", 0) for ch in chapters if "error" not in ch)
        / max(len([c for c in chapters if "error" not in c]), 1)
    )

    report = {
        "scan_time": datetime.now(tz=timezone.utc).isoformat(),
        "project_dir": project_dir,
        "total_chapters": len(chapters),
        "expected_chapters": expected,
        "missing_chapters": missing,
        "total_words": total_words,
        "average_score": round(avg_score, 1),
        "chapters": chapters,
        "global_issues": global_issues,
        "summary": {
            "completed": len(chapters),
            "missing": len(missing),
            "avg_score": round(avg_score, 1),
            "min_score": min((ch.get("quality_score", 100) for ch in chapters if "error" not in ch), default=0),
            "max_score": max((ch.get("quality_score", 0) for ch in chapters if "error" not in ch), default=0),
            "total_words": total_words,
            "chapters_with_faq": sum(1 for ch in chapters if ch.get("content", {}).get("has_faq", False)),
            "chapters_with_refs": sum(1 for ch in chapters if ch.get("content", {}).get("has_references", False)),
            "total_defects": sum(len(ch.get("defects", [])) for ch in chapters),
        },
    }

    return report


def run():
    """主入口: 扫描并保存报告。"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    report = scan_repository()

    out_path = os.path.join(OUTPUT_DIR, "scan-report.json")
    save_json(out_path, report)
    log.info(f"扫描报告已保存: {out_path}")
    log.info(f"  完成: {report['summary']['completed']}/{report['expected_chapters']} 章")
    log.info(f"  平均分: {report['summary']['avg_score']}")
    log.info(f"  缺陷数: {report['summary']['total_defects']}")

    return report


if __name__ == "__main__":
    run()
