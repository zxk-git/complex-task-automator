#!/usr/bin/env python3
"""
tutorial_refiner.py — 教程内容精炼优化器
=========================================
根据质量分析报告的优化计划，对教程章节进行精准优化。
核心引擎：读取分析报告 → 按优先级处理 → 应用增量修改 → 输出优化后文件。
属于优化流水线的第三阶段。

输入: {OUTPUT_DIR}/analysis-report.json + 章节文件
输出: 修改后的章节文件 + {OUTPUT_DIR}/refine-result.json
"""

from datetime import datetime, timezone
from pathlib import Path
import json
import os
import re
import shutil
import sys

from modules.types import ChapterAnalysis, RefineResult

_PROMPTS = os.path.join(os.path.dirname(__file__), "..", "prompts")
from modules.compat import (
    setup_logger, cfg, load_json, save_json, word_count,
    read_file_safe, PROJECT_DIR, OUTPUT_DIR, DRY_RUN,
)

_read_file = read_file_safe

log = setup_logger("tutorial_refiner")


# ── 导航信息缓存 ────────────────────────────────────
def _get_chapter_nav_info(project_dir: str) -> dict:
    """获取所有章节的导航信息（上一章/下一章）。"""
    files = sorted(
        f for f in os.listdir(project_dir)
        if re.match(r"\d+.*\.md$", f) and not f.endswith(".bak")
    )
    nav = {}
    for i, fname in enumerate(files):
        m = re.match(r"(\d+)-(.+)\.md", fname)
        if not m:
            continue
        num = int(m.group(1))
        title = m.group(2).replace("-", " ")
        prev_file = files[i - 1] if i > 0 else None
        next_file = files[i + 1] if i < len(files) - 1 else None

        prev_title = ""
        if prev_file:
            pm = re.match(r"\d+-(.+)\.md", prev_file)
            prev_title = pm.group(1).replace("-", " ") if pm else ""

        next_title = ""
        if next_file:
            nm = re.match(r"\d+-(.+)\.md", next_file)
            next_title = nm.group(1).replace("-", " ") if nm else ""

        nav[num] = {
            "file": fname,
            "title": title,
            "prev_file": prev_file,
            "prev_title": prev_title,
            "next_file": next_file,
            "next_title": next_title,
        }
    return nav


# ── 精炼操作实现 ────────────────────────────────────

# ── P0: 代码块修复 ──

def fix_broken_code_closings(text: str) -> tuple:
    """修复代码块关闭标记被错误追加语言标签的 BUG。

    例如 ```bash ... ```text 应为 ```bash ... ```
    也处理引用块内的代码块 (> ```text → > ```)
    """
    lines = text.split("\n")
    new_lines = []
    in_code = False
    changes = []

    for i, line in enumerate(lines):
        # 提取前缀 (支持 "> " 引用块前缀)
        prefix = ""
        content = line
        bq_match = re.match(r'^(>\s*)', line)
        if bq_match:
            prefix = bq_match.group(1)
            content = line[len(prefix):]

        stripped = content.strip()
        if stripped.startswith("```"):
            lang_part = stripped[3:].strip()
            if not in_code:
                in_code = True
                new_lines.append(line)
            elif lang_part:
                # 关闭时不应带语言标签 → 修复为纯关闭
                new_lines.append(prefix + "```")
                changes.append(f"L{i+1}: fixed ```{lang_part} → ```")
                in_code = False
            else:
                new_lines.append(line)
                in_code = False
        else:
            new_lines.append(line)

    if changes:
        return "\n".join(new_lines), changes
    return text, []


# ── P1: 爬虫残留清洗 ──

