#!/usr/bin/env python3
"""
health_check.py — 24/7 健康检查与状态追踪
功能：
  - 检测项目进度（已完成/剩余章节）
  - 检查批量运行状态（最近运行、失败记录）
  - 磁盘与环境健康
  - 生成可读状态报告（适合飞书推送）
  - 异常预警（连续失败、长时间无进展）
"""
import os
import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import (
    get_project_dir,
    get_output_dir,
    get_expected_chapters,
    parse_outline,
    find_completed_chapters,
    check_disk_health,
    load_json,
    save_json,
    setup_logger,
    get_encoding,
    cfg,
    banner,
)

log = setup_logger("health_check")

# ═══════════════════════════════════════════════════════
# 常量 — 从 utils/config 获取，环境变量可覆盖
# ═══════════════════════════════════════════════════════

PROJECT_DIR = get_project_dir()
OUTPUT_DIR = get_output_dir()
EXPECTED_CHAPTERS = get_expected_chapters()

MAX_HOURS_NO_PROGRESS = int(
    os.environ.get("MAX_HOURS_NO_PROGRESS", cfg("health.max_hours_no_progress", 24))
)
MAX_CONSECUTIVE_FAILURES = int(
    os.environ.get("MAX_CONSECUTIVE_FAILURES", cfg("health.max_consecutive_failures", 3))
)


# ═══════════════════════════════════════════════════════
# 环境健康检查（本地独有逻辑，保留）
# ═══════════════════════════════════════════════════════

def check_env_health() -> dict:
    """检查运行环境"""
    issues = []

    # Python
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

    # 项目目录
    if not Path(PROJECT_DIR).is_dir():
        issues.append("项目目录不存在")

    # 输出目录
    if not Path(OUTPUT_DIR).is_dir():
        issues.append("输出目录不存在（将自动创建）")

    # 大纲文件
    if not (Path(PROJECT_DIR) / "OUTLINE.md").is_file():
        issues.append("OUTLINE.md 不存在")

    return {
        "python_version": py_ver,
        "project_dir_exists": Path(PROJECT_DIR).is_dir(),
        "output_dir_exists": Path(OUTPUT_DIR).is_dir(),
        "issues": issues,
        "healthy": len(issues) == 0,
    }


# ═══════════════════════════════════════════════════════
# 预警分析
# ═══════════════════════════════════════════════════════

def analyze_alerts(chapters, batch_state) -> list:
    """生成预警信息"""
    alerts = []
    now = datetime.now()

    # 检查长时间无进展
    if batch_state and batch_state.get("last_run_at"):
        try:
            last_run = datetime.fromisoformat(batch_state["last_run_at"])
            hours_since = (now - last_run).total_seconds() / 3600
            if hours_since > MAX_HOURS_NO_PROGRESS:
                alerts.append({
                    "level": "warning",
                    "message": f"已超过 {int(hours_since)} 小时无新运行",
                    "detail": f"上次运行: {batch_state['last_run_at']}",
                })
        except Exception:
            pass

    # 检查连续失败
    if batch_state and batch_state.get("runs"):
        last_run = batch_state["runs"][-1]
        failed = last_run.get("chapters_failed", [])
        if len(failed) >= MAX_CONSECUTIVE_FAILURES:
            alerts.append({
                "level": "error",
                "message": f"上次运行连续失败 {len(failed)} 章",
                "detail": f"失败章节: {failed}",
            })

    # 检查失败历史
    if batch_state:
        total_failures = len(batch_state.get("failed_chapters", []))
        if total_failures > 5:
            alerts.append({
                "level": "warning",
                "message": f"累计失败 {total_failures} 次",
                "detail": "建议检查日志排查问题",
            })

    return alerts


# ═══════════════════════════════════════════════════════
# 状态报告生成
# ═══════════════════════════════════════════════════════

