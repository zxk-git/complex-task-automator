"""
score_highlighter.py — 示例插件: 低分高亮标记
================================================
在扫描结果中为低分章节添加 `_low_score_alert` 标记，
供后续阶段或通知系统使用。

演示了插件开发的最小模式。
"""

PLUGIN_META = {
    "name": "score_highlighter",
    "version": "1.0.0",
    "description": "为低分章节/文件添加告警标记",
    "author": "openclaw",
    "hooks": ["after_scan"],
    "priority": 50,       # 优先于默认插件执行
}

# 阈值可通过环境变量覆盖
import os
THRESHOLD = int(os.environ.get("PLUGIN_SCORE_THRESHOLD", "65"))


def after_scan(scan_result: dict) -> dict:
    """扫描完成后，为低分项添加告警标记。"""
    if not scan_result or not isinstance(scan_result, dict):
        return scan_result

    chapters = scan_result.get("chapters", [])
    alerts = []

    for ch in chapters:
        score = ch.get("quality_score", 100)
        if score < THRESHOLD:
            ch["_low_score_alert"] = True
            alerts.append({
                "chapter": ch.get("number", "?"),
                "file": ch.get("file", "?"),
                "score": score,
                "threshold": THRESHOLD,
            })

    if alerts:
        scan_result.setdefault("_plugin_alerts", []).extend(alerts)

    return scan_result