def clean_raw_scrape_artifacts(text: str) -> tuple:
    """移除 AI 优化过程中混入的原始搜索/爬虫结果。"""
    changes = []

    # 移除 "### 补充 N" 及其后续内容 (直到下一个 H2 或文件末尾)
    pattern = r"\n### 补充 \d+\n.*?(?=\n## |\Z)"
    matches = re.findall(pattern, text, re.DOTALL)
    if matches:
        text = re.sub(pattern, "", text, flags=re.DOTALL)
        changes.append(f"removed {len(matches)} raw scrape artifact blocks")

    # 移除引用块内的 "### 补充 N" (> ### 补充 1)
    bq_pattern = r"\n(?:>\s*)?### 补充 \d+\n(?:>.*\n)*"
    bq_matches = re.findall(bq_pattern, text)
    if bq_matches:
        text = re.sub(bq_pattern, "\n", text)
        changes.append(f"removed {len(bq_matches)} blockquoted scrape artifacts")

    # 移除裸 URL 搜索结果格式 (- **标题** (relevance: N%))
    relevance_pattern = r"\n-\s*\*\*[^*]+\*\*\s*\(relevance:\s*\d+%\).*\n?"
    rel_matches = re.findall(relevance_pattern, text)
    if rel_matches:
        text = re.sub(relevance_pattern, "\n", text)
        changes.append(f"removed {len(rel_matches)} relevance-tagged search results")

    # 去重 "## 最新动态与补充" 段落 (全部删除 — 这些是爬虫产物)
    update_pattern = r"\n## 最新动态与补充\n.*?(?=\n## |\Z)"
    update_blocks = list(re.finditer(update_pattern, text, re.DOTALL))
    if update_blocks:
        for m in reversed(update_blocks):
            text = text[:m.start()] + text[m.end():]
        changes.append(f"removed {len(update_blocks)} '最新动态与补充' blocks")

    return (text, changes) if changes else (text, [])


# ── P1: GitHub Alert 语法统一 ──

def convert_to_github_alerts(text: str) -> tuple:
    """将旧式提示/警告格式转换为 GitHub 原生 Alert 语法。

    > **💡 提示**：... → > [!TIP]\\n> ...
    > **⚠️ 注意**：... → > [!WARNING]\\n> ...
    > **📌 关键**：... → > [!IMPORTANT]\\n> ...
    > **提示**：...    → > [!TIP]\\n> ...
    """
    replacements = [
        (r">\s*\*\*💡\s*提示\*\*[：:]\s*", "> [!TIP]\n> "),
        (r">\s*\*\*⚠️\s*注意\*\*[：:]\s*", "> [!WARNING]\n> "),
        (r">\s*\*\*📌\s*关键\*\*[：:]\s*", "> [!IMPORTANT]\n> "),
        (r">\s*\*\*❗\s*警告\*\*[：:]\s*", "> [!CAUTION]\n> "),
        (r">\s*\*\*📝\s*备注\*\*[：:]\s*", "> [!NOTE]\n> "),
        (r">\s*\*\*提示\*\*[：:]\s*", "> [!TIP]\n> "),
        (r">\s*\*\*注意\*\*[：:]\s*", "> [!WARNING]\n> "),
    ]
    changes = []
    for pat, repl in replacements:
        if re.search(pat, text):
            count = len(re.findall(pat, text))
            text = re.sub(pat, repl, text)
            changes.append(f"converted {count} alerts: {pat[:30]}")
    return (text, changes) if changes else (text, [])


# ── P2: 章节头部视觉增强 ──

_DIFFICULTY_MAP = {
    range(0, 40): ("⭐", "入门", "brightgreen"),
    range(40, 60): ("⭐⭐", "基础", "green"),
    range(60, 75): ("⭐⭐⭐", "进阶", "orange"),
    range(75, 90): ("⭐⭐⭐⭐", "高级", "red"),
    range(90, 101): ("⭐⭐⭐⭐⭐", "专家", "critical"),
}


def _get_difficulty(readability_score: int) -> tuple:
    for rng, info in _DIFFICULTY_MAP.items():
        if readability_score in rng:
            return info
    return ("⭐⭐⭐", "进阶", "orange")