def generate_status_report(progress, chapters, outline, batch_state, disk, env, alerts) -> str:
    """生成可读状态报告（Markdown 格式，适合飞书推送）"""
    lines = []
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 标题
    lines.append("# 📊 教程自动化健康报告")
    lines.append(f"\n> 生成时间: {now_str}")

    # 进度条
    pct = progress["percentage"]
    filled = int(pct / 5)
    bar = "█" * filled + "░" * (20 - filled)
    lines.append(f"\n## 📈 项目进度")
    lines.append(f"\n`[{bar}]` **{pct}%** ({progress['completed']}/{progress['total']})")

    # 已完成章节
    if chapters:
        lines.append(f"\n### ✅ 已完成章节 ({len(chapters)})")
        for ch in chapters:
            size_kb = round(ch["size_bytes"] / 1024, 1)
            lines.append(f"- 第{ch['number']}章: {ch['file']} ({size_kb}KB)")

    # 待完成章节
    completed_nums = {ch["number"] for ch in chapters}
    missing = [o for o in outline if o["number"] not in completed_nums]
    if missing:
        lines.append(f"\n### 📝 待生成章节 ({len(missing)})")
        for m in missing:
            lines.append(f"- 第{m['number']}章: {m['title']}")

    # 批量运行状态
    if batch_state:
        lines.append(f"\n## 🔄 批量运行状态")
        lines.append(f"- 总运行次数: {batch_state.get('total_runs', 0)}")
        lines.append(f"- 上次运行: {batch_state.get('last_run_at', 'N/A')}")
        if batch_state.get("runs"):
            last = batch_state["runs"][-1]
            lines.append(f"- 上次成功: {len(last.get('chapters_succeeded', []))} 章")
            lines.append(f"- 上次失败: {len(last.get('chapters_failed', []))} 章")
            lines.append(f"- 上次耗时: {last.get('total_duration', 0):.1f}s")

    # 预警
    if alerts:
        lines.append(f"\n## ⚠️ 预警 ({len(alerts)})")
        for a in alerts:
            icon = "🔴" if a["level"] == "error" else "🟡"
            lines.append(f"- {icon} **{a['message']}**")
            if a.get("detail"):
                lines.append(f"  - {a['detail']}")
    else:
        lines.append(f"\n## ✅ 无预警")

    # 系统健康
    lines.append(f"\n## 🖥️ 系统状态")
    lines.append(f"- 磁盘: {disk['free_gb']}GB 可用 / {disk['total_gb']}GB 总量 ({disk['usage_percent']}%)")
    lines.append(f"- Python: {env['python_version']}")
    if env["issues"]:
        for issue in env["issues"]:
            lines.append(f"- ⚠️ {issue}")

    # 下一步建议
    lines.append(f"\n## 📋 下一步")
    if not missing:
        lines.append("- 🎉 **所有章节已全部完成！**可进行最终校对和发布。")
    elif alerts and any(a["level"] == "error" for a in alerts):
        lines.append("- 🔧 存在错误预警，建议先排查问题再继续生成。")
    else:
        next_ch = missing[0]
        lines.append(f"- 继续生成: 第{next_ch['number']}章《{next_ch['title']}》")
        lines.append(f"- 剩余工作量: {len(missing)} 章")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════

def run():
    banner("健康检查 — Health Check", "🏥")

    # 收集数据
    outline = parse_outline(PROJECT_DIR)
    chapters = find_completed_chapters(PROJECT_DIR)
    batch_state = load_json(Path(OUTPUT_DIR) / "batch-state.json")
    disk = check_disk_health()
    env = check_env_health()

    total = len(outline) or EXPECTED_CHAPTERS
    progress = {
        "completed": len(chapters),
        "total": total,
        "remaining": total - len(chapters),
        "percentage": round(len(chapters) / total * 100, 1),
    }

    alerts = analyze_alerts(chapters, batch_state)

    # 生成报告
    report = generate_status_report(
        progress, chapters, outline, batch_state, disk, env, alerts
    )

    # 输出 JSON 结果
    result = {
        "timestamp": datetime.now().isoformat(),
        "progress": progress,
        "chapters": chapters,
        "batch_state_summary": {
            "total_runs": batch_state.get("total_runs", 0) if batch_state else 0,
            "last_run_at": batch_state.get("last_run_at") if batch_state else None,
        },
        "disk": disk,
        "env": env,
        "alerts": alerts,
        "alert_count": len(alerts),
        "overall_healthy": len([a for a in alerts if a["level"] == "error"]) == 0,
        "all_complete": progress["remaining"] == 0,
    }

    # 保存
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    save_json(Path(OUTPUT_DIR) / "health-check.json", result)
    (Path(OUTPUT_DIR) / "health-report.md").write_text(report, encoding=get_encoding())

    log.info("健康检查完成 — 进度 %s/%s (%s%%), 预警 %d 条",
             progress["completed"], progress["total"],
             progress["percentage"], len(alerts))
    log.info("报告已保存: %s", Path(OUTPUT_DIR) / "health-report.md")

    print(report)
    print()
    print("─" * 50)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run()
