#!/usr/bin/env python3
"""
openclaw-tutorial-auto 项目 — 多维度章节质量检测系统 v2
═══════════════════════════════════════════════════════════

六大质量维度:
  1. 内容充实度 (Content)  — 字数、段落数、信息密度
  2. 结构完整性 (Structure) — 标题层级、小节数、章首/小结
  3. 代码质量   (Code)      — 代码块数量、语言标注、可运行性
  4. 可读性     (Readability) — 段落长度、列表/表格、格式一致性
  5. 教学价值   (Pedagogy)   — FAQ、示例、实操步骤、延伸链接
  6. 时效性     (Freshness)  — 最近修改时间、版本号引用、过时命令

每个维度 0-100 分，综合加权得出总分

用法:
  python check_quality.py              # 检查所有章节
  python check_quality.py --chapter 5  # 检查指定章节
  python check_quality.py --verbose    # 详细输出
"""
import os, sys, json, re, math
from pathlib import Path
from datetime import datetime

PROJECT_DIR = os.environ.get("PROJECT_DIR", "/root/.openclaw/workspace/zxk-private/openclaw-tutorial-auto")
OUTPUT_DIR  = os.environ.get("OUTPUT_DIR", "/tmp/openclaw-tutorial-auto-reports")

# 维度权重 (总和 1.0)
WEIGHTS = {
    "content":     0.25,
    "structure":   0.20,
    "code":        0.15,
    "readability": 0.15,
    "pedagogy":    0.15,
    "freshness":   0.10,
}

# 阈值配置
THRESHOLDS = {
    "min_words": 800,
    "ideal_words": 1500,
    "min_sections": 3,
    "ideal_sections": 5,
    "min_code_blocks": 2,
    "min_paragraphs": 5,
    "max_para_length": 300,
    "min_tables": 1,
    "stale_hours": 72,
    "very_stale_hours": 168,
}


def parse_file(filepath: Path) -> dict:
    """解析 Markdown 文件，提取所有结构化数据"""
    text = filepath.read_text(encoding="utf-8")
    lines = text.splitlines()

    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    english_words = len(re.findall(r'[a-zA-Z]+', text))
    word_count = chinese_chars + english_words

    # 标题
    headings = []
    for i, line in enumerate(lines, 1):
        m = re.match(r'^(#{1,6})\s+(.+)', line)
        if m:
            headings.append({"level": len(m.group(1)), "text": m.group(2).strip(), "line": i})

    # 代码块
    code_blocks = []
    in_block = False
    block_start = 0
    block_lang = ""
    for i, line in enumerate(lines, 1):
        if line.strip().startswith('```') and not in_block:
            in_block = True
            block_start = i
            block_lang = line.strip()[3:].strip()
        elif line.strip().startswith('```') and in_block:
            in_block = False
            code_blocks.append({
                "start": block_start, "end": i,
                "language": block_lang,
                "lines": i - block_start - 1,
            })

    # 段落
    paragraphs = []
    current_para = []
    in_code = False
    for line in lines:
        if line.strip().startswith('```'):
            in_code = not in_code
            if current_para:
                paragraphs.append("\n".join(current_para))
                current_para = []
            continue
        if in_code:
            continue
        if not line.strip() or line.strip().startswith('#') or line.strip().startswith('|'):
            if current_para:
                paragraphs.append("\n".join(current_para))
                current_para = []
        else:
            current_para.append(line)
    if current_para:
        paragraphs.append("\n".join(current_para))

    # 表格
    table_count = len(re.findall(r'^\|.*\|.*\|$', text, re.MULTILINE)) // 2

    # 列表
    ul_items = len(re.findall(r'^[\s]*[-*+]\s', text, re.MULTILINE))
    ol_items = len(re.findall(r'^[\s]*\d+\.\s', text, re.MULTILINE))
    list_items = ul_items + ol_items

    # 链接
    all_links = re.findall(r'\[([^\]]*)\]\(([^)]+)\)', text)
    external_links = [l for l in all_links if l[1].startswith('http')]

    # 引用块
    blockquotes = len(re.findall(r'^>\s', text, re.MULTILINE))

    # 特殊标记
    has_summary = bool(re.search(r'##?\s*(本章小结|小结|总结|Summary)', text, re.IGNORECASE))
    has_intro = bool(re.search(r'^#\s+', text, re.MULTILINE))
    has_next = bool(re.search(r'(下一章|下[一]节|Next)', text))
    has_faq = bool(re.search(r'(常见问题|FAQ|Q\s*[:：]|问[:：])', text, re.IGNORECASE))
    has_tip = bool(re.search(r'(提示|注意|💡|⚠️|Tip|Note|Warning)', text))
    has_step = bool(re.search(r'(步骤|第[一二三四五六七八九十\d]+步|Step\s+\d)', text))
    has_version = bool(re.findall(r'v\d+\.\d+', text))
    has_update_marker = bool(re.search(r'(最新动态|更新时间|Updated)', text))

    try:
        mtime = datetime.fromtimestamp(os.path.getmtime(str(filepath)))
    except Exception:
        mtime = None

    return {
        "path": str(filepath), "text": text, "lines": lines,
        "word_count": word_count, "chinese_chars": chinese_chars,
        "english_words": english_words, "char_count": len(text),
        "line_count": len(lines), "headings": headings,
        "code_blocks": code_blocks, "paragraphs": paragraphs,
        "table_count": table_count, "list_items": list_items,
        "external_links": external_links, "all_links": all_links,
        "blockquotes": blockquotes,
        "has_summary": has_summary, "has_intro": has_intro,
        "has_next": has_next, "has_faq": has_faq,
        "has_tip": has_tip, "has_step": has_step,
        "has_version": has_version, "has_update_marker": has_update_marker,
        "mtime": mtime,
    }


