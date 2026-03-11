#!/usr/bin/env python3
"""
feishu_notify.py — 优化报告飞书推送
读取优化结果 JSON，生成详细的 Markdown 报告，通过 OpenClaw delivery-queue 推送到飞书
"""
import json
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from utils import (
    get_output_dir,
    get_project_dir,
    load_json,
    save_json,
    setup_logger,
    cfg,
    find_completed_chapters,
)

log = setup_logger("feishu_notify")

DELIVERY_QUEUE_DIR = Path.home() / ".openclaw" / "delivery-queue"
FEISHU_CHAT_ID = cfg("feishu.chat_id", "chat:oc_d618ee5b611928489deeccc66535a1e6")
FEISHU_ACCOUNT = cfg("feishu.account", "default")


def load_optimize_result() -> dict:
    """加载优化结果"""
    return load_json(
        Path(get_output_dir()) / "optimize-result.json",
        default={},
    )


def load_daemon_result() -> dict:
    """加载 daemon 调度器结果"""
    return load_json(
        Path(get_output_dir()) / "daemon-result.json",
        default={},
    )


def load_git_result() -> dict:
    """加载 Git 推送结果"""
    return load_json(
        Path(get_output_dir()) / "git-result.json",
        default={},
    )


def load_research_summary() -> dict:
    """加载网络搜索摘要"""
    return load_json(
        Path(get_output_dir()) / "web-research-summary.json",
        default={},
    )


def format_report() -> str:
    """生成详细的优化报告 (Markdown 格式)"""
    opt = load_optimize_result()
    daemon = load_daemon_result()
    git = load_git_result()
    research = load_research_summary()

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = []

    # ── 标题 ──
    lines.append(f"📚 **OpenClaw 教程持续优化报告**")
    lines.append(f"🕐 {now}")
    lines.append("")

    # ── 优化结果 ──
    optimized = opt.get("optimized", 0)
    total_checked = opt.get("total_checked", 0)
    results = opt.get("results", [])

    if optimized > 0:
        lines.append(f"✅ **已优化 {optimized}/{total_checked} 个章节**")
        lines.append("")
        for r in results:
            ch = r.get("chapter", "?")
            status = r.get("status", "?")
            if status == "optimized":
                before = r.get("before", {}).get("word_count", "?")
                after = r.get("after", {}).get("word_count", "?")
                file_name = r.get("file", f"第{ch}章")
                delta = int(after) - int(before) if isinstance(after, int) and isinstance(before, int) else 0
                delta_str = f"+{delta}" if delta > 0 else str(delta)
                lines.append(f"  📝 **第{ch}章** {file_name}")
                lines.append(f"     字数: {before} → {after} ({delta_str})")
                merged = r.get("new_info_merged", 0)
                if merged:
                    lines.append(f"     新增信息: {merged} 条")
                lines.append("")
    elif total_checked > 0:
        lines.append(f"ℹ️ 检查了 {total_checked} 个章节，本轮无需优化")
        # 详细原因
        for r in results:
            ch = r.get("chapter", "?")
            status = r.get("status", "?")
            reason = r.get("reason", "")
            if status == "no_update":
                lines.append(f"  第{ch}章: 无新信息")
            elif status == "no_improvement":
                lines.append(f"  第{ch}章: 内容已最优")
        lines.append("")
    else:
        lines.append("ℹ️ 所有章节状态良好，无需优化")
        lines.append("")

    # ── 搜索引擎使用情况 ──
    if research:
        chapters_researched = research.get("total_chapters_researched", 0)
        if chapters_researched > 0:
            all_engines = set()
            for ch_key, ch_data in research.get("chapters", {}).items():
                r_data = ch_data.get("research", {})
                all_engines.update(r_data.get("engines_used", []))
            if all_engines:
                lines.append(f"🔍 **搜索引擎**: {', '.join(sorted(all_engines))}")
                lines.append(f"   搜索章节: {chapters_researched}")
                lines.append("")

    # ── Git 推送状态 ──
    git_summary = git.get("summary", {})
    if git_summary:
        committed = git_summary.get("committed", False)
        changes = git_summary.get("changes", 0)
        if committed:
            lines.append(f"📤 **Git**: 已提交并推送 ({changes} 个文件)")
            # 查找 commit hash
            for step in git.get("steps", []):
                if step.get("step") == "commit" and step.get("hash"):
                    lines.append(f"   Commit: `{step['hash']}`")
                    break
        elif changes > 0:
            lines.append(f"📤 **Git**: {changes} 个文件变更（未提交）")
        else:
            lines.append(f"📤 **Git**: 无变更")
        lines.append("")

    # ── 调度器耗时 ──
    duration = daemon.get("duration", 0)
    if duration:
        lines.append(f"⏱️ 耗时: {duration:.1f}s")

    # ── 项目总体进度 ──
    chapters = find_completed_chapters(get_project_dir())
    total_size = sum(c["size_bytes"] for c in chapters)
    lines.append(f"📊 教程总计: {len(chapters)} 章 / {total_size / 1024:.0f} KB")
    lines.append("")

    # ── 下次运行 ──
    lines.append("📅 下次自动优化: ~4小时后")
    lines.append("---")
    lines.append("🤖 *OpenClaw 24/7 教程自动化*")

    return "\n".join(lines)


def deliver_to_feishu(message: str) -> bool:
    """通过 OpenClaw delivery-queue 投递消息到飞书"""
    if not FEISHU_CHAT_ID:
        log.error("未配置飞书 chat_id")
        return False

    DELIVERY_QUEUE_DIR.mkdir(parents=True, exist_ok=True)

    delivery = {
        "id": str(uuid.uuid4()),
        "enqueuedAt": int(time.time() * 1000),
        "channel": "feishu",
        "to": FEISHU_CHAT_ID,
        "payloads": [
            {
                "text": message,
                "replyToTag": False,
                "replyToCurrent": False,
                "audioAsVoice": False,
            }
        ],
        "gifPlayback": False,
        "silent": False,
        "retryCount": 0,
    }

    # 如果指定了 account 且不是 default
    if FEISHU_ACCOUNT and FEISHU_ACCOUNT != "default":
        delivery["accountId"] = FEISHU_ACCOUNT

    out_path = DELIVERY_QUEUE_DIR / f"{delivery['id']}.json"
    save_json(out_path, delivery)
    log.info("已投递到 delivery-queue: %s", delivery["id"])
    return True


def run():
    """生成报告并推送到飞书"""
    log.info("生成优化报告...")
    report = format_report()

    log.info("报告内容:\n%s", report)

    # 保存报告副本
    report_file = Path(get_output_dir()) / "feishu-optimize-report.md"
    report_file.write_text(report, encoding="utf-8")
    log.info("报告已保存: %s", report_file)

    # 推送到飞书
    success = deliver_to_feishu(report)
    if success:
        log.info("✅ 飞书推送成功")
    else:
        log.error("❌ 飞书推送失败")

    return {"ok": success, "report": report}


if __name__ == "__main__":
    run()
