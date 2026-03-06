#!/usr/bin/env python3
"""
optimize_chapter.py — 基于网络最新信息优化已有章节
核心流程: 搜索 → 对比 → 识别差异 → 合并新信息 → 重写 → 质量检查 → 提交
"""
import os
import sys
import re
import time
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from utils import (
    get_project_dir, get_output_dir, read_chapter as utils_read_chapter,
    save_json, load_json, setup_logger, cfg, banner,
    get_git_remote_name, run_git, word_count, trim_history,
)

log = setup_logger("optimize")

PROJECT_DIR = get_project_dir()
OUTPUT_DIR = get_output_dir()
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"

MIN_OPTIMIZE_INTERVAL_HOURS = int(os.environ.get(
    "MIN_OPTIMIZE_INTERVAL_HOURS",
    cfg("optimize.min_interval_hours", 12),
))
OPTIMIZE_HISTORY_FILE = os.path.join(OUTPUT_DIR, "optimize-history.json")


def load_optimize_history() -> dict:
    data = load_json(OPTIMIZE_HISTORY_FILE)
    if data:
        return data
    return {"history": [], "stats": {"total_optimizations": 0, "chapters_optimized": {}}}


def save_optimize_history(history: dict):
    history = trim_history(history, int(cfg("optimize.history_max_entries", 200)))
    save_json(OPTIMIZE_HISTORY_FILE, history)


def can_optimize_chapter(chapter_num: int, history: dict) -> bool:
    """检查该章节是否在冷却期内"""
    ch_key = str(chapter_num)
    ch_stats = history["stats"]["chapters_optimized"].get(ch_key, {})
    last_opt = ch_stats.get("last_optimized")
    if last_opt:
        last_time = datetime.fromisoformat(last_opt)
        hours_since = (datetime.now() - last_time).total_seconds() / 3600
        if hours_since < MIN_OPTIMIZE_INTERVAL_HOURS:
            return False
    return True


def read_chapter(chapter_num: int) -> dict | None:
    """读取章节文件（delegate to utils）"""
    return utils_read_chapter(chapter_num, PROJECT_DIR)


def load_research_data(chapter_num: int) -> dict | None:
    """加载该章节的网络研究数据"""
    # 先查缓存
    cache_dir = Path(OUTPUT_DIR) / "research-cache"
    date_str = datetime.now().strftime("%Y-%m-%d")
    cache_file = cache_dir / f"ch{chapter_num:02d}-{date_str}.json"
    if cache_file.is_file():
        return json.loads(cache_file.read_text(encoding="utf-8"))

    # 查汇总
    summary_file = Path(OUTPUT_DIR) / "web-research-summary.json"
    if summary_file.is_file():
        summary = json.loads(summary_file.read_text(encoding="utf-8"))
        ch_data = summary.get("chapters", {}).get(str(chapter_num))
        if ch_data:
            return ch_data.get("research")
    return None


def extract_new_info(research_data: dict, current_content: str) -> list:
    """从研究数据中提取当前章节缺失的新信息"""
    new_info = []

    if not research_data or not research_data.get("findings"):
        return new_info

    for finding in research_data["findings"]:
        content = finding.get("content", "")
        # 从 Tavily 返回中提取有用的段落
        if content:
            # 提取带有关键信息的段落
            paragraphs = content.split("\n\n")
            for para in paragraphs:
                para = para.strip()
                if len(para) < 30:
                    continue
                # 检查是否包含当前内容中没有的信息
                # 简单匹配：如果整段出现在当前内容中则跳过
                normalized_para = re.sub(r'\s+', ' ', para.lower())
                normalized_content = re.sub(r'\s+', ' ', current_content.lower())
                # 提取关键短语检查
                key_phrases = re.findall(r'[a-zA-Z]{3,}(?:\s+[a-zA-Z]{3,}){0,2}', para)
                novel_phrases = [kp for kp in key_phrases if kp.lower() not in normalized_content]
                if len(novel_phrases) > 2:  # 有3个以上新短语
                    new_info.append({
                        "text": para[:500],
                        "source": finding.get("source", "unknown"),
                        "query": finding.get("query", ""),
                        "novel_phrases": novel_phrases[:5],
                    })

        # 从 DDG results 中提取链接信息
        results = finding.get("results", [])
        for r in results:
            title = r.get("title", "")
            url = r.get("url", "")
            if title and url and title.lower() not in current_content.lower():
                new_info.append({
                    "text": f"参考: [{title}]({url})",
                    "source": "ddg",
                    "type": "reference",
                })

    return new_info[:10]  # 最多 10 条新信息


