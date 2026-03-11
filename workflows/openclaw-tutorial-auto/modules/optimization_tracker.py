#!/usr/bin/env python3
"""
optimization_tracker.py — 优化历史反馈闭环模块
================================================
追踪每次优化前后的质量分数变化，存储优化历史，生成趋势报告。

核心功能:
  1. 记录每次优化的 pre/post 分数
  2. 追踪哪些操作类型最有效
  3. 检测质量退化 (分数下降)
  4. 生成趋势图数据 (时间序列)
  5. 提供反馈建议 (哪些优化值得继续)

数据存储: {OUTPUT_DIR}/optimization-history.json
报告输出: {OUTPUT_DIR}/optimization-trends.json
"""

from collections import defaultdict
from datetime import datetime, timezone
import json
import os
import re
import sys

from modules.compat import setup_logger, cfg, load_json, save_json, OUTPUT_DIR

log = setup_logger("optimization_tracker")

MAX_HISTORY = int(cfg("optimize.history_max_entries", "500"))
HISTORY_FILE = "optimization-history.json"
TRENDS_FILE = "optimization-trends.json"


# ═══════════════════════════════════════════════════════
# 历史数据管理
# ═══════════════════════════════════════════════════════

def _load_history(output_dir: str = None) -> list:
    """加载优化历史记录。"""
    output_dir = output_dir or OUTPUT_DIR
    path = os.path.join(output_dir, HISTORY_FILE)
    data = load_json(path, {"entries": []})
    return data.get("entries", [])


def _save_history(entries: list, output_dir: str = None):
    """保存优化历史记录（保留最近 MAX_HISTORY 条）。"""
    output_dir = output_dir or OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)
    # 截断
    if len(entries) > MAX_HISTORY:
        entries = entries[-MAX_HISTORY:]
    path = os.path.join(output_dir, HISTORY_FILE)
    save_json(path, {
        "version": "1.0",
        "max_entries": MAX_HISTORY,
        "total_entries": len(entries),
        "last_updated": datetime.now(tz=timezone.utc).isoformat(),
        "entries": entries,
    })


def record_optimization(
    chapter_num: int,
    chapter_file: str,
    pre_score: dict,
    post_score: dict,
    changes_applied: list,
    pipeline_run_id: str = None,
    output_dir: str = None,
) -> dict:
    """
    记录一次优化操作的前后分数。

    Args:
        chapter_num: 章节编号
        chapter_file: 章节文件名
        pre_score: 优化前评分 {total, dimensions, grade}
        post_score: 优化后评分 {total, dimensions, grade}
        changes_applied: 应用的修改列表
        pipeline_run_id: 流水线运行ID
        output_dir: 输出目录

    Returns:
        dict: 记录条目
    """
    output_dir = output_dir or OUTPUT_DIR
    entries = _load_history(output_dir)

    delta_total = (post_score.get("total", 0) - pre_score.get("total", 0))
    pre_dims = pre_score.get("dimensions", {})
    post_dims = post_score.get("dimensions", {})
    delta_dims = {
        dim: post_dims.get(dim, 0) - pre_dims.get(dim, 0)
        for dim in set(list(pre_dims.keys()) + list(post_dims.keys()))
    }

    entry = {
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "chapter": chapter_num,
        "file": chapter_file,
        "pipeline_run_id": pipeline_run_id,
        "pre_score": {
            "total": pre_score.get("total", 0),
            "grade": pre_score.get("grade", "?"),
            "dimensions": pre_dims,
        },
        "post_score": {
            "total": post_score.get("total", 0),
            "grade": post_score.get("grade", "?"),
            "dimensions": post_dims,
        },
        "delta": {
            "total": round(delta_total, 1),
            "dimensions": delta_dims,
            "improved": delta_total > 0,
            "regressed": delta_total < 0,
        },
        "changes": changes_applied,
        "change_count": len(changes_applied),
    }

    entries.append(entry)
    _save_history(entries, output_dir)

    # 回归警告
    if delta_total < -5:
        log.warning(f"  ⚠ 质量退化警告: 第{chapter_num}章 "
                     f"{pre_score.get('total', 0)} → {post_score.get('total', 0)} "
                     f"(Δ={delta_total:+.1f})")
    elif delta_total > 0:
        log.info(f"  ✅ 第{chapter_num}章 提升 {delta_total:+.1f} 分 "
                  f"({pre_score.get('grade', '?')} → {post_score.get('grade', '?')})")

    return entry