# ============================================================
#  六大维度评分函数
# ============================================================

def score_content(data: dict) -> dict:
    """维度1: 内容充实度"""
    score = 100
    details = []
    wc = data["word_count"]
    min_w = THRESHOLDS["min_words"]
    ideal_w = THRESHOLDS["ideal_words"]

    if wc < min_w * 0.5:
        score -= 50
        details.append(f"字数严重不足: {wc} (最低 {min_w})")
    elif wc < min_w:
        score -= 30
        details.append(f"字数不足: {wc} < {min_w}")
    elif wc < ideal_w:
        score -= 10
        details.append(f"字数偏少: {wc} < {ideal_w}")

    para_count = len(data["paragraphs"])
    if para_count < THRESHOLDS["min_paragraphs"]:
        score -= 10
        details.append(f"段落数不足: {para_count} < {THRESHOLDS['min_paragraphs']}")

    content_lines = sum(cb["lines"] for cb in data["code_blocks"]) + data["table_count"] * 3 + data["list_items"]
    density = content_lines / max(data["line_count"], 1) * 100
    if density < 10:
        score -= 10
        details.append(f"信息密度偏低: 结构化内容仅占 {density:.0f}%")

    return {"score": max(0, score), "details": details, "metrics": {
        "word_count": wc, "paragraphs": para_count, "density_pct": round(density, 1)
    }}


def score_structure(data: dict) -> dict:
    """维度2: 结构完整性"""
    score = 100
    details = []
    h2_count = len([h for h in data["headings"] if h["level"] == 2])
    h3_count = len([h for h in data["headings"] if h["level"] == 3])

    if not data["has_intro"]:
        score -= 10
        details.append("缺少一级标题")

    min_s = THRESHOLDS["min_sections"]
    ideal_s = THRESHOLDS["ideal_sections"]
    if h2_count < min_s:
        score -= 25
        details.append(f"小节数不足: {h2_count} < {min_s}")
    elif h2_count < ideal_s:
        score -= 10
        details.append(f"小节数偏少: {h2_count} < {ideal_s}")

    if h3_count == 0 and h2_count > 2:
        score -= 10
        details.append("缺少三级子标题，结构深度不够")

    if not data["has_summary"]:
        score -= 15
        details.append("缺少'本章小结'段落")

    prev_level = 0
    for h in data["headings"]:
        if h["level"] - prev_level > 1 and prev_level > 0:
            score -= 5
            details.append(f"标题层级跳跃: H{prev_level}→H{h['level']} (第{h['line']}行)")
            break
        prev_level = h["level"]

    texts = [h["text"] for h in data["headings"]]
    dupes = set([t for t in texts if texts.count(t) > 1])
    if dupes:
        score -= 5
        details.append(f"重复标题: {', '.join(dupes)}")

    return {"score": max(0, score), "details": details, "metrics": {
        "h1": len([h for h in data["headings"] if h["level"] == 1]),
        "h2": h2_count, "h3": h3_count, "has_summary": data["has_summary"],
    }}


