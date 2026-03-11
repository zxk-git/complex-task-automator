#!/usr/bin/env python3
"""
quality_analyzer.py — 深度质量分析器
======================================
基于扫描报告进行深度质量分析，生成每章的具体优化计划。
属于优化流水线的第二阶段。

输入: {OUTPUT_DIR}/scan-report.json
输出: {OUTPUT_DIR}/analysis-report.json
"""

from datetime import datetime, timezone
from pathlib import Path
import json
import os
import re
import sys

from modules.compat import setup_logger, cfg, load_json, save_json, PROJECT_DIR, OUTPUT_DIR
from modules.types import ChapterScanResult, ChapterAnalysis

log = setup_logger("quality_analyzer")

# ── 推荐章节结构模板 ────────────────────────────────
REQUIRED_SECTIONS = [
    "Introduction",     # 概述/引言
    "Core_Content",     # 核心内容 (至少3个H2)
    "Examples",         # 实战案例/示例
    "Troubleshooting",  # 故障排查
    "FAQ",              # 常见问题
    "Summary",          # 本章小结
    "References",       # 参考来源
]

# 中文段落名映射
SECTION_PATTERNS = {
    "Introduction": [r"概述|引言|介绍|简介|什么是|Overview|Introduction"],
    "Core_Content": [r"核心|原理|概念|工作方式|架构|配置|安装|使用|Core"],
    "Examples": [r"实战|案例|示例|演示|实践|练习|Example|Practice"],
    "Troubleshooting": [r"故障|排查|排错|问题解决|Troubleshoot"],
    "FAQ": [r"常见问题|FAQ|Q\s*[:：]|问答"],
    "Summary": [r"本章小结|小结|总结|Summary|回顾"],
    "References": [r"参考来源|参考|引用|References|延伸阅读"],
}