def record_batch(
    scan_before: dict,
    scan_after: dict,
    refine_result: dict,
    pipeline_run_id: str = None,
    output_dir: str = None,
) -> list:
    """
    批量记录一次流水线运行中所有章节的优化结果。

    Args:
        scan_before: 优化前扫描报告
        scan_after: 优化后扫描报告 (需二次扫描)
        refine_result: 精炼结果
        pipeline_run_id: 流水线运行ID

    Returns:
        list: 记录条目列表
    """
    output_dir = output_dir or OUTPUT_DIR
    entries = []

    # 索引优化前分数
    pre_scores = {}
    for ch in scan_before.get("chapters", []):
        if "error" not in ch:
            pre_scores[ch.get("number", 0)] = ch.get("score_detail", {
                "total": ch.get("quality_score", 0),
                "grade": ch.get("score_detail", {}).get("grade", "?"),
                "dimensions": ch.get("score_detail", {}).get("dimensions", {}),
            })

    # 索引优化后分数
    post_scores = {}
    for ch in scan_after.get("chapters", []):
        if "error" not in ch:
            post_scores[ch.get("number", 0)] = ch.get("score_detail", {
                "total": ch.get("quality_score", 0),
                "grade": ch.get("score_detail", {}).get("grade", "?"),
                "dimensions": ch.get("score_detail", {}).get("dimensions", {}),
            })

    # 索引精炼操作
    refine_changes = {}
    for r in refine_result.get("results", []):
        ch_num = r.get("chapter", 0)
        refine_changes[ch_num] = r.get("changes_applied", [])

    # 对有变更的章节记录
    for ch_num, changes in refine_changes.items():
        if not changes:
            continue
        pre = pre_scores.get(ch_num, {"total": 0, "grade": "?", "dimensions": {}})
        post = post_scores.get(ch_num, pre)
        entry = record_optimization(
            chapter_num=ch_num,
            chapter_file=f"{ch_num:02d}-*.md",
            pre_score=pre,
            post_score=post,
            changes_applied=changes,
            pipeline_run_id=pipeline_run_id,
            output_dir=output_dir,
        )
        entries.append(entry)

    return entries


# ═══════════════════════════════════════════════════════
# 趋势分析
# ═══════════════════════════════════════════════════════

