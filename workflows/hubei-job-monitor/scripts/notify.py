#!/usr/bin/env python3
"""
湖北招聘监控 — 飞书推送
推送工科硕士岗位详情 + 相关公告摘要。
"""
import re
import sys
import uuid
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import cfg, get_output_dir, setup_logger, save_json, load_json, now_iso

log = setup_logger("notify")

DELIVERY_QUEUE_DIR = Path.home() / ".openclaw" / "delivery-queue"


def clean_major(major: str) -> str:
    """去掉专业名称中的数字代码"""
    if not major:
        return ""
    cleaned = re.sub(r'\b\d{2,6}', '', major)
    cleaned = re.sub(r'[，,]\s*[，,]', '，', cleaned)
    return cleaned.strip('，, ')


def format_job_line(job: dict) -> str:
    """格式化单个岗位为一行（完整版）"""
    pos = job.get("position", "—")
    emp = job.get("employer_display", "") or job.get("employer", "")
    num = job.get("headcount", "")
    edu = job.get("education", "")
    major = clean_major(job.get("major", ""))

    parts = []
    if emp:
        parts.append(f"**{emp}**")
    parts.append(pos)

    detail_parts = []
    if num:
        detail_parts.append(f"{num}人")
    if edu:
        detail_parts.append(edu)
    if major:
        if len(major) > 30:
            major = major[:30] + "..."
        detail_parts.append(major)

    if detail_parts:
        return f"{'｜'.join(parts)} [{' · '.join(detail_parts)}]"
    return "｜".join(parts)


def format_job_line_short(job: dict) -> str:
    """格式化单个岗位（紧凑版，省略单位名）"""
    pos = job.get("position", "—")
    num = job.get("headcount", "")
    edu = job.get("education", "")
    major = clean_major(job.get("major", ""))

    detail_parts = []
    if num:
        detail_parts.append(f"{num}人")
    if edu:
        detail_parts.append(edu)
    if major:
        if len(major) > 35:
            major = major[:35] + "..."
        detail_parts.append(major)

    if detail_parts:
        return f"{pos} [{' · '.join(detail_parts)}]"
    return pos


def format_message(dedup_data: dict) -> str:
    """格式化推送消息：按招聘单位分组展示工科岗位 + 公告摘要"""
    items = dedup_data.get("items", [])
    matched_jobs = dedup_data.get("matched_jobs", [])

    lines = [f"📋 **湖北硕士岗位监控（工科）** — {now_iso()[:10]}\n"]

    # ── 岗位详情区：按招聘单位分组 ──
    if matched_jobs:
        # 按单位分组
        by_employer = {}
        for job in matched_jobs:
            emp = job.get("employer_display", "") or job.get("employer", "未知单位")
            by_employer.setdefault(emp, []).append(job)

        lines.append(f"🔧 **工科匹配岗位：{len(matched_jobs)} 个（{len(by_employer)} 个单位）**\n")

        # 按来源公告分组（用于输出公告标题链接）
        by_announcement = {}
        for job in matched_jobs:
            ann = job.get("_announcement_title", "")
            if ann and ann not in by_announcement:
                by_announcement[ann] = {
                    "url": job.get("_announcement_url", ""),
                    "date": job.get("_announcement_date", ""),
                }

        # 输出公告链接
        for ann_title, ann_info in by_announcement.items():
            short_title = ann_title[:50] + ("..." if len(ann_title) > 50 else "")
            if ann_info["url"]:
                lines.append(f"📢 [{short_title}]({ann_info['url']})" +
                             (f" ({ann_info['date']})" if ann_info["date"] else ""))
            else:
                lines.append(f"📢 {short_title}")

        # 按单位岗位数降序排列
        sorted_employers = sorted(by_employer.items(), key=lambda x: -len(x[1]))
        max_employers = cfg("notify.max_employers", 15)
        max_jobs_per = cfg("notify.max_jobs_per_employer", 5)
        total_shown = 0
        max_total = cfg("notify.max_jobs_total", 60)
        employers_shown = 0

        for emp_name, emp_jobs in sorted_employers:
            if employers_shown >= max_employers or total_shown >= max_total:
                break
            employers_shown += 1

            lines.append(f"\n🏢 **{emp_name}** ({len(emp_jobs)}个)")
            for job in emp_jobs[:max_jobs_per]:
                if total_shown >= max_total:
                    break
                lines.append(f"  • {format_job_line_short(job)}")
                total_shown += 1
            if len(emp_jobs) > max_jobs_per:
                lines.append(f"  • ...等{len(emp_jobs)}个岗位")

        # 未展示的单位统计
        remaining_employers = len(sorted_employers) - employers_shown
        remaining_jobs = len(matched_jobs) - total_shown
        if remaining_employers > 0:
            lines.append(f"\n📊 还有 {remaining_employers} 个单位共 {remaining_jobs} 个岗位")

    # ── 公告摘要区（无 Excel 数据的公告）──
    no_excel_items = [it for it in items if not it.get("excel_jobs")]
    if no_excel_items:
        lines.append(f"\n📄 **其他相关公告：{len(no_excel_items)} 条**\n")
        for i, item in enumerate(no_excel_items[:10], 1):
            title = item["title"]
            url = item.get("url", "")
            date = item.get("date", "")
            src = item.get("source_name", "")
            date_str = f" ({date})" if date else ""
            src_str = f" [{src}]" if src else ""

            if url:
                lines.append(f"  {i}. [{title}]({url}){date_str}{src_str}")
            else:
                lines.append(f"  {i}. {title}{date_str}{src_str}")

    lines.append(f"\n---\n🤖 自动监控 · 每日 05:00 更新")
    return "\n".join(lines)