def analyze_chapter(chapter_data: ChapterScanResult) -> ChapterAnalysis:
    """分析单个章节，生成优化计划。

    estimated_impact 现在使用数值（分），与 tutorial_scanner 的 SCORING 常量对齐：
    - D1 内容深度 25   - D2 结构 20   - D3 代码 15
    - D4 教学 15       - D5 参考 10   - D6 可读性 15
    """
    ch_num = chapter_data.get("number", 0)
    current_score = chapter_data.get("quality_score", 0)
    score_detail = chapter_data.get("score_detail", {})
    dims = score_detail.get("dimensions", {})
    h2_sections = chapter_data.get("h2_sections", [])
    content_info = chapter_data.get("content", {})
    structure = chapter_data.get("structure", {})
    defects = chapter_data.get("defects", [])
    wc = chapter_data.get("word_count", 0)

    improvements = []
    missing_sections = []
    weak_sections = []
    seen_targets = set()   # 防止相同 target 的重复 improvement

    # ── 1. 检查必需段落是否存在 ──
    section_titles = [s.get("title", "") for s in h2_sections]

    for req_sec, patterns in SECTION_PATTERNS.items():
        found = False
        for title in section_titles:
            for pat in patterns:
                if re.search(pat, title, re.IGNORECASE):
                    found = True
                    break
            if found:
                break

        if not found:
            if req_sec == "Core_Content":
                if structure.get("h2", 0) < 3:
                    missing_sections.append(req_sec)
                    improvements.append({
                        "type": "add_section",
                        "target": req_sec,
                        "dimension": "D2_structure",
                        "description": f"核心内容H2段落不足3个(当前{structure.get('h2', 0)}个)，需补充",
                        "estimated_impact": 6,       # D2: H2 >= 5 → +6
                        "effort": "high",
                        "priority": 1,
                    })
                    seen_targets.add(req_sec)
            elif req_sec == "Introduction":
                # 首个 H2 可能充当引言 — 仅在无任何 H2 时报缺失
                if structure.get("h2", 0) == 0:
                    missing_sections.append(req_sec)
                    improvements.append({
                        "type": "add_section",
                        "target": req_sec,
                        "dimension": "D2_structure",
                        "description": "缺少引言/概述段落",
                        "estimated_impact": 4,
                        "effort": "medium",
                        "priority": 2,
                    })
                    seen_targets.add(req_sec)
            elif req_sec == "FAQ":
                missing_sections.append(req_sec)
                improvements.append({
                    "type": "add_section",
                    "target": req_sec,
                    "dimension": "D4_pedagogy",     # FAQ 仅计入教学维度
                    "description": "缺少「FAQ/常见问题」段落",
                    "estimated_impact": 4,           # D4: FAQ → +4
                    "effort": "medium",
                    "priority": 2,
                })
                seen_targets.add(req_sec)
            elif req_sec == "Summary":
                missing_sections.append(req_sec)
                improvements.append({
                    "type": "add_section",
                    "target": req_sec,
                    "dimension": "D4_pedagogy",
                    "description": "缺少「本章小结」段落",
                    "estimated_impact": 3,           # D4: summary → +3
                    "effort": "low",
                    "priority": 3,
                })
                seen_targets.add(req_sec)
            elif req_sec == "References":
                if "References" not in seen_targets:
                    missing_sections.append(req_sec)
                    improvements.append({
                        "type": "add_section",
                        "target": req_sec,
                        "dimension": "D5_references",
                        "description": "缺少「参考来源」段落，至少包含3个可信链接",
                        "estimated_impact": 4,       # D5: has_references → +4
                        "effort": "low",
                        "priority": 2,
                    })
                    seen_targets.add(req_sec)
            else:
                # Examples, Troubleshooting
                missing_sections.append(req_sec)
                improvements.append({
                    "type": "add_section",
                    "target": req_sec,
                    "dimension": "D4_pedagogy",
                    "description": f"缺少「{req_sec}」段落，需要添加",
                    "estimated_impact": 4,
                    "effort": "medium",
                    "priority": 2,
                })
                seen_targets.add(req_sec)

    # ── 2. 检查薄弱段落 ──
    for sec in h2_sections:
        sec_wc = sec.get("word_count", 0)
        if sec_wc < 50:
            weak_sections.append({
                "section": sec["title"],
                "reason": "内容过短 (<50字)",
                "word_count": sec_wc,
                "line": sec.get("line", 0),
            })
            improvements.append({
                "type": "enrich_content",
                "target": sec["title"],
                "dimension": "D6_readability",
                "description": f"「{sec['title']}」仅{sec_wc}字，需扩展到200字以上",
                "estimated_impact": 3,
                "effort": "medium",
                "priority": 2,
            })
        elif sec_wc < 150:
            weak_sections.append({
                "section": sec["title"],
                "reason": "内容偏短 (<150字)",
                "word_count": sec_wc,
                "line": sec.get("line", 0),
            })
            improvements.append({
                "type": "enrich_content",
                "target": sec["title"],
                "dimension": "D6_readability",
                "description": f"「{sec['title']}」仅{sec_wc}字，建议扩展到300字以上",
                "estimated_impact": 2,
                "effort": "low",
                "priority": 3,
            })

    # ── 3. 结构问题修复 ──
    heading_jumps = structure.get("heading_jumps", [])
    for jump in heading_jumps:
        improvements.append({
            "type": "fix_structure",
            "target": "标题层级",
            "dimension": "penalty_reduction",
            "description": f"修复标题跳级: {jump}",
            "estimated_impact": 3,    # 减少 major 扣分
            "effort": "low",
            "priority": 1,
        })

    if not structure.get("has_nav", False):
        improvements.append({
            "type": "fix_structure",
            "target": "章节导航",
            "dimension": "D2_structure",
            "description": "添加章首和章尾导航链接",
            "estimated_impact": 3,    # D2: nav_bonus = 3
            "effort": "low",
            "priority": 2,
        })

    if not structure.get("has_toc", False):
        improvements.append({
            "type": "fix_structure",
            "target": "本章目录",
            "dimension": "D2_structure",
            "description": "添加本章目录(TOC)，链接到各H2段落",
            "estimated_impact": 2,    # D2: toc_bonus = 2
            "effort": "low",
            "priority": 3,
        })

    # ── 4. 代码示例补充 ──
    code_blocks = content_info.get("code_blocks", 0)
    if code_blocks < 3:
        improvements.append({
            "type": "add_example",
            "target": "代码示例",
            "dimension": "D3_code_quality",
            "description": f"当前仅{code_blocks}个代码块，至少需要3个完整的CLI/代码示例",
            "estimated_impact": 7,    # D3: code >= 3 → 7 分
            "effort": "medium",
            "priority": 1,
        })

    unlabeled = content_info.get("unlabeled_code_blocks", 0)
    if unlabeled > 0:
        improvements.append({
            "type": "fix_format",
            "target": "代码块标注",
            "dimension": "D3_code_quality",
            "description": f"{unlabeled}个代码块缺少语言标注",
            "estimated_impact": 2,    # D3: label_ratio → 0-2
            "effort": "low",
            "priority": 3,
        })

    if not content_info.get("has_cli_examples", False):
        improvements.append({
            "type": "add_example",
            "target": "CLI 示例",
            "dimension": "D3_code_quality",
            "description": "缺少 OpenClaw CLI 命令示例，需添加实际可运行的命令",
            "estimated_impact": 3,    # D3: has_cli → +3
            "effort": "medium",
            "priority": 2,
        })

    # ── 5. 参考来源 ──
    if "References" not in seen_targets and not content_info.get("has_references", False):
        improvements.append({
            "type": "add_section",
            "target": "References",
            "dimension": "D5_references",
            "description": "添加参考来源段落，至少包含3个可信链接",
            "estimated_impact": 4,
            "effort": "low",
            "priority": 2,
        })
        seen_targets.add("References")

    ext_links = content_info.get("links_external", 0)
    if ext_links < 3:
        improvements.append({
            "type": "add_reference",
            "target": "外部链接",
            "dimension": "D5_references",
            "description": f"外部链接仅{ext_links}个，建议至少3个官方/权威来源",
            "estimated_impact": 3 if ext_links == 0 else 3,
            "effort": "low",
            "priority": 3,
        })

    # ── 6. 内容充实度 ──
    if wc < 1000:
        improvements.append({
            "type": "enrich_content",
            "target": "全章",
            "dimension": "D1_content_depth",
            "description": f"总字数{wc}偏低，目标>=1500字",
            "estimated_impact": 12,   # D1: 从 7→18 分的差距
            "effort": "high",
            "priority": 1,
        })
    elif wc < 1500:
        improvements.append({
            "type": "enrich_content",
            "target": "全章",
            "dimension": "D1_content_depth",
            "description": f"总字数{wc}偏少，目标>=2000字",
            "estimated_impact": 4,    # D1: 从 13→18 分
            "effort": "medium",
            "priority": 2,
        })

    # ── 7. 基于缺陷的修复 ──
    placeholder_defects = [d for d in defects if d.get("type") == "placeholder"]
    if placeholder_defects:
        improvements.append({
            "type": "fix_content",
            "target": "占位符",
            "dimension": "penalty_reduction",
            "description": f"发现{len(placeholder_defects)}处占位符文本需替换为实际内容",
            "estimated_impact": len(placeholder_defects) * 5,  # critical: 5/个
            "effort": "medium",
            "priority": 1,
        })

    dense_defects = [d for d in defects if d.get("type") == "dense_block"]
    if dense_defects:
        improvements.append({
            "type": "fix_format",
            "target": "排版密度",
            "dimension": "penalty_reduction",
            "description": f"发现{len(dense_defects)}处连续密排(>30行无空行)，需插入空行",
            "estimated_impact": len(dense_defects) * 3,  # major: 3/个
            "effort": "low",
            "priority": 3,
        })

    # ── 8. 可读性增强（表格/图片） ──
    if content_info.get("tables", 0) == 0:
        improvements.append({
            "type": "add_element",
            "target": "表格",
            "dimension": "D6_readability",
            "description": "缺少表格，建议添加对比表或配置参数表",
            "estimated_impact": 2,    # D6: tables >= 1 → +2
            "effort": "low",
            "priority": 3,
        })

    # ── 计算优先级 ──
    improvements.sort(key=lambda x: x.get("priority", 5))

    # 预估目标分 (直接数值求和)
    impact_total = sum(imp.get("estimated_impact", 0) for imp in improvements)
    target_score = min(100, round(current_score + impact_total))

    # 优先级分类 — 使用渐进式阈值
    missing_count = len(missing_sections)
    if current_score < 40 or missing_count >= 4:
        priority = "high"
    elif current_score < 60 or missing_count >= 2:
        priority = "high"
    elif current_score < 80 or missing_count >= 1:
        priority = "medium"
    else:
        priority = "low"

    return {
        "chapter": ch_num,
        "file": chapter_data.get("file", ""),
        "title": chapter_data.get("title", ""),
        "current_score": current_score,
        "target_score": target_score,
        "score_detail": dims,
        "priority": priority,
        "improvements": improvements,
        "missing_sections": missing_sections,
        "weak_sections": weak_sections,
        "improvement_count": len(improvements),
        "estimated_effort": _estimate_total_effort(improvements),
    }