def analyze_trends(output_dir: str = None) -> dict:
    """
    分析优化历史趋势。

    Returns:
        dict: 趋势报告 {
            per_chapter_trends,
            effective_changes,
            regression_alerts,
            overall_trend,
            recommendations,
        }
    """
    output_dir = output_dir or OUTPUT_DIR
    entries = _load_history(output_dir)

    if not entries:
        return {
            "status": "no_history",
            "message": "尚无优化历史记录",
            "recommendations": ["运行一次完整流水线以开始追踪"],
        }

    # ── 按章节聚合 ──
    chapter_entries = defaultdict(list)
    for e in entries:
        chapter_entries[e["chapter"]].append(e)

    per_chapter = {}
    for ch_num, ch_entries in chapter_entries.items():
        ch_entries.sort(key=lambda x: x["timestamp"])
        scores = [e["post_score"]["total"] for e in ch_entries]
        deltas = [e["delta"]["total"] for e in ch_entries]
        per_chapter[ch_num] = {
            "optimization_count": len(ch_entries),
            "first_score": ch_entries[0]["pre_score"]["total"],
            "latest_score": scores[-1] if scores else 0,
            "best_score": max(scores) if scores else 0,
            "worst_score": min(scores) if scores else 0,
            "cumulative_delta": round(sum(deltas), 1),
            "avg_delta": round(sum(deltas) / len(deltas), 1) if deltas else 0,
            "has_regression": any(d < -2 for d in deltas),
            "score_timeline": [
                {"time": e["timestamp"], "score": e["post_score"]["total"]}
                for e in ch_entries
            ],
        }

    # ── 操作类型效果分析 ──
    change_effectiveness = defaultdict(lambda: {"count": 0, "total_delta": 0})
    for e in entries:
        per_change_delta = (
            e["delta"]["total"] / max(e["change_count"], 1)
        )
        for change in e.get("changes", []):
            # 标准化操作类型
            change_type = _normalize_change_type(change)
            change_effectiveness[change_type]["count"] += 1
            change_effectiveness[change_type]["total_delta"] += per_change_delta

    effective_changes = []
    for change_type, stats in change_effectiveness.items():
        avg_impact = round(stats["total_delta"] / max(stats["count"], 1), 2)
        effective_changes.append({
            "change_type": change_type,
            "count": stats["count"],
            "avg_impact": avg_impact,
            "total_impact": round(stats["total_delta"], 1),
        })
    effective_changes.sort(key=lambda x: -x["avg_impact"])

    # ── 回归警告 ──
    regressions = []
    for e in entries:
        if e["delta"]["total"] < -2:
            regressions.append({
                "chapter": e["chapter"],
                "timestamp": e["timestamp"],
                "delta": e["delta"]["total"],
                "pre_grade": e["pre_score"]["grade"],
                "post_grade": e["post_score"]["grade"],
                "changes": e.get("changes", []),
            })

    # ── 维度分析 ──
    dim_deltas = defaultdict(list)
    for e in entries:
        for dim, delta in e.get("delta", {}).get("dimensions", {}).items():
            dim_deltas[dim].append(delta)

    dimension_trends = {}
    for dim, deltas in dim_deltas.items():
        dimension_trends[dim] = {
            "total_improvements": sum(1 for d in deltas if d > 0),
            "total_regressions": sum(1 for d in deltas if d < 0),
            "avg_delta": round(sum(deltas) / len(deltas), 2) if deltas else 0,
            "cumulative": round(sum(deltas), 1),
        }

    # ── 总体趋势 ──
    all_deltas = [e["delta"]["total"] for e in entries]
    recent_deltas = [e["delta"]["total"] for e in entries[-10:]]

    overall = {
        "total_optimizations": len(entries),
        "total_chapters_touched": len(chapter_entries),
        "avg_improvement": round(sum(all_deltas) / len(all_deltas), 1) if all_deltas else 0,
        "recent_avg_improvement": round(sum(recent_deltas) / len(recent_deltas), 1) if recent_deltas else 0,
        "total_regressions": sum(1 for d in all_deltas if d < -2),
        "trend_direction": (
            "improving" if sum(recent_deltas) > 0 else
            "stable" if abs(sum(recent_deltas)) < 2 else
            "regressing"
        ),
    }

    # ── 建议 ──
    recommendations = _generate_recommendations(
        per_chapter, effective_changes, regressions, overall
    )

    report = {
        "analysis_time": datetime.now(tz=timezone.utc).isoformat(),
        "data_range": {
            "first_entry": entries[0]["timestamp"] if entries else None,
            "last_entry": entries[-1]["timestamp"] if entries else None,
            "total_entries": len(entries),
        },
        "overall": overall,
        "per_chapter": per_chapter,
        "effective_changes": effective_changes,
        "dimension_trends": dimension_trends,
        "regressions": regressions,
        "recommendations": recommendations,
    }

    return report