def score_code(data: dict) -> dict:
    """维度3: 代码质量"""
    score = 100
    details = []
    cb_count = len(data["code_blocks"])
    min_cb = THRESHOLDS["min_code_blocks"]

    if cb_count == 0:
        score -= 50
        details.append("完全没有代码示例")
    elif cb_count < min_cb:
        score -= 20
        details.append(f"代码块不足: {cb_count} < {min_cb}")

    unlabeled = [cb for cb in data["code_blocks"] if not cb["language"]]
    if unlabeled:
        ratio = len(unlabeled) / max(cb_count, 1)
        if ratio > 0.5:
            score -= 15
            details.append(f"{len(unlabeled)}/{cb_count} 个代码块缺少语言标注")
        else:
            score -= 5
            details.append(f"{len(unlabeled)} 个代码块缺少语言标注")

    short_blocks = [cb for cb in data["code_blocks"] if cb["lines"] <= 1]
    if len(short_blocks) > cb_count * 0.5 and cb_count > 0:
        score -= 10
        details.append(f"过多简短代码块: {len(short_blocks)}/{cb_count}")

    langs = set(cb["language"] for cb in data["code_blocks"] if cb["language"])
    if cb_count >= 3 and len(langs) <= 1:
        score -= 5
        details.append("代码语言单一")

    return {"score": max(0, score), "details": details, "metrics": {
        "code_blocks": cb_count, "languages": list(langs),
        "unlabeled": len(unlabeled),
    }}


def score_readability(data: dict) -> dict:
    """维度4: 可读性"""
    score = 100
    details = []

    long_paras = [p for p in data["paragraphs"]
                  if len(re.findall(r'[\u4e00-\u9fff]', p)) + len(re.findall(r'[a-zA-Z]+', p)) > THRESHOLDS["max_para_length"]]
    if long_paras:
        score -= min(20, len(long_paras) * 5)
        details.append(f"{len(long_paras)} 个段落过长 (>{THRESHOLDS['max_para_length']}字)")

    if data["list_items"] == 0:
        score -= 10
        details.append("没有使用列表")

    if data["table_count"] == 0:
        score -= 10
        details.append("没有使用表格")

    if not data["has_tip"] and data["blockquotes"] == 0:
        score -= 10
        details.append("缺少提示/注意/引用块")

    consecutive = 0
    max_consecutive = 0
    for line in data["lines"]:
        if line.strip():
            consecutive += 1
            max_consecutive = max(max_consecutive, consecutive)
        else:
            consecutive = 0
    if max_consecutive > 20:
        score -= 10
        details.append(f"连续 {max_consecutive} 行无空行间隔，排版密集")

    return {"score": max(0, score), "details": details, "metrics": {
        "list_items": data["list_items"], "tables": data["table_count"],
        "blockquotes": data["blockquotes"], "long_paras": len(long_paras),
    }}


def score_pedagogy(data: dict) -> dict:
    """维度5: 教学价值"""
    score = 100
    details = []

    if not data["has_faq"]:
        score -= 15
        details.append("缺少 FAQ / 常见问题")

    if not data["has_step"]:
        score -= 10
        details.append("缺少步骤化操作指引")

    if not data["external_links"]:
        score -= 10
        details.append("缺少外部参考链接")

    if not data["has_next"]:
        score -= 5
        details.append("缺少下一章导航")

    code_lines = sum(cb["lines"] for cb in data["code_blocks"])
    text_lines = data["line_count"] - code_lines
    if code_lines > 0 and text_lines < code_lines * 0.5:
        score -= 15
        details.append("代码过多但解释不足")

    return {"score": max(0, score), "details": details, "metrics": {
        "has_faq": data["has_faq"], "has_step": data["has_step"],
        "external_links": len(data["external_links"]),
        "has_next": data["has_next"],
    }}


def score_freshness(data: dict) -> dict:
    """维度6: 时效性"""
    score = 100
    details = []

    if data["mtime"]:
        hours_old = (datetime.now() - data["mtime"]).total_seconds() / 3600
        if hours_old > THRESHOLDS["very_stale_hours"]:
            score -= 30
            details.append(f"已 {hours_old:.0f}h 未更新 (>{THRESHOLDS['very_stale_hours']}h)")
        elif hours_old > THRESHOLDS["stale_hours"]:
            score -= 15
            details.append(f"已 {hours_old:.0f}h 未更新")
    else:
        score -= 10
        details.append("无法获取修改时间")

    if data["has_update_marker"]:
        score = min(100, score + 10)

    return {"score": max(0, score), "details": details, "metrics": {
        "last_modified": data["mtime"].isoformat() if data["mtime"] else None,
        "has_update_marker": data["has_update_marker"],
    }}