def deliver_to_feishu(message: str) -> bool:
    """通过 OpenClaw delivery-queue 投递消息到飞书"""
    channel = cfg("notify.channel", "feishu")
    chat_id = cfg("notify.chat_id", "")
    account = cfg("notify.account", "default")

    if not chat_id:
        log.error("未配置 notify.chat_id，无法推送")
        return False

    DELIVERY_QUEUE_DIR.mkdir(parents=True, exist_ok=True)

    delivery = {
        "id": str(uuid.uuid4()),
        "enqueuedAt": int(time.time() * 1000),
        "channel": channel,
        "to": chat_id,
        "accountId": account if account != "default" else None,
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

    delivery = {k: v for k, v in delivery.items() if v is not None}

    out_path = DELIVERY_QUEUE_DIR / f"{delivery['id']}.json"
    save_json(out_path, delivery)
    log.info("已投递到 delivery-queue: %s", delivery["id"])
    return True


def run():
    out_dir = get_output_dir()
    dedup_file = Path(out_dir) / "dedup-result.json"
    dedup_data = load_json(dedup_file, {"items": [], "matched_jobs": []})

    items = dedup_data.get("items", [])
    matched_jobs = dedup_data.get("matched_jobs", [])

    if not items and not matched_jobs:
        log.info("无新岗位需要推送")
        notify_empty = cfg("notify.notify_empty", False)
        if notify_empty:
            msg = f"📋 **湖北硕士岗位监控（工科）** — {now_iso()[:10]}\n\n今日未发现新的工科硕士岗位信息。\n\n🤖 自动监控 · 每日 05:00 更新"
            deliver_to_feishu(msg)

        save_json(Path(out_dir) / "notify-result.json", {
            "timestamp": now_iso(),
            "pushed": False,
            "reason": "no_new_items",
            "item_count": 0,
            "matched_jobs_count": 0,
        })
        return

    message = format_message(dedup_data)

    success = deliver_to_feishu(message)

    save_json(Path(out_dir) / "notify-result.json", {
        "timestamp": now_iso(),
        "pushed": success,
        "item_count": len(items),
        "matched_jobs_count": len(matched_jobs),
        "delivery_queue": str(DELIVERY_QUEUE_DIR),
    })
    log.info("推送完成: %d 条公告, %d 个工科岗位", len(items), len(matched_jobs))


if __name__ == "__main__":
    run()
