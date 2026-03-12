#!/usr/bin/env python3
"""
modules/llm_expander.py — LLM 自动内容扩写分析器
====================================================
分析教程章节中需要扩写的薄弱段落，生成扩写建议和 Prompt。

功能:
  - 识别短段落 (< min_words 阈值)
  - 分析内容覆盖度 (缺失的维度)
  - 生成结构化扩写建议
  - 输出可直接用于 LLM 的 Prompt

用法:
  from modules.llm_expander import analyze_expansion_needs
  report = analyze_expansion_needs(scan_report, analysis_report)
"""

import os
import re
from datetime import datetime, timezone
from typing import Any

from modules.compat import setup_logger

log = setup_logger("llm_expander")

# ── 默认配置 ──
DEFAULT_CONFIG = {
    "min_section_words": 80,       # 段落最小字数
    "min_chapter_words": 3000,     # 章节最小总字数
    "target_chapter_words": 5000,  # 章节目标字数
    "max_prompts_per_chapter": 5,  # 每章最多生成的 Prompt 数
    "expand_dimensions": [
        "content_depth",     # 内容深度 (缺少示例/解释)
        "pedagogy",          # 教学性 (缺少提示/警告/进阶)
        "code_quality",      # 代码质量 (缺少 CLI 命令)
        "readability",       # 可读性 (缺少表格/图示)
    ],
    "language": "zh-CN",
}

# ── 扩写建议模板 ──
EXPANSION_TEMPLATES = {
    "short_section": {
        "zh-CN": (
            "## 段落扩写\n"
            "章节「{chapter}」的段落「{section}」仅 {word_count} 字，建议扩展到 {target} 字以上。\n\n"
            "扩写方向：\n"
            "1. 添加更多具体示例\n"
            "2. 补充原理说明或最佳实践\n"
            "3. 添加对比表格或流程图\n"
        ),
        "en": (
            "## Section Expansion\n"
            "Section '{section}' in chapter '{chapter}' has only {word_count} words. "
            "Recommend expanding to {target}+ words.\n\n"
            "Expansion directions:\n"
            "1. Add more concrete examples\n"
            "2. Add principles or best practices\n"
            "3. Add comparison tables or diagrams\n"
        ),
    },
    "missing_cli": {
        "zh-CN": (
            "## 补充 CLI 命令\n"
            "章节「{chapter}」缺少 `openclaw` CLI 命令示例。建议添加：\n"
            "- 相关的 openclaw 子命令示例\n"
            "- 命令参数说明\n"
            "- 常见用法场景\n"
        ),
        "en": (
            "## Add CLI Commands\n"
            "Chapter '{chapter}' lacks `openclaw` CLI command examples. "
            "Recommend adding:\n"
            "- Relevant openclaw subcommand examples\n"
            "- Command parameter descriptions\n"
            "- Common usage scenarios\n"
        ),
    },
    "missing_table": {
        "zh-CN": (
            "## 补充表格\n"
            "章节「{chapter}」缺少表格（当前 {table_count} 个，建议 ≥2）。\n"
            "可以添加：\n"
            "- 参数/选项对比表\n"
            "- 功能特性速查表\n"
            "- 常见问题速查表\n"
        ),
        "en": (
            "## Add Tables\n"
            "Chapter '{chapter}' lacks tables (current: {table_count}, recommend ≥2).\n"
            "Consider adding:\n"
            "- Parameter/option comparison table\n"
            "- Feature quick reference table\n"
            "- FAQ quick reference table\n"
        ),
    },
    "missing_advanced": {
        "zh-CN": (
            "## 补充进阶内容\n"
            "章节「{chapter}」缺少进阶/架构类 H2 段落。建议添加：\n"
            "- 「进阶：XXX 架构原理」H2 段落\n"
            "- 内部实现机制说明\n"
            "- 性能优化建议\n"
        ),
        "en": (
            "## Add Advanced Content\n"
            "Chapter '{chapter}' lacks advanced/architecture H2 sections. "
            "Recommend adding:\n"
            "- 'Advanced: XXX Architecture' H2 section\n"
            "- Internal implementation details\n"
            "- Performance optimization tips\n"
        ),
    },
    "missing_caution": {
        "zh-CN": (
            "## 补充注意事项\n"
            "章节「{chapter}」缺少注意事项/常见错误 H2 段落。建议添加：\n"
            "- 「注意事项与常见错误」H2 段落\n"
            "- 常见错误及其后果\n"
            "- 正确做法对比表\n"
        ),
        "en": (
            "## Add Cautions\n"
            "Chapter '{chapter}' lacks caution/common-errors H2 sections. "
            "Recommend adding:\n"
            "- 'Cautions and Common Errors' H2 section\n"
            "- Common mistakes and consequences\n"
            "- Correct approach comparison table\n"
        ),
    },
}


