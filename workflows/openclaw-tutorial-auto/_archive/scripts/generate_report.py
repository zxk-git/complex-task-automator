#!/usr/bin/env python3
"""
generate_report.py — 综合报告生成
汇总所有检查结果 (env / quality / progress / dependency)，生成 Markdown 报告。
"""
from datetime import datetime
from pathlib import Path
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from utils import (
    get_output_dir, get_project_dir, get_encoding,
    load_json, save_json, progress_bar, setup_logger,
)

log = setup_logger("report")

OUTPUT_DIR = get_output_dir()
PROJECT_DIR = get_project_dir()


def severity_badge(level):
    """severity_badge 的功能描述。

        Args:
            level: ...
        """
    return {"pass": "✅", "warn": "⚠️", "fail": "❌"}.get(level, "ℹ️")


def run():
    """run 的功能描述。
        """
    env_data = load_json(os.path.join(OUTPUT_DIR, "01-env-check.json"))
    quality_data = load_json(os.path.join(OUTPUT_DIR, "02-quality-check.json"))
    progress_data = load_json(os.path.join(OUTPUT_DIR, "03-progress-analysis.json"))
    dep_data = load_json(os.path.join(OUTPUT_DIR, "04-dependency-check.json"))

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = []
    lines.append(f"# 📋 OpenClaw Tutorial Auto — 项目自动化报告")
    lines.append(f"")
    lines.append(f"> 生成时间: {now}")
    lines.append(f"> 项目路径: `{PROJECT_DIR}`")
    lines.append(f"")

    # ===== 总览 =====
    lines.append("---")
    lines.append("## 📊 总览")
    lines.append("")

    # 进度
    if progress_data:
        p = progress_data.get("progress", {})
        pct = p.get("percentage", 0)
        lines.append(f"### 进度")
        lines.append(f"- 完成: **{p.get('completed', 0)}** / {p.get('total', 0)} 章")
        lines.append(f"- 进度: {progress_bar(pct)}")
        lines.append(f"- 待完成: {p.get('missing', 0)} 章")
        lines.append("")

    # 质量 —— 兼容 check_quality.py v2 新格式
    if quality_data:
        s = quality_data.get("summary", {})
        avg_score = s.get("average_score", 0)
        level = "pass" if s.get("all_pass") else ("warn" if avg_score >= 70 else "fail")
        lines.append(f"### 质量")
        lines.append(f"- 平均质量分: **{avg_score}** / 100  {severity_badge(level)}")
        lines.append(f"- 等级: {s.get('average_grade', 'N/A')}")
        lines.append(f"- 总字数: {s.get('total_words', 0):,}")
        lines.append(f"- 问题数: {s.get('total_issues', 0)}")
        lines.append("")

    # ===== 环境检查 =====
    lines.append("---")
    lines.append("## 🔧 环境检查")
    lines.append("")
    if env_data:
        env = env_data.get("checks", {}).get("environment", {})
        lines.append("| 工具 | 状态 |")
        lines.append("|------|------|")
        for tool, ok in env.items():
            lines.append(f"| {tool} | {severity_badge('pass' if ok else 'warn')} {'可用' if ok else '未安装'} |")
        lines.append("")

        if env_data.get("errors"):
            lines.append("**错误:**")
            for e in env_data["errors"]:
                lines.append(f"- ❌ {e}")
            lines.append("")

        if env_data.get("warnings"):
            lines.append("**警告:**")
            for w in env_data["warnings"]:
                lines.append(f"- ⚠️ {w}")
            lines.append("")
    else:
        lines.append("*环境检查数据不可用*")
        lines.append("")

    # ===== 章节质量详情 (兼容 v1 + v2) =====
    lines.append("---")
    lines.append("## 📝 章节质量分析")
    lines.append("")
    if quality_data and quality_data.get("chapters"):
        lines.append("| 章节 | 字数 | 质量分 | 等级 | 状态 |")
        lines.append("|------|------|--------|------|------|")
        for ch in quality_data["chapters"]:
            name = ch.get("file", "?")[:30]
            # 兼容 v2 格式
            words = ch.get("stats", {}).get("word_count", ch.get("word_count", 0))
            score = ch.get("quality", {}).get("score", ch.get("score", 0))
            grade = ch.get("quality", {}).get("grade", "?")
            passed = ch.get("quality", {}).get("pass", score >= 70)
            level = "pass" if passed else ("warn" if score >= 60 else "fail")
            lines.append(f"| {name} | {words} | {score}/100 | {grade} | {severity_badge(level)} |")
        lines.append("")

        # 详细问题
        all_issues = []
        for ch in quality_data["chapters"]:
            issues = ch.get("quality", {}).get("issues", ch.get("issues", []))
            for issue in issues:
                all_issues.append(f"- **{ch.get('file', '?')}**: {issue}")
        if all_issues:
            lines.append("### 质量问题")
            lines.append("")
            for issue in all_issues[:30]:
                lines.append(issue)
            lines.append("")
    else:
        lines.append("*暂无已完成章节可分析*")
        lines.append("")

    # ===== 进度详情 =====
    lines.append("---")
    lines.append("## 📈 进度详情")
    lines.append("")
    if progress_data:
        if progress_data.get("completed_chapters"):
            lines.append("### 已完成章节")
            lines.append("")
            for ch in progress_data["completed_chapters"]:
                lines.append(f"- ✅ 第{ch['number']}章: {ch['title']} → `{ch.get('file', '?')}`")
            lines.append("")

        if progress_data.get("missing_chapters"):
            lines.append("### 待编写章节")
            lines.append("")
            for ch in progress_data["missing_chapters"]:
                lines.append(f"- ⬜ 第{ch['number']}章: {ch['title']}")
            lines.append("")

    # ===== 依赖检查 =====
    lines.append("---")
    lines.append("## 🔗 依赖与链接检查")
    lines.append("")
    if dep_data:
        s = dep_data.get("summary", {})
        level = "pass" if s.get("all_pass") else "warn"
        lines.append(f"- 总链接数: {s.get('total_links', 0)}")
        lines.append(f"- 失效内部链接: {s.get('total_broken_internal', 0)} {severity_badge(level)}")
        lines.append(f"- 跨章引用问题: {s.get('cross_reference_issues', 0)}")
        lines.append("")
    else:
        lines.append("*依赖检查数据不可用*")
        lines.append("")

    # ===== 建议 =====
    lines.append("---")
    lines.append("## 🎯 建议与下一步操作")
    lines.append("")
    if progress_data and progress_data.get("suggestions"):
        for i, sug in enumerate(progress_data["suggestions"], 1):
            priority = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(sug.get("priority", ""), "⚪")
            lines.append(f"{i}. {priority} **{sug.get('action', '?')}**: {sug.get('description', '')}")
        lines.append("")

    # ===== 尾部 =====
    lines.append("---")
    lines.append(f"*本报告由 Complex Task Automator Skill 自动生成 | {now}*")

    report = "\n".join(lines)

    # 保存
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    report_file = Path(OUTPUT_DIR) / "project-report.md"
    report_file.write_text(report, encoding=get_encoding())

    # 项目目录副本
    proj_report = Path(PROJECT_DIR) / ".automation-report.md"
    proj_report.write_text(report, encoding=get_encoding())

    log.info(f"报告已保存 → {report_file}")
    print(report)


if __name__ == "__main__":
    run()