def _estimate_total_effort(improvements: list) -> str:
    """估算总工作量。"""
    effort_map = {"low": 1, "medium": 2, "high": 3}
    total = sum(effort_map.get(imp.get("effort", "medium"), 2) for imp in improvements)
    if total <= 3:
        return "low"
    elif total <= 8:
        return "medium"
    else:
        return "high"


def analyze_all(scan_report: dict = None) -> dict:
    """分析所有章节，生成完整优化计划。"""
    if scan_report is None:
        scan_path = os.path.join(OUTPUT_DIR, "scan-report.json")
        scan_report = load_json(scan_path)
        if not scan_report:
            log.error(f"扫描报告不存在: {scan_path}，请先运行 tutorial_scanner")
            return {"error": "scan-report.json not found"}

    chapters = scan_report.get("chapters", [])
    log.info(f"分析 {len(chapters)} 个章节质量...")

    analyses = []
    for ch in chapters:
        if "error" in ch:
            continue
        analysis = analyze_chapter(ch)
        analyses.append(analysis)
        log.info(f"  [{ch.get('number', 0):02d}] {analysis['priority'].upper()} "
                  f"score={analysis['current_score']}→{analysis['target_score']} "
                  f"({analysis['improvement_count']}项优化)")

    # 按优先级和评分排序 (低分 + high 优先级排前面)
    analyses.sort(key=lambda a: (
        {"high": 0, "medium": 1, "low": 2}.get(a["priority"], 3),
        a["current_score"],
    ))

    # 汇总统计
    high_priority = [a for a in analyses if a["priority"] == "high"]
    medium_priority = [a for a in analyses if a["priority"] == "medium"]
    low_priority = [a for a in analyses if a["priority"] == "low"]

    all_improvements = []
    for a in analyses:
        all_improvements.extend(a.get("improvements", []))

    report = {
        "analysis_time": datetime.now(tz=timezone.utc).isoformat(),
        "total_chapters_analyzed": len(analyses),
        "priority_distribution": {
            "high": len(high_priority),
            "medium": len(medium_priority),
            "low": len(low_priority),
        },
        "total_improvements": len(all_improvements),
        "improvement_type_counts": _count_improvement_types(all_improvements),
        "optimization_queue": [
            {"chapter": a["chapter"], "file": a["file"], "priority": a["priority"],
             "score": a["current_score"], "target": a["target_score"],
             "improvements": a["improvement_count"]}
            for a in analyses
        ],
        "chapters": analyses,
        "recommendations": _generate_recommendations(analyses, scan_report),
    }

    return report