def analyze_expansion_needs(
    scan_report: dict,
    analysis_report: dict = None,
    config: dict = None,
) -> dict:
    """分析所有章节的扩写需求，生成结构化建议。

    Args:
        scan_report: tutorial_scanner 的扫描结果
        analysis_report: quality_analyzer 的分析结果 (可选)
        config: 自定义配置 (覆盖默认值)

    Returns:
        dict: 扩写分析报告
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    lang = cfg["language"]
    chapters = scan_report.get("chapters", [])

    all_suggestions = []
    total_prompts = 0

    for ch in chapters:
        ch_file = ch.get("file", "")
        ch_title = ch.get("title", ch_file)
        ch_number = ch.get("number", 0)
        word_count = ch.get("word_count", 0)
        score = ch.get("quality_score", ch.get("score", 0))
        content = ch.get("content", {})
        h2_sections = ch.get("h2_sections", [])
        dims = ch.get("score_detail", {}).get("dimensions", {})

        suggestions = []

        # ── 1. 短段落检测 ──
        for sec in h2_sections:
            sec_words = sec.get("word_count", 0)
            if sec_words < cfg["min_section_words"]:
                tpl = EXPANSION_TEMPLATES["short_section"].get(lang, "")
                suggestions.append({
                    "type": "short_section",
                    "section": sec["title"],
                    "current_words": sec_words,
                    "target_words": cfg["min_section_words"],
                    "priority": "high" if sec_words < 30 else "medium",
                    "prompt": tpl.format(
                        chapter=ch_title,
                        section=sec["title"],
                        word_count=sec_words,
                        target=cfg["min_section_words"],
                    ),
                })

        # ── 2. 章节总字数不足 ──
        if word_count < cfg["min_chapter_words"]:
            gap = cfg["target_chapter_words"] - word_count
            suggestions.append({
                "type": "low_word_count",
                "current_words": word_count,
                "target_words": cfg["target_chapter_words"],
                "gap": gap,
                "priority": "high",
                "prompt": (
                    f"章节「{ch_title}」当前 {word_count} 字，目标 {cfg['target_chapter_words']} 字。"
                    f"需要扩写约 {gap} 字。请扩充内容深度，添加更多示例和解释。"
                ),
            })

        # ── 3. 缺少 CLI 命令 ──
        if not content.get("has_cli_examples", False):
            tpl = EXPANSION_TEMPLATES["missing_cli"].get(lang, "")
            suggestions.append({
                "type": "missing_cli",
                "priority": "medium",
                "prompt": tpl.format(chapter=ch_title),
            })

        # ── 4. 缺少表格 ──
        table_count = content.get("tables", 0)
        if table_count < 2:
            tpl = EXPANSION_TEMPLATES["missing_table"].get(lang, "")
            suggestions.append({
                "type": "missing_table",
                "current_count": table_count,
                "priority": "medium",
                "prompt": tpl.format(chapter=ch_title, table_count=table_count),
            })

        # ── 5. 缺少进阶内容 ──
        h2_titles = [sec["title"] for sec in h2_sections]
        advanced_kw = ("高级", "进阶", "深入", "原理", "架构")
        has_advanced = any(
            any(kw in t for kw in advanced_kw) for t in h2_titles
        )
        if not has_advanced:
            tpl = EXPANSION_TEMPLATES["missing_advanced"].get(lang, "")
            suggestions.append({
                "type": "missing_advanced",
                "priority": "medium",
                "prompt": tpl.format(chapter=ch_title),
            })

        # ── 6. 缺少注意事项 ──
        caution_kw = ("注意", "常见错误", "踩坑", "陷阱", "最佳实践")
        has_caution = any(
            any(kw in t for kw in caution_kw) for t in h2_titles
        )
        if not has_caution:
            tpl = EXPANSION_TEMPLATES["missing_caution"].get(lang, "")
            suggestions.append({
                "type": "missing_caution",
                "priority": "medium",
                "prompt": tpl.format(chapter=ch_title),
            })

        # 限制每章 Prompt 数量
        suggestions = suggestions[:cfg["max_prompts_per_chapter"]]
        total_prompts += len(suggestions)

        if suggestions:
            all_suggestions.append({
                "chapter": ch_number,
                "file": ch_file,
                "title": ch_title,
                "score": score,
                "word_count": word_count,
                "suggestion_count": len(suggestions),
                "suggestions": suggestions,
            })

    # 按建议数量排序 (多的先处理)
    all_suggestions.sort(key=lambda x: (-x["suggestion_count"], x["chapter"]))

    # 优先级分布
    priority_dist = {"high": 0, "medium": 0, "low": 0}
    for ch_sug in all_suggestions:
        for s in ch_sug["suggestions"]:
            p = s.get("priority", "low")
            priority_dist[p] = priority_dist.get(p, 0) + 1

    report = {
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "config": cfg,
        "total_chapters": len(chapters),
        "chapters_needing_expansion": len(all_suggestions),
        "total_suggestions": total_prompts,
        "priority_distribution": priority_dist,
        "chapters": all_suggestions,
    }

    log.info(f"  扩写分析: {len(all_suggestions)}/{len(chapters)} 章节需要扩写")
    log.info(f"  总建议数: {total_prompts}")
    log.info(f"  优先级: {priority_dist}")

    return report


def generate_expansion_prompts(
    expansion_report: dict,
    output_dir: str = None,
) -> list[dict]:
    """将扩写分析结果转换为可执行的 LLM Prompt 列表。

    Args:
        expansion_report: analyze_expansion_needs 的输出
        output_dir: 可选的输出目录（保存 Prompt 文件）

    Returns:
        list: 结构化 Prompt 列表
    """
    prompts = []

    for ch_sug in expansion_report.get("chapters", []):
        ch_title = ch_sug["title"]
        ch_file = ch_sug["file"]

        for sug in ch_sug.get("suggestions", []):
            prompt_entry = {
                "chapter": ch_sug["chapter"],
                "file": ch_file,
                "title": ch_title,
                "type": sug["type"],
                "priority": sug.get("priority", "medium"),
                "prompt": sug.get("prompt", ""),
            }
            prompts.append(prompt_entry)

    # 按优先级排序
    priority_order = {"high": 0, "medium": 1, "low": 2}
    prompts.sort(key=lambda p: (priority_order.get(p["priority"], 9), p["chapter"]))

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        import json
        output_path = os.path.join(output_dir, "expansion-prompts.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(prompts, f, ensure_ascii=False, indent=2)
        log.info(f"  Prompt 已保存: {output_path} ({len(prompts)} 条)")

    return prompts