def compute_optimization_score(chapter: dict, research_data: dict) -> dict:
    """计算章节的优化优先级评分 — 基于六维度质量检测结果"""
    score = 0
    reasons = []
    quality_data = None

    # === 优先使用多维度质量系统 ===
    try:
        import check_quality as cq
        filepath = Path(chapter["path"])
        quality_data = cq.evaluate_chapter(filepath)
        overall = quality_data["overall"]["score"]
        grade = quality_data["overall"]["grade"]

        # 根据综合等级设定基础优化紧迫度
        if grade == "F":
            score += 50
            reasons.append(f"质量等级 F ({overall:.0f}分)，急需优化")
        elif grade == "D":
            score += 35
            reasons.append(f"质量等级 D ({overall:.0f}分)，需要优化")
        elif grade == "C":
            score += 20
            reasons.append(f"质量等级 C ({overall:.0f}分)，应改进")
        elif grade == "B":
            score += 10
            reasons.append(f"质量等级 B ({overall:.0f}分)，可微调")

        # 各维度低分加权
        dims = quality_data["dimensions"]
        dim_labels = {"content": "内容", "structure": "结构", "code": "代码",
                      "readability": "可读性", "pedagogy": "教学", "freshness": "时效"}
        for dim_name, dim_data in dims.items():
            ds = dim_data["score"]
            if ds < 60:
                score += 15
                reasons.append(f"{dim_labels.get(dim_name, dim_name)}维度严重不足 ({ds}分)")
            elif ds < 80:
                score += 5
                reasons.append(f"{dim_labels.get(dim_name, dim_name)}维度偏低 ({ds}分)")

    except Exception as e:
        # 回退到简单评分
        wc = chapter["word_count"]
        if wc < 500:
            score += 40
            reasons.append(f"字数严重不足 ({wc} < 500)")
        elif wc < 800:
            score += 20
            reasons.append(f"字数偏少 ({wc} < 800)")
        elif wc < 1200:
            score += 10
            reasons.append(f"字数可增加 ({wc} < 1200)")

        if chapter["code_blocks"] < 2:
            score += 15
            reasons.append(f"代码示例不足 ({chapter['code_blocks']} < 2)")

        h2_count = len([h for h in chapter["headings"] if h["level"] == 2])
        if h2_count < 3:
            score += 15
            reasons.append(f"小节数不足 ({h2_count} < 3)")

        if "本章小结" not in chapter["content"] and "小结" not in chapter["content"]:
            score += 10
            reasons.append("缺少本章小结")

    # 新信息可用 (始终检查)
    if research_data and research_data.get("findings"):
        new_info = extract_new_info(research_data, chapter["content"])
        if len(new_info) >= 3:
            score += 20
            reasons.append(f"发现 {len(new_info)} 条新信息可补充")
        elif len(new_info) >= 1:
            score += 10
            reasons.append(f"发现 {len(new_info)} 条新信息")

    # 文件较老
    try:
        mtime = datetime.fromtimestamp(os.path.getmtime(chapter["path"]))
        hours_old = (datetime.now() - mtime).total_seconds() / 3600
        if hours_old > 72:
            score += 10
            reasons.append(f"超过 {int(hours_old)}h 未更新")
    except Exception:
        pass

    return {"score": score, "reasons": reasons, "quality": quality_data}


def generate_optimization_prompt(chapter: dict, new_info: list) -> str:
    """构建给 write_chapter 的优化指令"""
    info_text = ""
    for idx, info in enumerate(new_info, 1):
        if info.get("type") == "reference":
            info_text += f"\n{idx}. {info['text']}"
        else:
            info_text += f"\n{idx}. {info['text'][:200]}"
            if info.get("novel_phrases"):
                info_text += f"\n   关键词: {', '.join(info['novel_phrases'][:3])}"

    prompt = f"""## 优化指令

请基于以下新收集的网络信息，优化和扩充本章内容。

### 当前状态
- 字数: {chapter['word_count']}
- 代码块: {chapter['code_blocks']}
- 小节数: {len([h for h in chapter['headings'] if h['level'] == 2])}

### 新收集的信息
{info_text}

### 优化要求
1. 保留原有结构和内容
2. 补充新发现的信息到合适的位置
3. 确保代码示例准确可运行
4. 如果有新命令或最佳实践，新增小节
5. 确保字数 >= 800
6. 保持中文教程的语气和风格
"""
    return prompt


