#!/usr/bin/env python3
"""
大纲管理 — 解析大纲、生成优化建议、追踪变更历史
使用 utils 共享模块，消除重复代码。
"""
import json, re
from pathlib import Path
from datetime import datetime

from utils import (
    get_project_dir,
    get_output_dir,
    parse_outline,
    find_completed_chapters,
    read_chapter,
    save_json,
    load_json,
    setup_logger,
    get_encoding,
    cfg,
)

log = setup_logger("manage_outline")


# ═══════════════════════════════════════════════════════
# 章节详情 — 基于 utils.read_chapter 的薄封装
# ═══════════════════════════════════════════════════════

def _build_chapter_map(proj_dir: str) -> dict:
    """
    为每个已完成章节调用 read_chapter()，返回
    {chapter_number: {file, headings, word_count, has_summary, has_next}, ...}
    """
    chapter_map = {}
    for ch in find_completed_chapters(proj_dir):
        info = read_chapter(ch["number"], proj_dir)
        if info is None:
            continue
        chapter_map[ch["number"]] = {
            "file": info["file"],
            "headings": info["headings"],
            "word_count": info["word_count"],
            "has_summary": bool(re.search(r"本章小结", info["content"])),
            "has_next": bool(re.search(r"下一章", info["content"])),
        }
    return chapter_map


# ═══════════════════════════════════════════════════════
# 章节结构生成
# ═══════════════════════════════════════════════════════

def generate_chapter_structure(
    chapter_num: int,
    title: str,
    prev_chapters: dict,
    research_data: dict | None = None,
) -> dict:
    """根据上下文为目标章节生成推荐的大纲结构。

    research_data 若包含 'keywords' 列表，会影响小节生成逻辑。
    """
    # 分析已有章节的模式
    avg_sections = 0
    patterns = []
    for _num, info in prev_chapters.items():
        h2_count = len([h for h in info["headings"] if h["level"] == 2])
        avg_sections += h2_count
        patterns.append(h2_count)
    if patterns:
        avg_sections = round(avg_sections / len(patterns))
    else:
        avg_sections = int(cfg("outline.default_sections", 6))

    # 从 research_data 提取额外关键词来辅助小节生成
    extra_keywords: list[str] = []
    if research_data and isinstance(research_data, dict):
        extra_keywords = research_data.get("keywords", [])

    # 生成推荐结构
    sections = [{"level": 1, "text": f"第{chapter_num}章：{title}"}]

    topic_sections = _generate_topic_sections(title, avg_sections, extra_keywords)
    for i, sec in enumerate(topic_sections, 1):
        sections.append({"level": 2, "text": f"{chapter_num}.{i} {sec}"})

    sections.append({"level": 2, "text": "常见问题"})
    sections.append({"level": 2, "text": "本章小结"})

    return {
        "chapter_num": chapter_num,
        "title": title,
        "recommended_sections": sections,
        "recommended_section_count": len(sections),
        "based_on_avg": avg_sections,
    }


def _generate_topic_sections(
    title: str, target_count: int, extra_keywords: list[str] | None = None,
) -> list:
    """基于标题关键词生成小节标题"""
    keyword_sections = {
        "Skills": ["Skills 简介", "Skills 目录结构", "SKILL.md 编写", "Skills 开发流程", "批量管理", "调试与测试"],
        "插件": ["插件体系概述", "插件结构", "插件开发规范", "插件安装与启用", "批量操作", "调试技巧"],
        "安装": ["安装前准备", "安装步骤", "验证安装", "常见安装问题"],
        "管理": ["管理概述", "启用与禁用", "版本管理", "批量操作", "最佳实践"],
        "ClawHub": ["ClawHub 简介", "注册与发布", "搜索与安装", "版本管理", "社区协作"],
        "自动化": ["自动化概述", "命令行工具", "脚本集成", "定时任务", "批处理", "实战案例"],
        "飞书": ["飞书集成概述", "App 创建与配置", "消息接收", "消息发送", "Webhook", "高级功能"],
        "Agent": ["Agent 概念", "Agent 配置", "多 Agent 路由", "Agent 通信", "实战部署"],
        "Gateway": ["Gateway 概述", "配置管理", "多 Agent 配置", "路由规则", "监控"],
        "故障": ["日志系统", "常见错误", "排查流程", "诊断工具", "性能分析"],
        "日志": ["日志配置", "日志查看", "日志分析", "告警设置"],
        "集成": ["集成概述", "API 接入", "Webhook 配置", "第三方服务", "安全考虑"],
        "持续": ["CI/CD 概述", "自动构建", "知识库同步", "发布流程"],
        "案例": ["场景一", "场景二", "场景三", "经验总结"],
        "维护": ["维护策略", "更新机制", "备份与恢复", "自动化脚本"],
    }

    sections = []
    for keyword, secs in keyword_sections.items():
        if keyword in title:
            sections = secs[:target_count]
            break

    if not sections:
        sections = [
            f"{title} 概述",
            "核心概念",
            "配置与使用",
            "进阶用法",
            "实战示例",
            "最佳实践",
        ][:target_count]

    # 如果 research_data 提供了额外关键词，追加尚未覆盖的
    if extra_keywords:
        existing_texts = {s.lower() for s in sections}
        for kw in extra_keywords:
            if kw.lower() not in existing_texts and len(sections) < target_count:
                sections.append(kw)

    return sections