def _normalize_change_type(change_desc: str) -> str:
    """标准化操作类型描述。"""
    change_lower = change_desc.lower()
    if "navigation" in change_lower or "nav" in change_lower:
        return "add_navigation"
    elif "toc" in change_lower or "table of contents" in change_lower or "目录" in change_lower:
        return "add_toc"
    elif "heading" in change_lower or "标题" in change_lower:
        return "fix_heading"
    elif "code" in change_lower and ("label" in change_lower or "lang" in change_lower):
        return "add_code_labels"
    elif "faq" in change_lower or "常见问题" in change_lower:
        return "add_faq"
    elif "summary" in change_lower or "小结" in change_lower:
        return "add_summary"
    elif "reference" in change_lower or "参考" in change_lower:
        return "add_references"
    elif "cjk" in change_lower or "spacing" in change_lower or "间距" in change_lower:
        return "fix_cjk_spacing"
    elif "dense" in change_lower or "blank" in change_lower or "密排" in change_lower:
        return "fix_dense_blocks"
    else:
        return change_desc[:40]


def _generate_recommendations(per_chapter, effective_changes, regressions, overall):
    """基于趋势分析生成优化建议。"""
    recs = []

    # 效果最好的操作
    if effective_changes:
        top = effective_changes[0]
        if top["avg_impact"] > 0:
            recs.append({
                "priority": "high",
                "type": "continue_effective",
                "message": (
                    f"继续执行 '{top['change_type']}' — "
                    f"平均每次提升 {top['avg_impact']:+.1f} 分 "
                    f"(执行 {top['count']} 次)"
                ),
            })

    # 效果最差的操作
    if effective_changes:
        worst = effective_changes[-1]
        if worst["avg_impact"] < -0.5:
            recs.append({
                "priority": "high",
                "type": "stop_harmful",
                "message": (
                    f"建议减少 '{worst['change_type']}' — "
                    f"平均导致退化 {worst['avg_impact']:+.1f} 分"
                ),
            })

    # 需要关注的章节
    for ch_num, stats in per_chapter.items():
        if stats["has_regression"] and stats["latest_score"] < stats["best_score"] - 5:
            recs.append({
                "priority": "medium",
                "type": "chapter_attention",
                "message": (
                    f"第{ch_num}章 出现质量退化: 最佳 {stats['best_score']} → "
                    f"当前 {stats['latest_score']} (Δ={stats['latest_score'] - stats['best_score']:+.1f})"
                ),
            })

    # 长期未优化的章节
    optimized_chapters = set(per_chapter.keys())
    if len(optimized_chapters) < 21:
        missing = set(range(1, 22)) - optimized_chapters
        if missing:
            recs.append({
                "priority": "low",
                "type": "untouched_chapters",
                "message": f"以下章节从未被优化: {sorted(missing)}",
            })

    # 总体趋势
    if overall["trend_direction"] == "regressing":
        recs.append({
            "priority": "high",
            "type": "trend_warning",
            "message": "近期优化趋势为退化，建议审查最近的修改策略",
        })
    elif overall["trend_direction"] == "stable" and overall["total_optimizations"] > 10:
        recs.append({
            "priority": "medium",
            "type": "plateau",
            "message": "优化效果已趋于平稳，考虑引入新的优化策略（如内容重写、AI辅助润色）",
        })

    recs.sort(key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x["priority"], 3))
    return recs


# ═══════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════

def run():
    """主入口: 分析趋势并保存报告。"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    report = analyze_trends()

    out_path = os.path.join(OUTPUT_DIR, TRENDS_FILE)
    save_json(out_path, report)
    log.info(f"优化趋势报告已保存: {out_path}")

    overall = report.get("overall", {})
    log.info(f"  总优化次数: {overall.get('total_optimizations', 0)}")
    log.info(f"  平均提升: {overall.get('avg_improvement', 0):+.1f}")
    log.info(f"  趋势: {overall.get('trend_direction', '?')}")

    recs = report.get("recommendations", [])
    if recs:
        log.info(f"  建议: ({len(recs)} 条)")
        for r in recs[:3]:
            log.info(f"    - [{r['priority']}] {r['message']}")

    return report


if __name__ == "__main__":
    run()