def optimize_single_chapter(chapter_num: int, research_data: dict = None) -> dict:
    """优化单个章节"""
    chapter = read_chapter(chapter_num)
    if not chapter:
        return {"status": "skip", "reason": "chapter_not_found", "chapter": chapter_num}

    # 如果没有预加载的研究数据，执行搜索
    if not research_data:
        import web_researcher
        log.info(f"搜索第 {chapter_num} 章最新信息...")
        research_data = web_researcher.research_chapter(chapter_num)

    # 提取新信息
    new_info = extract_new_info(research_data, chapter["content"])

    if not new_info:
        log.info("无新信息可补充")
        return {"status": "no_update", "reason": "no_new_info", "chapter": chapter_num}

    # 构建优化后的内容
    log.info(f"发现 {len(new_info)} 条新信息，开始优化...")

    if DRY_RUN:
        log.info("[DRY RUN] 跳过实际写入")
        return {
            "status": "dry_run",
            "chapter": chapter_num,
            "new_info_count": len(new_info),
            "optimization_prompt": generate_optimization_prompt(chapter, new_info),
        }

    # 实际优化：使用 write_chapter 的知识库 + 网络新信息合并重写
    optimized_content = merge_new_content(chapter, new_info)

    if optimized_content and len(optimized_content) > len(chapter["content"]):
        # 备份原文件
        backup_path = chapter["path"] + ".bak"
        shutil.copy2(chapter["path"], backup_path)

        # 写入优化后内容
        Path(chapter["path"]).write_text(optimized_content, encoding="utf-8")

        new_wc = word_count(optimized_content)

        result = {
            "status": "optimized",
            "chapter": chapter_num,
            "file": chapter["file"],
            "before": {"word_count": chapter["word_count"], "char_count": chapter["char_count"]},
            "after": {"word_count": new_wc, "char_count": len(optimized_content)},
            "new_info_merged": len(new_info),
            "backup": backup_path,
        }
        log.info(f"优化完成: {chapter['word_count']} → {new_wc} 字")
        return result
    else:
        log.warning("优化内容未改进，保留原文")
        return {"status": "no_improvement", "chapter": chapter_num}


def merge_new_content(chapter: dict, new_info: list) -> str:
    """将新信息合并到现有章节内容中"""
    content = chapter["content"]
    lines = content.split("\n")

    # 策略: 在本章小结之前 (或文末) 插入"最新动态"小节
    insert_idx = len(lines)
    for i, line in enumerate(lines):
        if re.match(r'^##\s*(本章小结|小结|总结)', line):
            insert_idx = i
            break

    # 构建补充内容
    additions = []
    ref_additions = []
    content_additions = []

    for info in new_info:
        if info.get("type") == "reference":
            ref_additions.append(info["text"])
        else:
            text = info["text"]
            # 清理 Markdown 源的格式标记
            text = re.sub(r'^#+\s*', '', text)
            text = text.strip()
            if len(text) > 50:
                content_additions.append(text)

    new_section_lines = []

    # 添加内容补充
    if content_additions:
        new_section_lines.append("")
        new_section_lines.append("## 最新动态与补充")
        new_section_lines.append("")
        new_section_lines.append(f"> 📅 更新时间: {datetime.now().strftime('%Y-%m-%d')}")
        new_section_lines.append("")
        for idx, ca in enumerate(content_additions[:5], 1):
            # 截取有意义的部分
            clean = ca[:300].strip()
            if clean:
                new_section_lines.append(f"### 补充 {idx}")
                new_section_lines.append("")
                new_section_lines.append(clean)
                new_section_lines.append("")

    # 添加参考链接
    if ref_additions:
        new_section_lines.append("")
        new_section_lines.append("### 延伸阅读")
        new_section_lines.append("")
        for ref in ref_additions[:5]:
            new_section_lines.append(f"- {ref}")
        new_section_lines.append("")

    if new_section_lines:
        # 在合适位置插入
        result_lines = lines[:insert_idx] + new_section_lines + lines[insert_idx:]
        return "\n".join(result_lines)

    return content


def select_chapters_to_optimize(max_chapters: int = 3) -> list:
    """选择最需要优化的章节"""
    history = load_optimize_history()
    candidates = []

    for ch_num in range(1, 14):
        chapter = read_chapter(ch_num)
        if not chapter:
            continue

        # 检查冷却期
        if not can_optimize_chapter(ch_num, history):
            log.info(f"第 {ch_num} 章: 冷却中，跳过")
            continue

        research = load_research_data(ch_num)
        opt_score = compute_optimization_score(chapter, research)
        candidates.append({
            "chapter": ch_num,
            "score": opt_score["score"],
            "reasons": opt_score["reasons"],
            "word_count": chapter["word_count"],
        })

    # 按优化评分降序排列
    candidates.sort(key=lambda c: c["score"], reverse=True)

    # 过滤掉评分为 0 的
    candidates = [c for c in candidates if c["score"] > 0]

    return candidates[:max_chapters]