def _count_improvement_types(improvements: list) -> dict:
    """统计各类改进项数量。"""
    counts = {}
    for imp in improvements:
        t = imp.get("type", "unknown")
        counts[t] = counts.get(t, 0) + 1
    return counts


def _generate_recommendations(analyses: list, scan_report: dict) -> list:
    """生成全局优化建议。"""
    recs = []

    # 缺失章节
    missing = scan_report.get("missing_chapters", [])
    if missing:
        recs.append({
            "type": "create_chapters",
            "description": f"创建缺失的 {len(missing)} 个章节: {missing}",
            "priority": "high",
        })

    # 最需优化的章节
    high_pri = [a for a in analyses if a["priority"] == "high"]
    if high_pri:
        recs.append({
            "type": "optimize_urgent",
            "description": f"优先优化 {len(high_pri)} 个高优先级章节: "
                          f"{[a['chapter'] for a in high_pri[:5]]}",
            "priority": "high",
        })

    # 全局缺失段落
    all_missing = set()
    for a in analyses:
        all_missing.update(a.get("missing_sections", []))
    if all_missing:
        recs.append({
            "type": "add_missing_sections",
            "description": f"多章缺失以下段落类型: {list(all_missing)}",
            "priority": "medium",
        })

    # 格式统一
    total_defects = sum(len(a.get("weak_sections", [])) for a in analyses)
    if total_defects > 0:
        recs.append({
            "type": "format_cleanup",
            "description": f"共{total_defects}个薄弱段落需要内容扩充",
            "priority": "medium",
        })

    return recs


def run():
    """主入口: 分析并保存报告。"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    report = analyze_all()

    if "error" in report:
        log.error(report["error"])
        return report

    out_path = os.path.join(OUTPUT_DIR, "analysis-report.json")
    save_json(out_path, report)
    log.info(f"分析报告已保存: {out_path}")
    log.info(f"  优先级分布: {report['priority_distribution']}")
    log.info(f"  总优化项: {report['total_improvements']}")

    return report


if __name__ == "__main__":
    run()