def enhance_chapter_header(text: str, chapter_num: int, chapter_title: str,
                           word_cnt: int = 0, readability_score: int = 50) -> tuple:
    """在 H1 标题下方添加 shields.io 徽章和章节概要框。
    若已有徽章，则更新难度等级以保持一致性。同时同步正文元数据行。"""
    stars, label, color = _get_difficulty(readability_score)
    minutes = max(5, word_cnt // 250) if word_cnt else 20
    changes = []

    badge_line = (
        f"![difficulty](https://img.shields.io/badge/难度-{stars}_{label}-{color})"
        f" ![time](https://img.shields.io/badge/阅读时间-{minutes}_分钟-blue)"
        f" ![chapter](https://img.shields.io/badge/章节-{chapter_num:02d}%2F21-purple)"
    )

    # 更新已有徽章
    badge_pattern = r'!\[difficulty\]\(https://img\.shields\.io/badge/难度-[^)]*\)' \
                    r'\s*!\[time\]\(https://img\.shields\.io/badge/阅读时间-[^)]*\)' \
                    r'\s*!\[chapter\]\(https://img\.shields\.io/badge/章节-[^)]*\)'
    if re.search(badge_pattern, text):
        old = re.search(badge_pattern, text).group()
        if old != badge_line:
            text = re.sub(badge_pattern, badge_line, text)
            changes.append(f"updated chapter badges (difficulty={stars} {label})")
    elif "img.shields.io/badge" not in text:
        # 无徽章 → 在 H1 后插入
        h1_match = re.search(r"^(#\s+.+)$", text, re.MULTILINE)
        if h1_match:
            end = h1_match.end()
            text = text[:end] + "\n\n" + badge_line + "\n" + text[end:]
            changes.append("added chapter badges (difficulty, reading time)")

    # 同步正文元数据行
    meta_pattern = r'>\s*\*\*难度\*\*:\s*⭐[⭐]*\s*\S+'
    meta_replacement = f'> **难度**: {stars} {label}'
    meta_match = re.search(meta_pattern, text)
    if meta_match:
        old_meta = meta_match.group()
        if stars not in old_meta or label not in old_meta:
            text = re.sub(meta_pattern, meta_replacement, text)
            changes.append(f"synced text difficulty to {stars} {label}")

    return (text, changes) if changes else (text, [])


def _build_header_nav(info: dict) -> str:
    """构建居中的章首导航 HTML 块。"""
    parts = []
    if info["prev_file"]:
        prev_num = re.match(r"(\d+)", info["prev_file"])
        pn = prev_num.group(1) if prev_num else ""
        parts.append(f"[← 第 {pn} 章]({info['prev_file']})")
    parts.append("[📑 目录](README.md)")
    parts.append("[📋 大纲](OUTLINE.md)")
    if info["next_file"]:
        next_num = re.match(r"(\d+)", info["next_file"])
        nn = next_num.group(1) if next_num else ""
        parts.append(f"[第 {nn} 章 →]({info['next_file']})")
    return '<div align="center">\n\n' + " · ".join(parts) + "\n\n</div>"


def _build_footer_nav(info: dict) -> str:
    """构建居中的章尾导航 HTML 块。"""
    parts = []
    if info["prev_file"]:
        parts.append(f"[← 上一章：{info['prev_title']}]({info['prev_file']})")
    parts.append("[📑 返回目录](README.md)")
    if info["next_file"]:
        parts.append(f"[下一章：{info['next_title']} →]({info['next_file']})")
    return '---\n\n<div align="center">\n\n' + " · ".join(parts) + "\n\n</div>"


# 导航检测正则：匹配旧格式（blockquote）和新格式（div centered）
_RE_NAV_HEADER = re.compile(
    r'\[←\s*上一章|\[目录\]\(README\.md\)|<div align="center">.*\[📑 目录\]',
    re.DOTALL,
)
_RE_NAV_FOOTER = re.compile(
    r'📖\s*章节导航|<div align="center">.*\[📑 返回目录\]',
    re.DOTALL,
)


def add_chapter_navigation(text: str, chapter_num: int, nav_info: dict) -> tuple:
    """添加章首和章尾导航（居中 HTML 格式）。返回 (修改后文本, 变更描述)。"""
    info = nav_info.get(chapter_num)
    if not info:
        return text, []

    changes = []

    # 章首导航
    if not _RE_NAV_HEADER.search(text[:800]):
        header = _build_header_nav(info)
        text = header + "\n\n" + text
        changes.append("added header navigation")

    # 章尾导航
    if not _RE_NAV_FOOTER.search(text[-800:]):
        footer = _build_footer_nav(info)
        text = text.rstrip() + "\n\n" + footer + "\n"
        changes.append("added footer navigation")

    return text, changes if changes else []


def add_toc(text: str) -> tuple:
    """在 H1 标题后添加本章目录。返回 (修改后文本, 变更描述)。"""
    # 检测已有 TOC（包含所有变体）
    if re.search(r"##\s+.*(?:📑?\s*本章目录|📖?\s*目录|Table of Contents)", text):
        return text, []

    # 提取 H2 标题
    h2s = re.findall(r"^##\s+(.+)$", text, re.MULTILINE)
    if not h2s:
        return text, []

    toc_lines = ["## 📑 本章目录", ""]
    for title in h2s:
        title_clean = title.strip()
        # 生成锚点
        anchor = re.sub(r"[^\w\u4e00-\u9fff\s-]", "", title_clean)
        anchor = anchor.strip().lower().replace(" ", "-")
        toc_lines.append(f"- [{title_clean}](#{anchor})")
    toc_lines.append("")
    toc_block = "\n".join(toc_lines)

    # 在 H1 后插入
    h1_match = re.search(r"^#\s+.+$", text, re.MULTILINE)
    if h1_match:
        insert_pos = h1_match.end()
        # 跳过紧跟的元数据行（难度、阅读时间等）
        remaining = text[insert_pos:]
        meta_match = re.match(r"\n+(?:>.*\n)*\n*", remaining)
        if meta_match:
            insert_pos += meta_match.end()
        text = text[:insert_pos] + "\n\n" + toc_block + "\n" + text[insert_pos:]
        return text, ["added table of contents"]

    return text, []


def fix_heading_jumps(text: str) -> tuple:
    """修复标题层级跳跃。

    当检测到 H2→H4 这类跳跃时，将原标题降级到正确的层级 (H3)，
    而不是插入多余的中间标题。支持多级跳跃 (如 H2→H5 修正为 H3)。
    """
    lines = text.split("\n")
    changes = []
    prev_level = 0
    new_lines = []

    for line in lines:
        m = re.match(r"^(#{1,6})\s+(.+)", line)
        if m:
            level = len(m.group(1))
            if prev_level > 0 and level > prev_level + 1:
                # 将当前标题降到 prev_level + 1
                correct_level = prev_level + 1
                fixed_heading = "#" * correct_level + " " + m.group(2)
                new_lines.append(fixed_heading)
                changes.append(f"H{level}→H{correct_level} (was H{prev_level}→H{level})")
                prev_level = correct_level
            else:
                new_lines.append(line)
                prev_level = level
        else:
            new_lines.append(line)

    if changes:
        return "\n".join(new_lines), changes
    return text, []


def add_code_language_labels(text: str) -> tuple:
    """为未标注语言的代码块添加语言标注。"""
    changes = []

    def _infer_language(code_block: str) -> str:
        if re.search(r"openclaw\s|apt\s|pip\s|npm\s|curl\s|git\s|cd\s|ls\s|mkdir\s|docker\s|sudo\s", code_block):
            return "bash"
        if re.search(r"import\s|def\s|class\s|print\(|from\s.*import", code_block):
            return "python"
        if re.search(r"const\s|let\s|var\s|function\s|=>|require\(|module\.exports", code_block):
            return "javascript"
        if re.search(r"^\s*[\w-]+:\s", code_block, re.MULTILINE):
            return "yaml"
        if re.search(r'^\s*[{"]', code_block):
            return "json"
        if re.search(r"✓|✅|❌|→|──|═|╔", code_block):
            return "text"
        return "text"

    def _replace_unlabeled(match):
        code = match.group(1)
        lang = _infer_language(code)
        changes.append(f"added '{lang}' to code block")
        return f"```{lang}\n{code}```"

    text = re.sub(r"```\n(.*?)```", _replace_unlabeled, text, flags=re.DOTALL)

    if changes:
        return text, changes
    return text, []


def add_references_section(text: str, chapter_num: int,
                           collected_refs: dict = None) -> tuple:
    """
    添加参考来源段落。

    优先使用 reference_collector 收集的来源数据 (collected_refs)，
    回退到默认 3 条参考来源。

    Args:
        text: 章节文本
        chapter_num: 章节编号
        collected_refs: reference_collector 的输出 (per-chapter dict)
    """
    if re.search(r"##\s+.*(?:参考来源|参考链接|参考资料|References|延伸阅读)", text, re.IGNORECASE):
        return text, []

    # 优先使用 collected_refs 中的 Markdown 块
    if collected_refs and collected_refs.get("recommended_references_block"):
        refs_block = "\n\n---\n\n" + collected_refs["recommended_references_block"] + "\n"
    elif collected_refs and collected_refs.get("references"):
        # 从 references 列表自行构建
        refs = collected_refs["references"][:8]
        lines = [
            "",
            "---",
            "",
            "## 参考来源",
            "",
            "| 来源 | 链接 | 可信度 | 说明 |",
            "|------|------|--------|------|",
        ]
        for ref in refs:
            title = ref.get("title", "")
            url = ref.get("url", "")
            cred = ref.get("credibility", "D")
            topics = ", ".join(ref.get("topics", [])[:3])
            lines.append(f"| {title} | {url} | {cred} | {topics} |")
        lines.append("")
        refs_block = "\n".join(lines)
    else:
        # 回退默认
        refs_block = """

---

## 参考来源

| 来源 | 链接 | 说明 |
|------|------|------|
| OpenClaw 官方文档 | https://docs.openclaw.com | 官方安装与配置手册 |
| OpenClaw GitHub | https://github.com/anthropics/openclaw | 源码与 Issue 追踪 |
| ClawHub 平台 | https://hub.openclaw.com | Skills 市场与文档 |
"""

    # 在"本章小结"前或文件末尾插入
    summary_match = re.search(r"\n##\s+.*本章小结", text)
    if summary_match:
        pos = summary_match.start()
        text = text[:pos] + refs_block + text[pos:]
    else:
        # 在章尾导航前或文件末尾
        nav_match = re.search(r"\n---\s*\n+<div align=\"center\">\s*\n+\[.*📑 返回目录|\n>\s*\*\*📖\s*章节导航", text)
        if nav_match:
            pos = nav_match.start()
            text = text[:pos] + refs_block + text[pos:]
        else:
            text = text.rstrip() + refs_block

    return text, ["added References section (from collected sources)" if collected_refs else "added References section (default)"]


def add_faq_section(text: str, chapter_title: str) -> tuple:
    """添加 FAQ 段落（如不存在）。根据章节内容生成定制化 FAQ。"""
    if re.search(r"##\s+.*(?:常见问题|FAQ)", text, re.IGNORECASE):
        return text, []

    # 从章节内容中提取 H2 标题，生成有针对性的 FAQ
    h2s = re.findall(r"^##\s+(.+)$", text, re.MULTILINE)
    topic_names = [h.strip() for h in h2s[:5] if "目录" not in h and "小结" not in h
                   and "FAQ" not in h and "参考" not in h]

    # 检测章节中是否有命令行内容
    has_commands = bool(re.search(r"```(?:bash|shell|sh)", text))
    has_config = bool(re.search(r"```(?:yaml|json|toml)", text))

    q_items = []

    # 第一个 FAQ：基于章节主题
    if topic_names:
        main_topic = topic_names[0]
        q_items.append(
            f"### Q: {main_topic}的核心要点是什么？\n\n"
            f"**A:** 本章围绕「{chapter_title}」展开，重点涵盖了"
            f" {', '.join(topic_names[:3])} 等内容。建议结合实际操作逐步理解。"
        )

    # 第二个 FAQ：基于内容类型
    if has_commands:
        q_items.append(
            "### Q: 执行命令时遇到权限错误怎么办？\n\n"
            "**A:** 请确认当前用户是否有足够权限。可尝试 `sudo` 或检查文件/目录权限。"
            "如果使用 Docker 环境，确保容器内用户配置正确。"
        )
    elif has_config:
        q_items.append(
            "### Q: 配置文件修改后不生效怎么办？\n\n"
            "**A:** 请检查以下几点：\n"
            "1. 配置文件路径是否正确\n"
            "2. YAML/JSON 语法是否有效（注意缩进和引号）\n"
            "3. 是否需要重启服务才能加载新配置"
        )

    # 第三个 FAQ：通用但有用
    q_items.append(
        "### Q: 本章内容如何与其他章节衔接？\n\n"
        "**A:** 建议按照教程顺序阅读。本章内容会在后续章节中被引用和扩展。"
        "遇到困难时可参考 [目录](README.md) 快速定位相关章节。"
    )

    faq_block = "\n\n## 常见问题 (FAQ)\n\n" + "\n\n".join(q_items) + "\n"

    # 在"本章小结"前插入
    summary_match = re.search(r"\n##\s+.*本章小结", text)
    refs_match = re.search(r"\n##\s+.*参考来源", text)
    insert_before = summary_match or refs_match
    if insert_before:
        pos = insert_before.start()
        text = text[:pos] + faq_block + text[pos:]
    else:
        text = text.rstrip() + faq_block

    return text, ["added FAQ section"]


def add_summary_section(text: str, chapter_title: str) -> tuple:
    """添加本章小结（如不存在）。从章节内容提取要点生成有针对性的小结。"""
    if re.search(r"##\s+.*(?:本章小结|Summary)", text, re.IGNORECASE):
        return text, []

    # 提取 H2 标题作为要点
    h2s = re.findall(r"^##\s+(.+)$", text, re.MULTILINE)
    key_topics = [h.strip() for h in h2s
                  if not re.search(r"目录|FAQ|常见问题|参考来源|小结", h)]

    # 检测章节中的关键技术术语
    tech_terms = set()
    for term in re.findall(r"`([^`]{2,30})`", text):
        if re.search(r"openclaw|skill|agent|gateway|mcp|hook|cron|memory", term, re.I):
            tech_terms.add(term)

    points = []
    for topic in key_topics[:4]:
        points.append(f"- ✅ {topic}")
    if tech_terms:
        terms_str = "、".join(f"`{t}`" for t in sorted(tech_terms)[:5])
        points.append(f"- 🔧 涉及核心概念：{terms_str}")

    if not points:
        points = [
            f"- ✅ 理解了「{chapter_title}」的核心内容",
            "- ✅ 掌握了关键操作步骤",
            "- ✅ 了解了最佳实践和注意事项",
        ]

    summary_block = (
        "\n\n---\n\n## 本章小结\n\n"
        f"本章系统讲解了 **{chapter_title}** 的核心内容。关键要点：\n\n"
        + "\n".join(points)
        + "\n\n> [!TIP]\n> 建议在实际环境中动手练习本章内容，加深理解。\n"
    )

    # 在参考来源前或文件末尾
    refs_match = re.search(r"\n##\s+.*参考来源", text)
    nav_match = re.search(r"\n---\s*\n+<div align=\"center\">\s*\n+\[.*📑 返回目录|\n>\s*\*\*📖\s*章节导航", text)
    insert_before = refs_match or nav_match
    if insert_before:
        pos = insert_before.start()
        text = text[:pos] + summary_block + text[pos:]
    else:
        text = text.rstrip() + summary_block

    return text, ["added Summary section"]


def fix_cjk_spacing(text: str) -> tuple:
    """修复中英文间缺少空格。

    跳过行内代码 (`code`) 和代码块 (```) 中的内容，
    避免破坏 Markdown 格式。
    """
    lines = text.split("\n")
    new_lines = []
    changes_count = 0
    in_code_block = False

    for line in lines:
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            new_lines.append(line)
            continue
        if in_code_block:
            new_lines.append(line)
            continue

        # 保护行内代码: 先提取 `...` 并替换为占位符
        inline_codes = []
        def _preserve_inline(m):
            inline_codes.append(m.group(0))
            return f"\x00ICODE{len(inline_codes) - 1}\x00"

        protected = re.sub(r'`[^`]+`', _preserve_inline, line)

        # 中文后紧跟英文/数字
        fixed = re.sub(r'([\u4e00-\u9fff])([A-Za-z0-9])', r'\1 \2', protected)
        # 英文/数字后紧跟中文
        fixed = re.sub(r'([A-Za-z0-9])([\u4e00-\u9fff])', r'\1 \2', fixed)

        # 恢复行内代码
        for i, code in enumerate(inline_codes):
            fixed = fixed.replace(f"\x00ICODE{i}\x00", code)

        if fixed != line:
            changes_count += 1
        new_lines.append(fixed)

    result = "\n".join(new_lines)
    if changes_count > 0:
        return result, [f"fixed CJK-Latin spacing in {changes_count} lines"]
    return text, []


def fix_dense_blocks(text: str) -> tuple:
    """修复连续密排。"""
    lines = text.split("\n")
    new_lines = []
    consecutive = 0
    changes = 0

    for line in lines:
        if line.strip():
            consecutive += 1
            if consecutive > 20 and not re.match(r"^```|^\||^>|^-|^\d+\.", line):
                # 在非代码块/表格/列表的密排段落中插空行
                new_lines.append("")
                consecutive = 0
                changes += 1
        else:
            consecutive = 0
        new_lines.append(line)

    if changes > 0:
        return "\n".join(new_lines), [f"inserted {changes} blank lines in dense blocks"]
    return text, []


def deduplicate_sections(text: str) -> tuple:
    """去除重复的 TOC 和参考来源段落。

    - 保留 '📑 本章目录'，删除单独的 '📖 目录' 段落
    - 保留第一个参考来源段落，删除后续重复的
    """
    changes = []

    # 去重 TOC – 保留 '📑 本章目录'，删除其他冗余目录段
    if '## 📑 本章目录' in text:
        for dup_label in ['📖 目录', '📑 目录']:
            dup_heading = f'## {dup_label}'
            if dup_heading in text:
                pattern = r'\n' + re.escape(dup_heading) + r'\n.*?(?=\n## )'
                if re.search(pattern, text, re.DOTALL):
                    text = re.sub(pattern, '', text, flags=re.DOTALL)
                    changes.append(f"removed duplicate '{dup_label}' section")

    # 去重参考来源
    ref_sections = list(re.finditer(r'\n## (?:参考来源|参考链接|参考资料)\b', text))
    if len(ref_sections) > 1:
        for m in reversed(ref_sections[1:]):
            remaining = text[m.end():]
            next_h2 = re.search(r'\n## ', remaining)
            sec_end = m.end() + next_h2.start() if next_h2 else len(text)
            text = text[:m.start()] + text[sec_end:]
        changes.append(f"removed {len(ref_sections)-1} duplicate reference sections")

    return (text, changes) if changes else (text, [])


# ── 核心精炼逻辑 ────────────────────────────────────

def refine_chapter(chapter_analysis: ChapterAnalysis, nav_info: dict,
                   refs_data: dict = None) -> RefineResult:
    """根据分析结果精炼单个章节。

    Args:
        chapter_analysis: 分析报告中的章节数据
        nav_info: 导航信息
        refs_data: reference_collector 输出 (按章节号索引的 dict)
    """
    ch_num = chapter_analysis.get("chapter", 0)
    ch_file = chapter_analysis.get("file", "")
    ch_title = chapter_analysis.get("title", "")
    filepath = os.path.join(PROJECT_DIR, ch_file)

    if not os.path.exists(filepath):
        return {"chapter": ch_num, "status": "file_not_found", "file": ch_file}

    log.info(f"精炼章节 [{ch_num:02d}]: {ch_title}")

    # 读取原始内容
    text = _read_file(filepath)
    original_wc = word_count(text)
    all_changes = []

    # 备份
    if not DRY_RUN:
        bak_path = filepath + ".bak"
        if not os.path.exists(bak_path):
            shutil.copy2(filepath, bak_path)

    # ── 按优先级执行优化操作 ──

    # 0. [P0] 修复损坏的代码块关闭标记
    text, changes = fix_broken_code_closings(text)
    if changes:
        all_changes.extend(changes)

    # 0b. [P1] 清洗爬虫/搜索残留
    text, changes = clean_raw_scrape_artifacts(text)
    if changes:
        all_changes.extend(changes)

    # 0c. [P1] 去除重复的目录/参考章节
    text, changes = deduplicate_sections(text)
    if changes:
        all_changes.extend(changes)

    # 1. 修复标题层级
    text, changes = fix_heading_jumps(text)
    if changes:
        all_changes.extend(changes)

    # 2. 添加章节导航
    text, changes = add_chapter_navigation(text, ch_num, nav_info)
    if changes:
        all_changes.extend(changes)

    # 2b. [P2] 章节头部视觉增强（徽章）
    # 基于章节编号估算难度分数，避免使用固定默认值 50
    _ch_difficulty_score = (
        20 if ch_num <= 5 else
        50 if ch_num <= 10 else
        70 if ch_num <= 15 else
        85
    )
    text, changes = enhance_chapter_header(text, ch_num, ch_title,
                                           word_count(text),
                                           readability_score=_ch_difficulty_score)
    if changes:
        all_changes.extend(changes)

    # 3. 添加本章目录
    text, changes = add_toc(text)
    if changes:
        all_changes.extend(changes)

    # 4. 修复代码块标注
    text, changes = add_code_language_labels(text)
    if changes:
        all_changes.extend(changes)

    # 5. 添加 FAQ
    improvements = chapter_analysis.get("improvements", [])
    need_faq = any(i.get("target") == "FAQ" for i in improvements)
    if need_faq or not re.search(r"##\s*常见问题|##\s*FAQ", text, re.IGNORECASE):
        text, changes = add_faq_section(text, ch_title)
        if changes:
            all_changes.extend(changes)

    # 6. 添加本章小结
    text, changes = add_summary_section(text, ch_title)
    if changes:
        all_changes.extend(changes)

    # 7. 添加参考来源 (使用 reference_collector 收集的数据)
    ch_refs = refs_data.get(ch_num) if refs_data else None
    text, changes = add_references_section(text, ch_num, collected_refs=ch_refs)
    if changes:
        all_changes.extend(changes)

    # 8. 中英文间距
    text, changes = fix_cjk_spacing(text)
    if changes:
        all_changes.extend(changes)

    # 8b. [P1] GitHub Alert 语法统一
    text, changes = convert_to_github_alerts(text)
    if changes:
        all_changes.extend(changes)

    # 9. 密排修复
    text, changes = fix_dense_blocks(text)
    if changes:
        all_changes.extend(changes)

    # ── 写入 ──
    new_wc = word_count(text)
    if all_changes and not DRY_RUN:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(text)
        log.info(f"  已更新: {ch_file} ({len(all_changes)} 项修改, "
                  f"{original_wc}→{new_wc} 字)")
    elif DRY_RUN:
        log.info(f"  [DRY_RUN] 跳过写入: {ch_file}")
    else:
        log.info(f"  无需修改: {ch_file}")

    return {
        "chapter": ch_num,
        "file": ch_file,
        "status": "refined" if all_changes else "no_change",
        "changes_applied": all_changes,
        "words_before": original_wc,
        "words_after": new_wc,
        "change_count": len(all_changes),
    }


def refine_all(analysis_report: dict = None, max_chapters: int = None,
               references_report: dict = None) -> dict:
    """根据分析报告精炼所有需要优化的章节。

    Args:
        analysis_report: 质量分析报告
        max_chapters: 最大优化章节数
        references_report: reference_collector 的输出 (可选)
    """
    if analysis_report is None:
        analysis_path = os.path.join(OUTPUT_DIR, "analysis-report.json")
        analysis_report = load_json(analysis_path)
        if not analysis_report:
            log.error(f"分析报告不存在: {analysis_path}")
            return {"error": "analysis-report.json not found"}

    # 加载参考来源数据 (如果 pipeline 未传入则尝试从文件加载)
    refs_data = {}
    if references_report is None:
        refs_path = os.path.join(OUTPUT_DIR, "references.json")
        references_report = load_json(refs_path, {})
    if references_report:
        # 按章节号索引
        for ch_ref in references_report.get("chapters", []):
            ch_num = ch_ref.get("chapter", 0)
            if ch_num > 0:
                refs_data[ch_num] = ch_ref
        if refs_data:
            log.info(f"已加载 {len(refs_data)} 个章节的参考来源数据")

    chapters = analysis_report.get("chapters", [])
    if max_chapters:
        chapters = chapters[:max_chapters]

    nav_info = _get_chapter_nav_info(PROJECT_DIR)
    log.info(f"开始精炼 {len(chapters)} 个章节...")

    results = []
    refined_count = 0

    for ch in chapters:
        try:
            result = refine_chapter(ch, nav_info, refs_data=refs_data)
            results.append(result)
            if result.get("status") == "refined":
                refined_count += 1
        except Exception as e:
            log.error(f"  精炼失败 [{ch.get('chapter', '?')}]: {e}")
            results.append({
                "chapter": ch.get("chapter", 0),
                "status": "error",
                "error": str(e),
            })

    report = {
        "refine_time": datetime.now(tz=timezone.utc).isoformat(),
        "total_processed": len(results),
        "refined": refined_count,
        "no_change": sum(1 for r in results if r.get("status") == "no_change"),
        "errors": sum(1 for r in results if r.get("status") == "error"),
        "dry_run": DRY_RUN,
        "results": results,
        "total_changes": sum(r.get("change_count", 0) for r in results),
    }

    return report


def run():
    """主入口: 精炼并保存结果。"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    report = refine_all()

    if "error" in report:
        log.error(report["error"])
        return report

    out_path = os.path.join(OUTPUT_DIR, "refine-result.json")
    save_json(out_path, report)
    log.info(f"精炼结果已保存: {out_path}")
    log.info(f"  精炼: {report['refined']}/{report['total_processed']}")
    log.info(f"  总修改: {report['total_changes']}")

    return report


if __name__ == "__main__":
    run()
