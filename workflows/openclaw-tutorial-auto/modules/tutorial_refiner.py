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

_PROMPTS = os.path.join(os.path.dirname(__file__), "..", "prompts")
from modules.compat import setup_logger, cfg, load_json, save_json, word_count

def _read_file(filepath: str) -> str:
    """直接读取文件内容。"""
    with open(filepath, encoding="utf-8") as f:
        return f.read()

log = setup_logger("tutorial_refiner")

PROJECT_DIR = cfg("project_dir", os.environ.get(
    "PROJECT_DIR", "/root/.openclaw/workspace/zxk-private/openclaw-tutorial-auto"))
OUTPUT_DIR = cfg("output_dir", os.environ.get(
    "OUTPUT_DIR", "/tmp/openclaw-tutorial-auto-reports"))
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"


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

def add_chapter_navigation(text: str, chapter_num: int, nav_info: dict) -> tuple:
    """添加章首和章尾导航。返回 (修改后文本, 变更描述)。"""
    info = nav_info.get(chapter_num)
    if not info:
        return text, None

    changes = []
    prev_link = f"[← 上一章：{info['prev_title']}]({info['prev_file']})" if info["prev_file"] else ""
    next_link = f"[下一章：{info['next_title']} →]({info['next_file']})" if info["next_file"] else ""
    nav_bar = f"> **📖 OpenClaw 中文实战教程** | {prev_link} | [目录](README.md) | {next_link}"

    # 章首导航
    if not re.search(r"\[←\s*上一章|\[目录\]\(README\.md\)", text[:500]):
        text = nav_bar + "\n\n---\n\n" + text
        changes.append("added header navigation")

    # 章尾导航
    if not re.search(r"📖\s*章节导航", text[-500:]):
        footer_nav = f"\n\n---\n\n> **📖 章节导航** | {prev_link} | [目录](README.md) | {next_link}\n"
        text = text.rstrip() + footer_nav
        changes.append("added footer navigation")

    return text, changes if changes else None


def add_toc(text: str) -> tuple:
    """在 H1 标题后添加本章目录。返回 (修改后文本, 变更描述)。"""
    if re.search(r"##\s*📑?\s*本章目录|##\s*目录", text):
        return text, None

    # 提取 H2 标题
    h2s = re.findall(r"^##\s+(.+)$", text, re.MULTILINE)
    if not h2s:
        return text, None

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

    return text, None


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
    return text, None


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
    return text, None


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
    if re.search(r"##\s*参考来源|##\s*References", text, re.IGNORECASE):
        return text, None

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
    summary_match = re.search(r"\n##\s*本章小结", text)
    if summary_match:
        pos = summary_match.start()
        text = text[:pos] + refs_block + text[pos:]
    else:
        # 在章尾导航前或文件末尾
        nav_match = re.search(r"\n>\s*\*\*📖\s*章节导航", text)
        if nav_match:
            pos = nav_match.start()
            text = text[:pos] + refs_block + text[pos:]
        else:
            text = text.rstrip() + refs_block

    return text, ["added References section (from collected sources)" if collected_refs else "added References section (default)"]


def add_faq_section(text: str, chapter_title: str) -> tuple:
    """添加 FAQ 段落（如不存在）。"""
    if re.search(r"##\s*常见问题|##\s*FAQ", text, re.IGNORECASE):
        return text, None

    faq_block = f"""

## 常见问题 (FAQ)

### Q: 本章内容是否需要前置知识？

**A:** 建议先完成前面的章节，确保理解 OpenClaw 的基础概念和安装方式。

### Q: 遇到命令执行错误怎么办？

**A:** 请检查 OpenClaw 是否正确安装，运行 `openclaw --version` 确认版本。如问题持续，请参考故障排查章节或提交 GitHub Issue。

### Q: 如何获取更多帮助？

**A:** 可以通过以下渠道获取帮助：
- OpenClaw GitHub Issues
- ClawHub 社区讨论
- 官方文档 FAQ 页面
"""

    # 在"本章小结"前插入
    summary_match = re.search(r"\n##\s*本章小结", text)
    refs_match = re.search(r"\n##\s*参考来源", text)
    insert_before = summary_match or refs_match
    if insert_before:
        pos = insert_before.start()
        text = text[:pos] + faq_block + text[pos:]
    else:
        text = text.rstrip() + faq_block

    return text, ["added FAQ section"]


def add_summary_section(text: str, chapter_title: str) -> tuple:
    """添加本章小结（如不存在）。"""
    if re.search(r"##\s*本章小结|##\s*Summary", text, re.IGNORECASE):
        return text, None

    summary_block = f"""

---

## 本章小结

本章介绍了 {chapter_title} 的核心内容。关键要点：

- ✅ 理解了相关基本概念
- ✅ 掌握了核心操作步骤
- ✅ 了解了常见问题及解决方案

> **提示**：建议在实际环境中动手练习本章内容，加深理解。
"""

    # 在参考来源前或文件末尾
    refs_match = re.search(r"\n##\s*参考来源", text)
    nav_match = re.search(r"\n>\s*\*\*📖\s*章节导航", text)
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
    return text, None


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
    return text, None


# ── 核心精炼逻辑 ────────────────────────────────────

def refine_chapter(chapter_analysis: dict, nav_info: dict,
                   refs_data: dict = None) -> dict:
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

    # 1. 修复标题层级
    text, changes = fix_heading_jumps(text)
    if changes:
        all_changes.extend(changes)

    # 2. 添加章节导航
    text, changes = add_chapter_navigation(text, ch_num, nav_info)
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
