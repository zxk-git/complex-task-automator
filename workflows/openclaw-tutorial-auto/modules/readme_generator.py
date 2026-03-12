#!/usr/bin/env python3
"""
readme_generator.py — README 自动生成器
=========================================
在所有教程文档优化完成后，根据当前教程结构自动生成或更新 README.md。

功能:
  - 扫描所有已完成的章节文件
  - 生成教程目录导航 (带链接和摘要)
  - 包含项目介绍、快速开始、示例入口
  - 适合作为 GitHub 项目首页文档

属于优化流水线的 update_readme 阶段。
"""

from datetime import datetime, timezone
import os
import re
import shutil

from modules.compat import (
    setup_logger, cfg, save_json, read_file_safe, word_count,
    PROJECT_DIR, OUTPUT_DIR, DRY_RUN,
)

log = setup_logger("readme_generator")


# ── 从章节文件提取元数据 ────────────────────────────

def _extract_chapter_meta(filepath: str) -> dict:
    """从章节文件中提取标题、摘要、难度等信息。"""
    text = read_file_safe(filepath)
    if not text:
        return {}

    fname = os.path.basename(filepath)
    lines = text.split("\n")

    # 章节编号
    num_match = re.match(r"(\d+)", fname)
    chapter_num = int(num_match.group(1)) if num_match else 0

    # H1 标题
    h1_title = ""
    for line in lines:
        if line.startswith("# ") and not line.startswith("## "):
            h1_title = line.lstrip("# ").strip()
            break

    # 摘要 (H1 标题后的第一段非空文本，忽略徽章行)
    summary = ""
    found_h1 = False
    for line in lines:
        if line.startswith("# ") and not line.startswith("## "):
            found_h1 = True
            continue
        if found_h1:
            stripped = line.strip()
            # 跳过徽章行、空行、导航行
            if not stripped:
                continue
            if stripped.startswith("!["):
                continue
            if stripped.startswith(">"):
                # 可能是前置要求行，提取
                continue
            if stripped.startswith("<div"):
                continue
            if stripped.startswith("[←") or stripped.startswith("[📑"):
                continue
            if stripped.startswith("## "):
                break
            summary = stripped[:150]
            if len(stripped) > 150:
                summary += "..."
            break

    # 字数
    wc = word_count(text)

    # 难度 (从徽章提取)
    difficulty = ""
    diff_match = re.search(r"难度-([^)]+)-", text)
    if diff_match:
        difficulty = diff_match.group(1).replace("_", " ")

    # 阅读时间
    time_match = re.search(r"阅读时间-(\d+)_分钟", text)
    reading_time = int(time_match.group(1)) if time_match else max(5, wc // 250)

    # H2 小节列表
    h2_sections = re.findall(r"^##\s+(.+)$", text, re.MULTILINE)

    return {
        "file": fname,
        "number": chapter_num,
        "title": h1_title or fname,
        "summary": summary,
        "word_count": wc,
        "difficulty": difficulty,
        "reading_time": reading_time,
        "h2_count": len(h2_sections),
        "h2_sections": h2_sections[:8],  # 最多取 8 个
    }


# ── README 内容生成 ─────────────────────────────────

def _generate_readme_content(
    project_name: str,
    chapters: list,
    scan_report: dict = None,
    discover_report: dict = None,
) -> str:
    """生成 README.md 的完整 Markdown 内容。"""

    total_words = sum(ch.get("word_count", 0) for ch in chapters)
    total_time = sum(ch.get("reading_time", 10) for ch in chapters)
    total_chapters = len(chapters)

    # 从 scan report 提取全局统计
    avg_score = 0
    if scan_report:
        avg_score = scan_report.get("summary", {}).get("avg_score", 0)

    lines = []

    # ── 标题区域 ──
    lines.extend([
        f'<div align="center">',
        "",
        f"# 📚 {project_name}",
        "",
        f"**一套完整的开源教程 — 从入门到精通**",
        "",
        f"![chapters](https://img.shields.io/badge/章节-{total_chapters}-blue)"
        f" ![words](https://img.shields.io/badge/总字数-{total_words:,}-green)"
        f" ![time](https://img.shields.io/badge/总阅读时间-{total_time}_分钟-orange)",
        "",
        "</div>",
        "",
        "---",
        "",
    ])

    # ── 项目介绍 ──
    lines.extend([
        "## 📖 项目介绍",
        "",
        f"本教程共 **{total_chapters} 章**，涵盖从基础入门到高级实践的完整学习路径。"
        f"总计约 **{total_words:,} 字**，预计总阅读时间 **{total_time} 分钟**。",
        "",
        "教程特色：",
        "",
        "- ✅ **循序渐进** — 从零基础到高级用法，章节间逻辑连贯",
        "- ✅ **实战导向** — 大量可运行的命令和代码示例",
        "- ✅ **结构规范** — 每章包含目录、FAQ、小结、参考来源",
        "- ✅ **持续更新** — 自动化质量检测与优化流水线保障质量",
        "",
        "---",
        "",
    ])

    # ── 快速开始 ──
    lines.extend([
        "## 🚀 快速开始",
        "",
        "### 阅读教程",
        "",
        "直接从第 1 章开始阅读：",
        "",
    ])
    if chapters:
        first_ch = chapters[0]
        lines.append(f"👉 **[{first_ch['title']}]({first_ch['file']})**")
    lines.extend([
        "",
        "### 克隆仓库",
        "",
        "```bash",
        f"git clone <仓库地址>",
        f"cd {project_name}",
        "```",
        "",
        "---",
        "",
    ])

    # ── 教程目录导航 ──
    lines.extend([
        "## 📑 教程目录",
        "",
        "| 章节 | 标题 | 难度 | 阅读时间 | 字数 |",
        "|:---:|------|:---:|:---:|---:|",
    ])

    for ch in chapters:
        num = ch.get("number", 0)
        title = ch.get("title", ch.get("file", ""))
        fname = ch.get("file", "")
        difficulty = ch.get("difficulty", "")
        reading_time = ch.get("reading_time", "?")
        wc = ch.get("word_count", 0)

        # 难度徽章颜色
        if "入门" in difficulty:
            diff_display = "🟢 入门"
        elif "基础" in difficulty:
            diff_display = "🟡 基础"
        elif "进阶" in difficulty:
            diff_display = "🟠 进阶"
        elif "高级" in difficulty:
            diff_display = "🔴 高级"
        elif "专家" in difficulty:
            diff_display = "🔴 专家"
        else:
            diff_display = difficulty or "—"

        lines.append(
            f"| {num:02d} | [{title}]({fname}) | {diff_display} | ~{reading_time}min | {wc:,} |"
        )

    lines.extend([
        "",
        "---",
        "",
    ])

    # ── 学习路径推荐 ──
    if total_chapters >= 5:
        lines.extend([
            "## 🗺️ 推荐学习路径",
            "",
            "### 🌱 初学者路径",
            "",
        ])
        beginner = [ch for ch in chapters[:5]]
        for ch in beginner:
            lines.append(f"1. [{ch['title']}]({ch['file']})")
        lines.extend([
            "",
            "### 🚀 进阶路径",
            "",
        ])
        advanced = [ch for ch in chapters[5:min(12, total_chapters)]]
        for ch in advanced:
            lines.append(f"1. [{ch['title']}]({ch['file']})")
        if total_chapters > 12:
            lines.extend([
                "",
                "### 🏆 高级路径",
                "",
            ])
            expert = [ch for ch in chapters[12:]]
            for ch in expert:
                lines.append(f"1. [{ch['title']}]({ch['file']})")
        lines.extend([
            "",
            "---",
            "",
        ])

    # ── 质量统计 ──
    if avg_score > 0:
        lines.extend([
            "## 📊 质量统计",
            "",
            f"| 指标 | 值 |",
            f"|------|-----|",
            f"| 平均质量分 | {avg_score:.1f}/100 |",
            f"| 总章节数 | {total_chapters} |",
            f"| 总字数 | {total_words:,} |",
            f"| 预计总阅读时间 | {total_time} 分钟 |",
            "",
            "> 质量分由自动化流水线检测，涵盖内容深度、结构完整性、代码质量、教学价值、参考来源、可读性六个维度。",
            "",
            "---",
            "",
        ])

    # ── 贡献指南入口 ──
    lines.extend([
        "## 🤝 贡献",
        "",
        "欢迎提交 Issue 和 Pull Request 来改进教程内容。",
        "",
        "---",
        "",
    ])

    # ── 页脚 ──
    lines.extend([
        '<div align="center">',
        "",
        f"*自动生成 by OpenClaw Tutorial Auto Pipeline v5.1 — "
        f"{datetime.now(tz=timezone.utc).strftime('%Y-%m-%d')}*",
        "",
        "</div>",
        "",
    ])

    return "\n".join(lines)


# ── 主入口 ──────────────────────────────────────────

def generate_readme(
    project_dir: str = None,
    scan_report: dict = None,
    discover_report: dict = None,
    refine_report: dict = None,
    analysis_report: dict = None,
    dry_run: bool = None,
) -> dict:
    """生成或更新 README.md。

    Args:
        project_dir: 教程项目目录
        scan_report: 扫描报告 (包含章节元数据)
        discover_report: 发现报告 (包含文件列表)
        refine_report: 精炼报告
        analysis_report: 分析报告
        dry_run: 是否干跑模式
    Returns:
        dict: 生成结果报告
    """
    project_dir = project_dir or PROJECT_DIR
    if dry_run is None:
        dry_run = DRY_RUN

    log.info(f"生成 README.md: {project_dir}")

    # 收集所有章节元数据
    chapters_meta = []

    # 从 scan_report 获取已扫描章节
    if scan_report and scan_report.get("chapters"):
        for ch in scan_report["chapters"]:
            if "error" in ch:
                continue
            chapters_meta.append({
                "file": ch["file"],
                "number": ch.get("number", 0),
                "title": ch.get("title", ch["file"]),
                "word_count": ch.get("word_count", 0),
                "quality_score": ch.get("quality_score", 0),
                "difficulty": "",
                "reading_time": max(5, ch.get("word_count", 0) // 250),
                "h2_count": ch.get("structure", {}).get("h2", 0),
            })
    else:
        # 如果没有 scan_report，直接从文件系统扫描
        md_files = sorted(
            f for f in os.listdir(project_dir)
            if re.match(r"\d+.*\.md$", f) and not f.endswith(".bak")
        )
        for fname in md_files:
            filepath = os.path.join(project_dir, fname)
            try:
                meta = _extract_chapter_meta(filepath)
                if meta:
                    chapters_meta.append(meta)
            except Exception as e:
                log.warning(f"  提取 {fname} 元数据失败: {e}")

    # 按章节编号排序
    chapters_meta.sort(key=lambda x: x.get("number", 0))

    if not chapters_meta:
        log.warning("  未发现任何章节文件，跳过 README 生成")
        return {"status": "skipped", "reason": "no chapters found", "toc_entries": 0}

    # 补充难度信息 (从文件中提取)
    for ch in chapters_meta:
        if not ch.get("difficulty"):
            filepath = os.path.join(project_dir, ch["file"])
            if os.path.exists(filepath):
                meta = _extract_chapter_meta(filepath)
                ch["difficulty"] = meta.get("difficulty", "")
                ch["summary"] = meta.get("summary", "")

    # 推断项目名称
    project_name = os.path.basename(project_dir)
    # 尝试从现有 README 提取项目名
    existing_readme = os.path.join(project_dir, "README.md")
    if os.path.exists(existing_readme):
        old_text = read_file_safe(existing_readme)
        h1_match = re.search(r"^#\s+(.+)$", old_text, re.MULTILINE)
        if h1_match:
            raw_name = h1_match.group(1).strip()
            # 去除 emoji 前缀
            project_name = re.sub(r"^[^\w\u4e00-\u9fff]+", "", raw_name).strip() or project_name

    # 生成内容
    readme_content = _generate_readme_content(
        project_name=project_name,
        chapters=chapters_meta,
        scan_report=scan_report,
        discover_report=discover_report,
    )

    readme_path = os.path.join(project_dir, "README.md")

    # 备份旧 README
    if os.path.exists(readme_path):
        backup_path = os.path.join(project_dir, "README.md.bak")
        if not dry_run:
            shutil.copy2(readme_path, backup_path)
            log.info(f"  已备份旧 README: {backup_path}")

    # 写入新 README
    if dry_run:
        log.info(f"  [DRY_RUN] 将生成 README.md ({len(readme_content)} 字符, {len(chapters_meta)} 章节)")
        status = "dry_run"
    else:
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(readme_content)
        log.info(f"  已更新 README.md ({len(readme_content)} 字符)")
        status = "updated"

    return {
        "status": status,
        "readme_path": readme_path,
        "content_length": len(readme_content),
        "toc_entries": len(chapters_meta),
        "project_name": project_name,
        "chapters": [
            {"number": ch["number"], "title": ch["title"], "file": ch["file"]}
            for ch in chapters_meta
        ],
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
    }


def run():
    """主入口: 独立生成 README。"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    report = generate_readme()
    out_path = os.path.join(OUTPUT_DIR, "readme-update-report.json")
    save_json(out_path, report)
    log.info(f"README 生成报告: {out_path}")
    return report


if __name__ == "__main__":
    run()