# ============================================================
#  综合评分
# ============================================================

def evaluate_chapter(filepath: Path) -> dict:
    """对单个章节进行六维度综合评估"""
    data = parse_file(filepath)

    dimensions = {
        "content": score_content(data),
        "structure": score_structure(data),
        "code": score_code(data),
        "readability": score_readability(data),
        "pedagogy": score_pedagogy(data),
        "freshness": score_freshness(data),
    }

    weighted_score = sum(dimensions[dim]["score"] * WEIGHTS[dim] for dim in WEIGHTS)

    all_issues = []
    for dim_name, dim_data in dimensions.items():
        for detail in dim_data["details"]:
            all_issues.append(f"[{dim_name}] {detail}")

    if weighted_score >= 90: grade = "A"
    elif weighted_score >= 80: grade = "B"
    elif weighted_score >= 70: grade = "C"
    elif weighted_score >= 60: grade = "D"
    else: grade = "F"

    return {
        "file": filepath.name,
        "chapter_num": int(re.match(r'^(\d+)', filepath.name).group(1)) if re.match(r'^(\d+)', filepath.name) else 0,
        "overall": {
            "score": round(weighted_score, 1),
            "grade": grade,
            "pass": weighted_score >= 70,
            "issues_count": len(all_issues),
        },
        "dimensions": dimensions,
        "all_issues": all_issues,
        "basics": {
            "word_count": data["word_count"],
            "char_count": data["char_count"],
            "line_count": data["line_count"],
        },
    }


def generate_report_md(results: dict) -> str:
    """生成 Markdown 质量报告"""
    lines = []
    lines.append("# 📊 教程质量检测报告\n")
    lines.append(f"> 检测时间: {results['timestamp']}")
    lines.append(f"> 检测版本: v2.0 (六维度多指标)\n")

    s = results["summary"]
    lines.append("## 总体评价\n")
    lines.append("| 指标 | 值 |")
    lines.append("|------|------|")
    lines.append(f"| 平均总分 | **{s['average_score']}** ({s['average_grade']}) |")
    lines.append(f"| 总字数 | {s['total_words']} |")
    lines.append(f"| 平均字数 | {s['average_words']} |")
    lines.append(f"| 总问题数 | {s['total_issues']} |")
    lines.append(f"| 全部通过 | {'✅' if s['all_pass'] else '❌'} |")
    lines.append("")

    lines.append("## 维度平均分\n")
    lines.append("| 维度 | 平均分 | 权重 |")
    lines.append("|------|--------|------|")
    dim_labels = {"content": "内容充实度", "structure": "结构完整性", "code": "代码质量",
                  "readability": "可读性", "pedagogy": "教学价值", "freshness": "时效性"}
    for dim_name, avg in s["dimension_averages"].items():
        lines.append(f"| {dim_labels.get(dim_name, dim_name)} | {avg} | {WEIGHTS[dim_name]*100:.0f}% |")
    lines.append("")

    lines.append("## 逐章详情\n")
    for ch in results["chapters"]:
        grade = ch["overall"]["grade"]
        score = ch["overall"]["score"]
        emoji = {"A": "🟢", "B": "🔵", "C": "🟡", "D": "🟠", "F": "🔴"}.get(grade, "⚪")
        lines.append(f"### {emoji} {ch['file']} — {score}分 ({grade})\n")
        lines.append(f"字数: {ch['basics']['word_count']}\n")

        dim_strs = []
        for dn in ["content", "structure", "code", "readability", "pedagogy", "freshness"]:
            ds = ch["dimensions"][dn]["score"]
            dim_strs.append(f"{dim_labels.get(dn, dn)}={ds}")
        lines.append("| ".join(dim_strs))
        lines.append("")

        if ch["all_issues"]:
            for issue in ch["all_issues"][:5]:
                lines.append(f"- ⚠️ {issue}")
            if len(ch["all_issues"]) > 5:
                lines.append(f"- ... 还有 {len(ch['all_issues'])-5} 个问题")
            lines.append("")

    return "\n".join(lines)


# ============================================================
#  主入口
# ============================================================

