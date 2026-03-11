#!/usr/bin/env python3
"""
readability_analyzer.py — 阅读时间与难度递进分析模块
=====================================================
为每个章节计算:
  1. 阅读时间估算 (分钟) — 基于中文/英文字数 + 代码块阅读时间
  2. 难度级别 (beginner / intermediate / advanced)
  3. 难度递进验证 — 检测系列教程是否合理递进

输出: {OUTPUT_DIR}/readability-report.json
"""

from collections import defaultdict
from datetime import datetime, timezone
import json
import os
import re
import sys

from modules.compat import setup_logger, cfg, load_json, save_json, word_count

log = setup_logger("readability_analyzer")

OUTPUT_DIR = cfg("output_dir", os.environ.get(
    "OUTPUT_DIR", "/tmp/openclaw-tutorial-auto-reports"))
PROJECT_DIR = cfg("project_dir", os.environ.get(
    "PROJECT_DIR", "/root/.openclaw/workspace/zxk-private/openclaw-tutorial-auto"))


# ═══════════════════════════════════════════════════════
# 阅读时间估算常量
# ═══════════════════════════════════════════════════════

# 中文阅读速度 (字/分钟), 来源: 参考研究, 技术教程场景偏慢
CJK_WORDS_PER_MIN = 300
# 英文阅读速度 (词/分钟)
ENG_WORDS_PER_MIN = 150
# 代码块额外阅读时间 (分钟/块)
CODE_BLOCK_MIN = 1.5
# 表格额外阅读时间 (分钟/个)
TABLE_MIN = 0.5
# 图片浏览时间 (分钟/张)
IMAGE_MIN = 0.3


# ═══════════════════════════════════════════════════════
# 难度指标关键词
# ═══════════════════════════════════════════════════════

DIFFICULTY_KEYWORDS = {
    "advanced": {
        "keywords": [
            "高级", "进阶", "深入", "架构", "原理", "内部实现",
            "源码", "底层", "性能优化", "集群", "分布式",
            "生产环境", "安全加固", "灾难恢复", "自定义协议",
            "插件开发", "SDK开发", "webhook", "API开发",
        ],
        "cli_advanced": [
            "openclaw daemon", "openclaw config set",
            "openclaw extension", "openclaw hook",
        ],
        "concepts": [
            r"mcp\s+protocol", r"event\s*loop", r"async\b",
            r"middleware", r"interceptor", r"pipeline",
            r"topological", r"concurren",
        ],
    },
    "intermediate": {
        "keywords": [
            "配置", "管理", "集成", "调试", "日志", "监控",
            "定时", "调度", "自动化", "工作流", "飞书",
            "浏览器", "部署", "Docker",
        ],
        "cli_advanced": [
            "openclaw skill", "openclaw cron",
            "openclaw run", "openclaw workflow",
        ],
        "concepts": [
            r"yaml\b", r"json\b", r"crontab", r"regex\b",
            r"environment\s+variable", r"config\b",
        ],
    },
    "beginner": {
        "keywords": [
            "安装", "入门", "基础", "初识", "简介", "概述",
            "快速开始", "Hello", "第一个", "什么是",
        ],
        "cli_advanced": [],
        "concepts": [
            r"npm\s+install", r"pip\s+install",
            r"--version", r"--help",
        ],
    },
}


# ═══════════════════════════════════════════════════════
# 阅读时间计算
# ═══════════════════════════════════════════════════════

