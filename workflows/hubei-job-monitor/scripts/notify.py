#!/usr/bin/env python3
"""
湖北招聘监控 — 飞书推送
将新发现的硕士岗位推送到飞书群，通过 OpenClaw delivery-queue 机制。
"""
import sys
import uuid
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import cfg, get_output_dir, setup_logger, save_json, load_json, now_iso

log = setup_logger("notify")

DELIVERY_QUEUE_DIR = Path.home() / ".openclaw" / "delivery-queue"


def format_message(items: list) -> str:
    """格式化飞书推送消息（含 Excel 岗位详情）"""
    if not items:
        return ""

    # 统计 Excel 岗位总数
    total_excel = sum(len(item.get("excel_jobs", [])) for item in items)

    lines = [f"📋 **湖北招聘硕士岗位监控** — {now_iso()[:10]}\n"]
    if total_excel > 0:
        lines.append(f"发现 **{len(items)}** 条新公告，含 **{total_excel}** 个硕士岗位\n")
    else:
        lines.append(f"发现 **{len(items)}** 条新岗位\n")

    # 按数据源分组
    by_source = {}
    for item in items:
        src = item.get("source_name", item.get("source_id", "未知"))
        by_source.setdefault(src, []).append(item)

    for source, source_items in by_source.items():
        lines.append(f"\n🏢 **{source}** ({len(source_items)} 条)\n")

        for i, item in enumerate(source_items, 1):
            title = item["title"]
            url = item.get("url", "")
            date = item.get("date", "")
            date_str = f" ({date})" if date else ""

            if url:
                lines.append(f"**{i}. [{title}]({url}){date_str}**")
            else:
                lines.append(f"**{i}. {title}{date_str}**")

            # 如果有 Excel 解析的岗位信息，展示详情
            excel_jobs = item.get("excel_jobs", [])
            if excel_jobs:
                # 按招聘单位分组（优先使用 employer_display）
                by_employer = {}
                for job in excel_jobs:
                    emp = job.get("employer_display", "") or job.get("employer", "未知单位")
                    by_employer.setdefault(emp, []).append(job)

                show_limit = cfg("notify.max_jobs_per_announcement", 10)
                shown = 0

                for emp, emp_jobs in by_employer.items():
                    if shown >= show_limit:
                        remaining = sum(len(v) for v in list(by_employer.values())[list(by_employer.keys()).index(emp):])
                        lines.append(f"  ... 还有 {remaining} 个岗位")
                        break

                    # 显示单位名称
                    display_emp = emp

                    lines.append(f"  📍 **{display_emp}** ({len(emp_jobs)} 个岗位)")
                    for job in emp_jobs[:max(3, show_limit - shown)]:
                        pos = job.get("position", "—")
                        edu = job.get("education", "")
                        num = job.get("headcount", "")
                        major = job.get("major", "")

                        detail_parts = []
                        if num:
                            detail_parts.append(f"{num}人")
                        if edu:
                            detail_parts.append(edu)
                        if major:
                            if len(major) > 30:
                                major = major[:30] + "..."
                            detail_parts.append(major)

                        detail = " · ".join(detail_parts)
                        lines.append(f"    - {pos}" + (f" [{detail}]" if detail else ""))
                        shown += 1

                    if len(emp_jobs) > max(3, show_limit - shown):
                        lines.append(f"    - ... 等 {len(emp_jobs)} 个岗位")

                lines.append("")

    lines.append(f"---\n🤖 自动监控 · 每日 05:00 更新")
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

    # 移除 None 值
    delivery = {k: v for k, v in delivery.items() if v is not None}

    out_path = DELIVERY_QUEUE_DIR / f"{delivery['id']}.json"
    save_json(out_path, delivery)
    log.info("已投递到 delivery-queue: %s", delivery["id"])
    return True


def run():
    out_dir = get_output_dir()
    dedup_file = Path(out_dir) / "dedup-result.json"
    dedup_data = load_json(dedup_file, {"items": []})

    items = dedup_data.get("items", [])
    max_items = cfg("notify.max_items_per_push", 20)

    if not items:
        log.info("无新岗位需要推送")
        notify_empty = cfg("notify.notify_empty", False)
        if notify_empty:
            msg = f"📋 **湖北招聘硕士岗位监控** — {now_iso()[:10]}\n\n今日未发现新的硕士岗位信息。\n\n🤖 自动监控 · 每日 05:00 更新"
            deliver_to_feishu(msg)

        save_json(Path(out_dir) / "notify-result.json", {
            "timestamp": now_iso(),
            "pushed": False,
            "reason": "no_new_items",
            "item_count": 0,
        })
        return

    # 限制推送数量
    push_items = items[:max_items]
    overflow = len(items) - max_items if len(items) > max_items else 0

    message = format_message(push_items)
    if overflow > 0:
        message += f"\n\n⚠️ 还有 {overflow} 条未显示，请查看完整报告。"

    success = deliver_to_feishu(message)

    save_json(Path(out_dir) / "notify-result.json", {
        "timestamp": now_iso(),
        "pushed": success,
        "item_count": len(push_items),
        "overflow": overflow,
        "delivery_queue": str(DELIVERY_QUEUE_DIR),
    })
    log.info("推送完成: %d 条岗位%s", len(push_items), f" (+{overflow} 未显示)" if overflow else "")


if __name__ == "__main__":
    run()