def run():
    import argparse
    parser = argparse.ArgumentParser(description="多维度质量检测 v2")
    parser.add_argument("--chapter", type=int, default=0, help="指定章节号 (0=全部)")
    parser.add_argument("--verbose", action="store_true", help="详细输出")
    args = parser.parse_args()

    proj = Path(PROJECT_DIR)

    if args.chapter > 0:
        pattern = f"{args.chapter:02d}-*.md"
        chapter_files = sorted(proj.glob(pattern))
    else:
        chapter_files = sorted([f for f in proj.iterdir()
                                if f.is_file() and f.name[0:2].isdigit() and f.name.endswith('.md')])

    if not chapter_files:
        print("❌ 未找到章节文件")
        return

    print("╔══════════════════════════════════════════════════════╗")
    print("║  📊 多维度质量检测 v2                                ║")
    print("╚══════════════════════════════════════════════════════╝")
    print(f"  检测章节: {len(chapter_files)}")
    print()

    results = {
        "timestamp": datetime.now().isoformat(),
        "version": "2.0",
        "project_dir": PROJECT_DIR,
        "weights": WEIGHTS,
        "thresholds": THRESHOLDS,
        "chapters": [],
        "summary": {},
    }

    total_score = 0
    total_issues = 0
    total_words = 0
    dim_totals = {d: 0 for d in WEIGHTS}

    for f in chapter_files:
        evaluation = evaluate_chapter(f)
        results["chapters"].append(evaluation)
        total_score += evaluation["overall"]["score"]
        total_issues += evaluation["overall"]["issues_count"]
        total_words += evaluation["basics"]["word_count"]
        for d in WEIGHTS:
            dim_totals[d] += evaluation["dimensions"][d]["score"]

        grade = evaluation["overall"]["grade"]
        score = evaluation["overall"]["score"]
        wc = evaluation["basics"]["word_count"]
        emoji = {"A": "🟢", "B": "🔵", "C": "🟡", "D": "🟠", "F": "🔴"}.get(grade, "⚪")
        print(f"  {emoji} {f.name:<45s} {score:5.1f} ({grade})  {wc}字  {evaluation['overall']['issues_count']}问题")

        if args.verbose and evaluation["all_issues"]:
            for issue in evaluation["all_issues"]:
                print(f"      ⚠️ {issue}")

    n = len(chapter_files) or 1
    avg_score = round(total_score / n, 1)

    if avg_score >= 90: avg_grade = "A"
    elif avg_score >= 80: avg_grade = "B"
    elif avg_score >= 70: avg_grade = "C"
    elif avg_score >= 60: avg_grade = "D"
    else: avg_grade = "F"

    dim_averages = {d: round(dim_totals[d] / n, 1) for d in WEIGHTS}

    results["summary"] = {
        "chapters_analyzed": n,
        "average_score": avg_score,
        "average_grade": avg_grade,
        "total_words": total_words,
        "average_words": round(total_words / n),
        "total_issues": total_issues,
        "all_pass": all(ch["overall"]["pass"] for ch in results["chapters"]),
        "dimension_averages": dim_averages,
    }

    print()
    print("╔══════════════════════════════════════════════════════╗")
    print("║  📊 汇总                                             ║")
    print("╚══════════════════════════════════════════════════════╝")
    print(f"  平均分: {avg_score} ({avg_grade})")
    print(f"  总字数: {total_words} | 平均: {round(total_words/n)}")
    print(f"  总问题: {total_issues}")
    print(f"  维度平均: ", end="")
    for d in WEIGHTS:
        short = {"content": "内容", "structure": "结构", "code": "代码",
                 "readability": "可读", "pedagogy": "教学", "freshness": "时效"}[d]
        print(f"{short}={dim_averages[d]}", end="  ")
    print()

    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    out_json = Path(OUTPUT_DIR) / "quality-report.json"
    out_json.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    report_md = generate_report_md(results)
    out_md = Path(OUTPUT_DIR) / "quality-report.md"
    out_md.write_text(report_md, encoding="utf-8")

    # 兼容旧接口
    compat = {
        "timestamp": results["timestamp"],
        "project_dir": PROJECT_DIR,
        "chapters_analyzed": n,
        "chapters": [{
            "file": ch["file"],
            "stats": {"word_count": ch["basics"]["word_count"], "characters": ch["basics"]["char_count"]},
            "quality": {"score": ch["overall"]["score"], "issues": ch["all_issues"], "pass": ch["overall"]["pass"]},
        } for ch in results["chapters"]],
        "summary": {
            "average_score": avg_score,
            "total_issues": total_issues,
            "total_words": total_words,
            "all_pass": results["summary"]["all_pass"],
        },
    }
    (Path(OUTPUT_DIR) / "02-quality-check.json").write_text(
        json.dumps(compat, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\n  📄 报告已保存: {out_json}")
    print(f"  📄 Markdown:  {out_md}")
    return results


if __name__ == "__main__":
    run()