def estimate_reading_time(text: str) -> dict:
    """
    估算章节阅读时间。

    Returns:
        dict: {
            total_minutes: float,
            text_minutes: float,
            code_minutes: float,
            table_minutes: float,
            image_minutes: float,
            cjk_chars: int,
            eng_words: int,
            code_blocks: int,
            tables: int,
            images: int,
        }
    """
    lines = text.split("\n")
    in_code = False
    text_lines = []
    code_block_count = 0

    for line in lines:
        if line.strip().startswith("```"):
            if not in_code:
                code_block_count += 1
            in_code = not in_code
            continue
        if not in_code:
            text_lines.append(line)

    # 纯文本
    plain_text = "\n".join(text_lines)
    cjk_chars = len(re.findall(r'[\u4e00-\u9fff]', plain_text))
    eng_words = len(re.findall(r'[a-zA-Z]+', plain_text))

    # 表格、图片
    tables = len(re.findall(r'^\|.+\|$\n\|[-:| ]+\|$', text, re.MULTILINE))
    images = len(re.findall(r'!\[.*?\]\(.*?\)', text))

    # 时间计算
    text_min = cjk_chars / CJK_WORDS_PER_MIN + eng_words / ENG_WORDS_PER_MIN
    code_min = code_block_count * CODE_BLOCK_MIN
    table_min = tables * TABLE_MIN
    image_min = images * IMAGE_MIN
    total = text_min + code_min + table_min + image_min

    return {
        "total_minutes": round(total, 1),
        "text_minutes": round(text_min, 1),
        "code_minutes": round(code_min, 1),
        "table_minutes": round(table_min, 1),
        "image_minutes": round(image_min, 1),
        "cjk_chars": cjk_chars,
        "eng_words": eng_words,
        "code_blocks": code_block_count,
        "tables": tables,
        "images": images,
        "display": _format_time(total),
    }