# ═══════════════════════════════════════════════════════
# 大纲历史追踪（含内容去重）
# ═══════════════════════════════════════════════════════

def track_outline_history(proj_dir: str, out_dir: str) -> str | None:
    """追踪大纲变更历史，仅在内容发生变化时才保存新快照。"""
    history_dir = Path(out_dir) / "outline-history"
    history_dir.mkdir(parents=True, exist_ok=True)

    outline_path = Path(proj_dir) / "OUTLINE.md"
    if not outline_path.is_file():
        return None

    current_content = outline_path.read_text(encoding=get_encoding())

    # 查找最新的历史快照，比较内容
    existing = sorted(history_dir.glob("OUTLINE-*.md"))
    if existing:
        latest = existing[-1].read_text(encoding=get_encoding())
        if latest == current_content:
            log.debug("大纲内容未变化，跳过历史快照")
            return None

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = history_dir / f"OUTLINE-{ts}.md"
    dst.write_text(current_content, encoding=get_encoding())
    log.info("已保存大纲快照: %s", dst.name)
    return str(dst)


# ═══════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════

def run():
    proj_dir = get_project_dir()
    out_dir = get_output_dir()
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    log.info("开始大纲分析 — 项目: %s", proj_dir)

    outline = parse_outline(proj_dir)
    chapters = _build_chapter_map(proj_dir)
    completed_nums = set(chapters.keys())

    # 加载研究数据（如果有）
    research_data = load_json(Path(out_dir) / "research-data.json")

    # 找到下一个待写章节
    next_chapter = None
    for item in outline:
        if item["number"] not in completed_nums:
            next_chapter = item
            break

    # 为下一章生成推荐结构
    recommended_structure = None
    if next_chapter:
        recommended_structure = generate_chapter_structure(
            next_chapter["number"],
            next_chapter["title"],
            chapters,
            research_data,
        )

    # 大纲优化建议
    suggestions = []
    for item in outline:
        if item["number"] in completed_nums:
            ch = chapters[item["number"]]
            if not ch["has_summary"]:
                suggestions.append({
                    "chapter": item["number"],
                    "type": "missing_summary",
                    "message": f"第{item['number']}章缺少'本章小结'",
                })
            if not ch["has_next"] and item["number"] < len(outline):
                suggestions.append({
                    "chapter": item["number"],
                    "type": "missing_next_ref",
                    "message": f"第{item['number']}章缺少'下一章'指引",
                })
            min_words = int(cfg("quality.min_words_per_chapter", 500))
            if ch["word_count"] < min_words:
                suggestions.append({
                    "chapter": item["number"],
                    "type": "short_content",
                    "message": f"第{item['number']}章内容偏少（{ch['word_count']}字）",
                })

    # 追踪历史
    history_file = track_outline_history(proj_dir, out_dir)

    result = {
        "timestamp": datetime.now().isoformat(),
        "outline": outline,
        "total_chapters": len(outline),
        "completed": sorted(list(completed_nums)),
        "completed_count": len(completed_nums),
        "next_chapter": next_chapter,
        "recommended_structure": recommended_structure,
        "suggestions": suggestions,
        "history_file": history_file,
    }

    save_json(Path(out_dir) / "outline-analysis.json", result)
    log.info("大纲分析完成 — 已完成 %d/%d 章", len(completed_nums), len(outline))
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    run()
