#!/usr/bin/env python3
"""
湖北招聘监控 — 飞书推送
自适应输出：
  - 少量岗位（<= inline_threshold）：直接推送详情
  - 大量岗位：生成 Markdown 云文档推送到 GitHub，飞书推送摘要 + 链接
"""
import re
import sys
import uuid
import time
import subprocess
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import cfg, get_output_dir, setup_logger, save_json, load_json, now_iso

log = setup_logger("notify")

DELIVERY_QUEUE_DIR = Path.home() / ".openclaw" / "delivery-queue"
SKILL_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = SKILL_ROOT / "reports"
GITHUB_REPO_URL = "https://github.com/zxk-git/complex-task-automator"


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


# ── Markdown 报告生成 ──────────────────────────────

def generate_report_md(dedup_data: dict) -> str:
    """生成完整 Markdown 岗位报告（不截断，全部岗位）"""
    items = dedup_data.get("items", [])
    matched_jobs = dedup_data.get("matched_jobs", [])
    today = now_iso()[:10]

    lines = [
        f"# 📋 湖北硕士岗位监控（工科）— {today}\n",
        f"> 自动生成 · {now_iso()[:19]}\n",
    ]

    if matched_jobs:
        # 按单位分组
        by_employer = {}
        for job in matched_jobs:
            emp = job.get("employer_display", "") or job.get("employer", "未知单位")
            by_employer.setdefault(emp, []).append(job)

        lines.append(f"## 🔧 工科匹配岗位：{len(matched_jobs)} 个（{len(by_employer)} 个单位）\n")

        # 公告链接
        by_announcement = {}
        for job in matched_jobs:
            ann = job.get("_announcement_title", "")
            if ann and ann not in by_announcement:
                by_announcement[ann] = {
                    "url": job.get("_announcement_url", ""),
                    "date": job.get("_announcement_date", ""),
                }

        if by_announcement:
            lines.append("**来源公告：**\n")
            for ann_title, ann_info in by_announcement.items():
                if ann_info["url"]:
                    lines.append(f"- [{ann_title}]({ann_info['url']})" +
                                 (f" ({ann_info['date']})" if ann_info["date"] else ""))
                else:
                    lines.append(f"- {ann_title}")
            lines.append("")

        # 按单位岗位数降序，完整输出
        sorted_employers = sorted(by_employer.items(), key=lambda x: -len(x[1]))
        for emp_name, emp_jobs in sorted_employers:
            lines.append(f"### 🏢 {emp_name}（{len(emp_jobs)}个）\n")
            lines.append("| 岗位 | 人数 | 学历 | 专业要求 |")
            lines.append("|------|------|------|----------|")
            for job in emp_jobs:
                pos = job.get("position", "—")
                num = job.get("headcount", "—")
                edu = job.get("education", "—")
                major = clean_major(job.get("major", "—"))
                lines.append(f"| {pos} | {num} | {edu} | {major} |")
            lines.append("")

    # 其他公告
    no_excel_items = [it for it in items if not it.get("excel_jobs")]
    if no_excel_items:
        lines.append(f"## 📄 其他相关公告（{len(no_excel_items)} 条）\n")
        for i, item in enumerate(no_excel_items, 1):
            title = item["title"]
            url = item.get("url", "")
            date = item.get("date", "")
            src = item.get("source_name", "")
            date_str = f" ({date})" if date else ""
            src_str = f" — {src}" if src else ""
            if url:
                lines.append(f"{i}. [{title}]({url}){date_str}{src_str}")
            else:
                lines.append(f"{i}. {title}{date_str}{src_str}")
        lines.append("")

    lines.append("---\n*🤖 自动监控 · 每日 05:00 更新*\n")
    return "\n".join(lines)