def _format_time(minutes: float) -> str:
    """将分钟数格式化为可读时间。"""
    if minutes < 1:
        return "< 1 分钟"
    elif minutes < 60:
        return f"约 {round(minutes)} 分钟"
    else:
        hours = int(minutes // 60)
        mins = round(minutes % 60)
        return f"约 {hours} 小时 {mins} 分钟"


# ═══════════════════════════════════════════════════════
# 难度评估
# ═══════════════════════════════════════════════════════

def assess_difficulty(text: str, title: str = "",
                      chapter_num: int = 0) -> dict:
    """
    评估章节难度等级。

    基于:
    - 关键词密度
    - 代码复杂度
    - 概念数量
    - 章节序号 (越后通常越难)

    Returns:
        dict: {
            level: str,       # beginner / intermediate / advanced
            score: float,     # 0-100 难度分
            factors: list,    # 难度因素
            confidence: float # 置信度 0-1
        }
    """
    text_lower = text.lower()
    title_lower = title.lower()
    factors = []

    # 基础分: 章节序号给出的先验
    if chapter_num <= 5:
        base_score = 20
    elif chapter_num <= 12:
        base_score = 45
    else:
        base_score = 65

    score = base_score

    # 关键词匹配
    for level, rule in DIFFICULTY_KEYWORDS.items():
        kw_count = 0
        for kw in rule["keywords"]:
            count = text_lower.count(kw.lower())
            if count > 0:
                kw_count += count
                if kw.lower() in title_lower:
                    kw_count += 3  # 标题命中权重更高

        for pat in rule.get("concepts", []):
            matches = len(re.findall(pat, text_lower))
            kw_count += matches

        if level == "advanced" and kw_count > 3:
            score += min(30, kw_count * 3)
            factors.append(f"高级关键词命中 {kw_count} 次")
        elif level == "intermediate" and kw_count > 3:
            score += min(15, kw_count * 1.5)
            factors.append(f"中级关键词命中 {kw_count} 次")
        elif level == "beginner" and kw_count > 3:
            score -= min(15, kw_count * 2)
            factors.append(f"入门关键词命中 {kw_count} 次")

    # 代码复杂度
    code_blocks = re.findall(r'```(\w*)\n(.*?)```', text, re.DOTALL)
    avg_code_lines = 0
    if code_blocks:
        code_line_counts = [len(block[1].strip().split("\n")) for block in code_blocks]
        avg_code_lines = sum(code_line_counts) / len(code_line_counts)
        if avg_code_lines > 20:
            score += 10
            factors.append(f"代码块平均 {avg_code_lines:.0f} 行 (长)")
        elif avg_code_lines > 10:
            score += 5
            factors.append(f"代码块平均 {avg_code_lines:.0f} 行 (中)")

    # 专业术语密度
    tech_terms = len(re.findall(
        r'\b(?:API|SDK|CLI|HTTP|HTTPS|JSON|YAML|TCP|UDP|WSS|MCP|'
        r'OAuth|JWT|TLS|SSL|SSH|DNS|CDN|CI/CD|Docker|Kubernetes|'
        r'async|await|callback|promise|middleware|webhook|'
        r'daemon|systemd|crontab|nginx)\b',
        text, re.IGNORECASE
    ))
    total_words = word_count(text)
    term_density = tech_terms / max(total_words, 1) * 1000  # 千词密度
    if term_density > 20:
        score += 10
        factors.append(f"技术术语密度: {term_density:.0f}/千字 (高)")
    elif term_density > 10:
        score += 5
        factors.append(f"技术术语密度: {term_density:.0f}/千字 (中)")

    # 截断 score 到 0-100
    score = max(0, min(100, round(score)))

    # 分级
    if score >= 70:
        level = "advanced"
    elif score >= 35:
        level = "intermediate"
    else:
        level = "beginner"

    # 置信度 (基于因素数量)
    confidence = min(1.0, 0.4 + len(factors) * 0.15)

    return {
        "level": level,
        "score": score,
        "factors": factors,
        "confidence": round(confidence, 2),
        "label_cn": {"beginner": "入门", "intermediate": "中级", "advanced": "高级"}[level],
        "label_emoji": {"beginner": "🟢", "intermediate": "🟡", "advanced": "🔴"}[level],
    }


# ═══════════════════════════════════════════════════════
# 难度递进验证
# ═══════════════════════════════════════════════════════

def validate_progression(chapters: list) -> dict:
    """
    验证教程系列的难度递进是否合理。

    规则:
    - 前 1/3 应以 beginner 为主
    - 中 1/3 应以 intermediate 为主
    - 后 1/3 应以 advanced 为主
    - 不应有大幅度难度跳跃 (相邻章节分差 > 30)
    - 不应有大幅度回落 (跳回更简单)

    Args:
        chapters: list of {chapter, difficulty_score, difficulty_level, ...}

    Returns:
        dict: 验证结果
    """
    if not chapters:
        return {"status": "no_data", "issues": []}

    n = len(chapters)
    issues = []
    chapters_sorted = sorted(chapters, key=lambda c: c.get("chapter", 0))

    # 相邻章节跳跃检测
    prev_score = None
    for ch in chapters_sorted:
        score = ch.get("difficulty_score", 50)
        ch_num = ch.get("chapter", 0)
        if prev_score is not None:
            delta = score - prev_score
            if delta > 30:
                issues.append({
                    "type": "difficulty_spike",
                    "severity": "major",
                    "chapter": ch_num,
                    "message": f"第{ch_num}章难度跳跃过大: Δ={delta:+.0f} 分",
                    "detail": f"前一章 {prev_score} → 本章 {score}",
                })
            elif delta < -25:
                issues.append({
                    "type": "difficulty_drop",
                    "severity": "minor",
                    "chapter": ch_num,
                    "message": f"第{ch_num}章难度大幅回落: Δ={delta:+.0f} 分",
                    "detail": f"前一章 {prev_score} → 本章 {score}",
                })
        prev_score = score

    # 三阶段检测
    third = max(1, n // 3)
    early = chapters_sorted[:third]
    mid = chapters_sorted[third:2*third]
    late = chapters_sorted[2*third:]

    early_avg = sum(c.get("difficulty_score", 0) for c in early) / max(len(early), 1)
    mid_avg = sum(c.get("difficulty_score", 0) for c in mid) / max(len(mid), 1)
    late_avg = sum(c.get("difficulty_score", 0) for c in late) / max(len(late), 1)

    if early_avg > mid_avg:
        issues.append({
            "type": "inverted_progression",
            "severity": "major",
            "message": f"前期难度({early_avg:.0f})高于中期({mid_avg:.0f})，递进不合理",
            "chapter": 0,
        })
    if mid_avg > late_avg + 10:
        issues.append({
            "type": "inverted_progression",
            "severity": "minor",
            "message": f"中期难度({mid_avg:.0f})明显高于后期({late_avg:.0f})",
            "chapter": 0,
        })

    # 高级内容过早出现
    for ch in early:
        if ch.get("difficulty_level") == "advanced":
            issues.append({
                "type": "premature_advanced",
                "severity": "major",
                "chapter": ch.get("chapter", 0),
                "message": f"第{ch.get('chapter', 0)}章 被标记为高级，但出现在教程前期",
            })

    return {
        "status": "ok" if not issues else "has_issues",
        "total_issues": len(issues),
        "issues": issues,
        "stage_averages": {
            "early": round(early_avg, 1),
            "mid": round(mid_avg, 1),
            "late": round(late_avg, 1),
        },
        "progression_direction": (
            "ascending" if late_avg > early_avg + 10 else
            "flat" if abs(late_avg - early_avg) <= 10 else
            "descending"
        ),
    }


# ═══════════════════════════════════════════════════════
# 全量分析入口
# ═══════════════════════════════════════════════════════

def analyze_all(project_dir: str = None, scan_report: dict = None) -> dict:
    """
    对所有章节执行阅读时间和难度分析。

    Args:
        project_dir: 项目目录
        scan_report: 可选, 扫描报告 (获取章节列表)

    Returns:
        dict: 完整分析报告
    """
    project_dir = project_dir or PROJECT_DIR
    log.info(f"阅读时间与难度分析: {project_dir}")

    md_files = sorted(
        f for f in os.listdir(project_dir)
        if re.match(r"\d+.*\.md$", f) and not f.endswith(".bak")
    )

    chapters = []
    total_time = 0

    for fname in md_files:
        filepath = os.path.join(project_dir, fname)
        ch_match = re.match(r"(\d+)", fname)
        ch_num = int(ch_match.group(1)) if ch_match else 0

        try:
            with open(filepath, encoding="utf-8") as f:
                text = f.read()

            # 提取标题
            h1_match = re.search(r'^#\s+(.+)$', text, re.MULTILINE)
            title = h1_match.group(1).strip() if h1_match else fname

            # 阅读时间
            reading_time = estimate_reading_time(text)
            total_time += reading_time["total_minutes"]

            # 难度评估
            difficulty = assess_difficulty(text, title, ch_num)

            ch_data = {
                "file": fname,
                "chapter": ch_num,
                "title": title,
                "reading_time": reading_time,
                "difficulty_level": difficulty["level"],
                "difficulty_score": difficulty["score"],
                "difficulty": difficulty,
            }
            chapters.append(ch_data)

            log.info(
                f"  [{ch_num:02d}] {reading_time['display']} | "
                f"{difficulty['label_emoji']} {difficulty['label_cn']} "
                f"(score={difficulty['score']}) | {title[:30]}"
            )
        except Exception as e:
            log.error(f"  分析失败: {fname} — {e}")

    # 难度递进验证
    progression = validate_progression(chapters)

    # 汇总
    times = [c["reading_time"]["total_minutes"] for c in chapters]
    scores = [c["difficulty_score"] for c in chapters]
    level_dist = defaultdict(int)
    for c in chapters:
        level_dist[c["difficulty_level"]] += 1

    report = {
        "analysis_time": datetime.now(tz=timezone.utc).isoformat(),
        "project_dir": project_dir,
        "total_chapters": len(chapters),
        "summary": {
            "total_reading_time": round(total_time, 1),
            "total_reading_display": _format_time(total_time),
            "avg_reading_time": round(total_time / max(len(chapters), 1), 1),
            "min_reading_time": round(min(times), 1) if times else 0,
            "max_reading_time": round(max(times), 1) if times else 0,
            "avg_difficulty": round(sum(scores) / max(len(scores), 1), 1) if scores else 0,
            "difficulty_distribution": dict(level_dist),
        },
        "chapters": chapters,
        "progression": progression,
    }

    return report


def run():
    """主入口。"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    report = analyze_all()

    out_path = os.path.join(OUTPUT_DIR, "readability-report.json")
    save_json(out_path, report)
    log.info(f"分析报告已保存: {out_path}")

    s = report["summary"]
    log.info(f"  总阅读时间: {s['total_reading_display']}")
    log.info(f"  平均阅读: {s['avg_reading_time']:.0f} 分钟/章")
    log.info(f"  难度分布: {s['difficulty_distribution']}")

    p = report["progression"]
    if p["issues"]:
        log.warning(f"  递进问题: {len(p['issues'])} 个")
        for issue in p["issues"][:5]:
            log.warning(f"    - {issue['message']}")

    return report


if __name__ == "__main__":
    run()