def run():
    import argparse
    parser = argparse.ArgumentParser(description="章节持续优化引擎")
    parser.add_argument("--chapter", type=int, default=0, help="指定优化章节 (0=自动选择)")
    parser.add_argument("--all", action="store_true", help="优化所有章节")
    parser.add_argument("--max-chapters", type=int, default=3, help="最多优化章节数")
    parser.add_argument("--dry-run", action="store_true", help="空运行")
    args = parser.parse_args()

    global DRY_RUN
    if args.dry_run:
        DRY_RUN = True

    max_chap = args.max_chapters
    if max_chap == 3:  # default
        max_chap = int(os.environ.get("MAX_OPTIMIZE_CHAPTERS", str(max_chap)))

    banner("章节持续优化引擎 — Optimizer", "🔄")
    log.info(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info(f"模式: {'空运行' if DRY_RUN else '实际优化'}")

    history = load_optimize_history()
    results = []

    if args.chapter > 0:
        # 优化指定章节
        chapters = [args.chapter]
    elif args.all:
        chapters = list(range(1, 14))
    else:
        # 自动选择
        candidates = select_chapters_to_optimize(max_chap)
        if not candidates:
            log.info("所有章节状态良好，无需优化")
            return {"status": "all_good", "optimized": 0}
        log.info(f"优化候选 ({len(candidates)} 章):")
        for c in candidates:
            log.info(f"  第 {c['chapter']:2d} 章 | 评分 {c['score']:3d} | {', '.join(c['reasons'][:2])}")
        chapters = [c["chapter"] for c in candidates]

    # 先进行搜索
    banner("阶段 1: 网络信息搜集", "🌐")
    import web_researcher
    for ch_num in chapters:
        log.info(f"第 {ch_num} 章: 搜索中...")
        web_researcher.research_chapter(ch_num)

    # 再进行优化
    banner("阶段 2: 章节优化", "📝")
    for ch_num in chapters:
        log.info(f"── 第 {ch_num} 章 ──")
        research = load_research_data(ch_num)
        result = optimize_single_chapter(ch_num, research)
        results.append(result)

        # 更新历史
        if result["status"] in ("optimized", "dry_run"):
            ch_key = str(ch_num)
            if ch_key not in history["stats"]["chapters_optimized"]:
                history["stats"]["chapters_optimized"][ch_key] = {"count": 0}
            history["stats"]["chapters_optimized"][ch_key]["count"] += 1
            history["stats"]["chapters_optimized"][ch_key]["last_optimized"] = datetime.now().isoformat()
            history["stats"]["total_optimizations"] += 1
            history["history"].append({
                "timestamp": datetime.now().isoformat(),
                "chapter": ch_num,
                "status": result["status"],
                "before_words": result.get("before", {}).get("word_count"),
                "after_words": result.get("after", {}).get("word_count"),
            })

        time.sleep(2)

    save_optimize_history(history)

    # Git 提交（如果有优化）
    optimized_count = len([r for r in results if r["status"] == "optimized"])
    if optimized_count > 0 and not DRY_RUN:
        banner("阶段 3: Git 提交", "📤")
        git_commit_optimization(results)

    # 汇总
    banner("优化汇总", "📊")
    log.info(f"总章节: {len(chapters)}")
    log.info(f"已优化: {optimized_count}")
    log.info(f"无更新: {len([r for r in results if r['status'] == 'no_update'])}")
    log.info(f"无改进: {len([r for r in results if r['status'] == 'no_improvement'])}")

    summary = {
        "timestamp": datetime.now().isoformat(),
        "optimized": optimized_count,
        "total_checked": len(chapters),
        "results": results,
    }

    save_json(os.path.join(OUTPUT_DIR, "optimize-result.json"), summary)

    return summary


def git_commit_optimization(results: list):
    """提交优化变更到 Git"""
    try:
        optimized = [r for r in results if r["status"] == "optimized"]
        if not optimized:
            return
        nums = [str(r["chapter"]) for r in optimized]
        msg = f"optimize: 基于网络最新信息优化第 {', '.join(nums)} 章 [{datetime.now().strftime('%Y-%m-%d %H:%M')}]"

        run_git(["add", "-A"], PROJECT_DIR)
        result = run_git(["commit", "-m", msg], PROJECT_DIR)
        if result["ok"]:
            log.info(f"已提交: {msg}")
            remote_name = get_git_remote_name()
            branch = cfg("git.branch", "main")
            push = run_git(["push", remote_name, branch], PROJECT_DIR)
            if push["ok"]:
                log.info("已推送到 GitHub")
            else:
                log.warning(f"推送失败: {push['stderr'][:100]}")
        else:
            log.info("无变更需提交")
    except Exception as e:
        log.error(f"Git 操作异常: {e}")


if __name__ == "__main__":
    run()