def push_report_to_github(md_content: str, filename: str) -> str | None:
    """
    将 Markdown 报告推送到 GitHub，返回浏览 URL。
    文件存放在 workflows/hubei-job-monitor/reports/ 目录。
    """
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / filename

    report_path.write_text(md_content, encoding="utf-8")
    log.info("报告已生成: %s", report_path)

    try:
        subprocess.run(
            ["git", "add", str(report_path)],
            cwd=str(SKILL_ROOT), check=True, capture_output=True, timeout=15
        )
        result = subprocess.run(
            ["git", "commit", "-m", f"report: 工科岗位日报 {filename}"],
            cwd=str(SKILL_ROOT), check=True, capture_output=True, timeout=15
        )
        push_result = subprocess.run(
            ["git", "push", "origin", "master"],
            cwd=str(SKILL_ROOT), check=True, capture_output=True, timeout=30
        )
        log.info("报告已推送到 GitHub")

        # 构造浏览 URL — 需要相对 git 仓库根目录
        try:
            git_root = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=str(SKILL_ROOT), capture_output=True, text=True, check=True
            ).stdout.strip()
            rel_path = report_path.relative_to(git_root)
        except Exception:
            rel_path = report_path.relative_to(SKILL_ROOT)
        url = f"{GITHUB_REPO_URL}/blob/master/{rel_path}"
        return url

    except subprocess.CalledProcessError as e:
        log.error("Git 推送失败: %s", e.stderr.decode().rstrip() if e.stderr else str(e))
        # 返回本地路径作为备选
        return None
    except Exception as e:
        log.error("推送异常: %s", e)
        return None


def format_summary_with_link(dedup_data: dict, report_url: str) -> str:
    """格式化简短摘要消息（附云文档链接）"""
    matched_jobs = dedup_data.get("matched_jobs", [])
    items = dedup_data.get("items", [])
    today = now_iso()[:10]

    by_employer = {}
    for job in matched_jobs:
        emp = job.get("employer_display", "") or job.get("employer", "未知")
        by_employer.setdefault(emp, []).append(job)

    sorted_employers = sorted(by_employer.items(), key=lambda x: -len(x[1]))
    top5 = sorted_employers[:5]

    lines = [
        f"📋 **湖北硕士岗位监控（工科）** — {today}\n",
        f"🔧 **新增工科岗位：{len(matched_jobs)} 个（{len(by_employer)} 个单位）**\n",
        "**岗位最多的单位：**",
    ]
    for emp_name, emp_jobs in top5:
        lines.append(f"  • {emp_name}（{len(emp_jobs)}个）")

    if len(sorted_employers) > 5:
        lines.append(f"  • ... 等 {len(sorted_employers)} 个单位")

    no_excel = [it for it in items if not it.get("excel_jobs")]
    if no_excel:
        lines.append(f"\n📄 其他相关公告：{len(no_excel)} 条")

    lines.append(f"\n📄 **完整岗位详情（含专业要求）：**")
    lines.append(f"👉 [{today} 工科岗位报告]({report_url})")
    lines.append(f"\n---\n🤖 自动监控 · 每日 05:00 更新")
    return "\n".join(lines)


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

    # ── 自适应输出模式选择 ──
    inline_threshold = cfg("notify.inline_threshold", 15)
    mode = "inline" if len(matched_jobs) <= inline_threshold else "report"
    log.info("输出模式: %s (matched_jobs=%d, threshold=%d)", mode, len(matched_jobs), inline_threshold)

    report_url = None
    if mode == "inline":
        # 少量岗位：直接推送详情
        message = format_message(dedup_data)
    else:
        # 大量岗位：生成 Markdown 报告 + 推送到 GitHub
        today = now_iso()[:10]
        filename = f"{today}.md"
        md_content = generate_report_md(dedup_data)
        report_url = push_report_to_github(md_content, filename)

        if report_url:
            message = format_summary_with_link(dedup_data, report_url)
        else:
            # GitHub 推送失败，降级为内联模式
            log.warning("云文档推送失败，降级为内联模式")
            message = format_message(dedup_data)

    success = deliver_to_feishu(message)

    save_json(Path(out_dir) / "notify-result.json", {
        "timestamp": now_iso(),
        "pushed": success,
        "mode": mode,
        "item_count": len(items),
        "matched_jobs_count": len(matched_jobs),
        "report_url": report_url,
        "delivery_queue": str(DELIVERY_QUEUE_DIR),
    })
    log.info("推送完成: %d 条公告, %d 个工科岗位 [mode=%s]", len(items), len(matched_jobs), mode)


if __name__ == "__main__":
    run()
