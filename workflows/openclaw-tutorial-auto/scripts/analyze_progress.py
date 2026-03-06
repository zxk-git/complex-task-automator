#!/usr/bin/env python3
"""
openclaw-tutorial-auto 项目 — 内容完整性与进度分析
对比大纲，识别未完成章节，生成待办任务列表。
使用 utils 共享模块统一路径、解析和输出。
"""
import json
from datetime import datetime
from pathlib import Path

from utils import (
    get_project_dir,
    get_output_dir,
    parse_outline,
    find_completed_chapters,
    save_json,
    load_json,
    setup_logger,
    get_encoding,
    cfg,
)

log = setup_logger("analyze_progress")

# 质量分数低于此阈值的章节将被建议优化
QUALITY_THRESHOLD = cfg("quality.min_score", 70)


def _build_chapter_map(chapters: list[dict]) -> dict[int, dict]:
    """将 find_completed_chapters 列表转换为 {编号: 信息} 映射"""
    return {ch["number"]: ch for ch in chapters}


def _load_quality_scores(output_dir: str) -> dict[str, dict]:
    """
    加载 check_quality 产出的 02-quality-check.json，
    返回 {filename: {"score": float, "pass": bool}} 映射。
    文件不存在或格式异常时返回空字典。
    """
    quality_data = load_json(Path(output_dir) / "02-quality-check.json")
    if not quality_data or "chapters" not in quality_data:
        return {}
    scores: dict[str, dict] = {}
    for ch in quality_data["chapters"]:
        fname = ch.get("file", "")
        q = ch.get("quality", {})
        if fname and "score" in q:
            scores[fname] = {"score": q["score"], "pass": q.get("pass", True)}
    return scores


def run():
    proj_dir = get_project_dir()
    output_dir = get_output_dir()

    log.info("开始进度分析 — 项目目录: %s", proj_dir)

    # ── 大纲 & 已完成章节 ──
    outline = parse_outline(proj_dir)
    chapter_list = find_completed_chapters(proj_dir)
    chapter_map = _build_chapter_map(chapter_list)

    log.info("大纲条目: %d | 已有文件: %d", len(outline), len(chapter_list))

    # ── 质量评分（如有） ──
    quality_scores = _load_quality_scores(output_dir)
    if quality_scores:
        log.info("已加载质量评分: %d 个章节", len(quality_scores))

    # ── 对比 ──
    completed = []
    missing = []
    next_task = None

    for item in outline:
        num = item["number"]
        if num in chapter_map:
            completed.append({
                **item,
                **chapter_map[num],
                "status": "completed",
            })
        else:
            entry = {**item, "status": "missing", "file": None}
            missing.append(entry)
            if next_task is None:
                next_task = entry

    total = len(outline)
    done = len(completed)

    # ── 生成建议 ──
    suggestions: list[dict] = []

    # 1) 高优先级：下一个缺失章节
    if next_task:
        num = next_task["number"]
        title = next_task["title"]
        suggested_filename = (
            f"{num:02d}-{title.replace(' ', '-').replace('：', '-').replace('/', '-')}.md"
        )
        suggestions.append({
            "priority": "high",
            "action": "create_chapter",
            "chapter": num,
            "title": title,
            "suggested_filename": suggested_filename,
            "description": f"下一个需要编写的章节: 第{num}章《{title}》",
        })

    # 2) 质量优化：低分章节
    low_quality = []
    for ch in completed:
        fname = ch.get("file", "")
        qs = quality_scores.get(fname)
        if qs and qs["score"] < QUALITY_THRESHOLD:
            low_quality.append((ch, qs["score"]))
    low_quality.sort(key=lambda x: x[1])  # 最低分优先

    for ch_info, score in low_quality[:3]:
        suggestions.append({
            "priority": "high",
            "action": "optimize_chapter",
            "chapter": ch_info["number"],
            "title": ch_info.get("title", ""),
            "file": ch_info["file"],
            "quality_score": score,
            "description": (
                f"第{ch_info['number']}章质量评分仅 {score}（阈值 {QUALITY_THRESHOLD}），建议优化"
            ),
        })

    # 3) 中优先级：回顾已完成章节
    if 0 < done < total:
        suggestions.append({
            "priority": "medium",
            "action": "review_existing",
            "description": f"建议回顾已完成的 {done} 个章节，确保内容一致性",
        })

    # 4) 低优先级：规划后续缺失章节
    if missing:
        for m in missing[1:4]:
            suggestions.append({
                "priority": "low",
                "action": "plan_chapter",
                "chapter": m["number"],
                "title": m["title"],
                "description": f"规划第{m['number']}章《{m['title']}》的内容结构",
            })

    results = {
        "timestamp": datetime.now().isoformat(),
        "progress": {
            "completed": done,
            "missing": len(missing),
            "total": total,
            "percentage": round(done / total * 100, 1) if total > 0 else 0,
        },
        "completed_chapters": completed,
        "missing_chapters": missing,
        "next_task": next_task,
        "suggestions": suggestions,
    }

    # ── 保存 ──
    out_file = Path(output_dir) / "03-progress-analysis.json"
    save_json(out_file, results)
    log.info("进度报告已保存: %s", out_file)
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run()
