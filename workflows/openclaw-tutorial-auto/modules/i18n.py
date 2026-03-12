#!/usr/bin/env python3
"""
modules/i18n.py — 国际化 (i18n) 消息目录系统
================================================
为 Pipeline 报告、日志、Dashboard 提供多语言支持。

支持语言:
  - zh-CN (简体中文) — 默认
  - en (English)

用法:
  from modules.i18n import t, set_locale, get_locale

  set_locale("en")
  print(t("pipeline.banner.title"))  # → "Tutorial Auto-Optimization Pipeline"

  set_locale("zh-CN")
  print(t("pipeline.banner.title"))  # → "教程自动优化流水线"
"""

from typing import Any

_current_locale = "zh-CN"

# ── 消息目录 ──
_MESSAGES: dict[str, dict[str, str]] = {
    # ── Pipeline 通用 ──
    "pipeline.banner.title": {
        "zh-CN": "教程自动优化流水线",
        "en": "Tutorial Auto-Optimization Pipeline",
    },
    "pipeline.banner.project": {
        "zh-CN": "项目",
        "en": "Project",
    },
    "pipeline.banner.output": {
        "zh-CN": "输出",
        "en": "Output",
    },
    "pipeline.banner.stages": {
        "zh-CN": "阶段",
        "en": "Stages",
    },
    "pipeline.banner.mode": {
        "zh-CN": "模式",
        "en": "Mode",
    },
    "pipeline.stage.complete": {
        "zh-CN": "{stage} 完成",
        "en": "{stage} complete",
    },
    "pipeline.stage.failed": {
        "zh-CN": "{stage} 失败: {error}",
        "en": "{stage} failed: {error}",
    },
    "pipeline.stage.critical_abort": {
        "zh-CN": "关键阶段失败，中断流水线",
        "en": "Critical stage failed, aborting pipeline",
    },
    "pipeline.parallel.executing": {
        "zh-CN": "并行执行",
        "en": "Parallel execution",
    },
    "pipeline.done": {
        "zh-CN": "流水线完成: {ok}/{total} 阶段成功, 耗时 {duration:.1f}s",
        "en": "Pipeline done: {ok}/{total} stages succeeded, took {duration:.1f}s",
    },

    # ── 阶段名称 ──
    "stage.discover": {
        "zh-CN": "文档发现",
        "en": "Document Discovery",
    },
    "stage.scan": {
        "zh-CN": "质量扫描",
        "en": "Quality Scan",
    },
    "stage.analyze": {
        "zh-CN": "质量分析",
        "en": "Quality Analysis",
    },
    "stage.collect_refs": {
        "zh-CN": "参考收集",
        "en": "Reference Collection",
    },
    "stage.check_links": {
        "zh-CN": "断链检测",
        "en": "Link Check",
    },
    "stage.check_consistency": {
        "zh-CN": "一致性检测",
        "en": "Consistency Check",
    },
    "stage.check_readability": {
        "zh-CN": "可读性分析",
        "en": "Readability Analysis",
    },
    "stage.llm_expand": {
        "zh-CN": "LLM 扩写分析",
        "en": "LLM Expansion Analysis",
    },
    "stage.refine": {
        "zh-CN": "内容精炼",
        "en": "Content Refinement",
    },
    "stage.fix_issues": {
        "zh-CN": "自动修复",
        "en": "Auto Fix",
    },
    "stage.format": {
        "zh-CN": "格式统一",
        "en": "Format Normalization",
    },
    "stage.track": {
        "zh-CN": "优化追踪",
        "en": "Optimization Tracking",
    },
    "stage.update_readme": {
        "zh-CN": "README 更新",
        "en": "README Update",
    },
    "stage.git": {
        "zh-CN": "Git 提交",
        "en": "Git Commit",
    },
    "stage.report": {
        "zh-CN": "报告生成",
        "en": "Report Generation",
    },
    "stage.html_report": {
        "zh-CN": "HTML 报告生成",
        "en": "HTML Report Generation",
    },

    # ── 报告 ──
    "report.title": {
        "zh-CN": "📚 教程自动优化报告",
        "en": "📚 Tutorial Auto-Optimization Report",
    },
    "report.time": {
        "zh-CN": "时间",
        "en": "Time",
    },
    "report.duration": {
        "zh-CN": "耗时",
        "en": "Duration",
    },
    "report.seconds": {
        "zh-CN": "秒",
        "en": "seconds",
    },
    "report.overview": {
        "zh-CN": "总体概览",
        "en": "Overview",
    },
    "report.score_dashboard": {
        "zh-CN": "章节评分仪表板",
        "en": "Chapter Score Dashboard",
    },
    "report.chapter": {
        "zh-CN": "章节",
        "en": "Chapter",
    },
    "report.score": {
        "zh-CN": "分数",
        "en": "Score",
    },
    "report.grade": {
        "zh-CN": "等级",
        "en": "Grade",
    },
    "report.defects": {
        "zh-CN": "缺陷",
        "en": "Defects",
    },
    "report.words": {
        "zh-CN": "字数",
        "en": "Words",
    },
    "report.yes": {
        "zh-CN": "是",
        "en": "Yes",
    },
    "report.no": {
        "zh-CN": "否",
        "en": "No",
    },

    # ── 扩写分析 ──
    "expand.analyzing": {
        "zh-CN": "扩写分析: {need}/{total} 章节需要扩写",
        "en": "Expansion analysis: {need}/{total} chapters need expansion",
    },
    "expand.total_suggestions": {
        "zh-CN": "总建议数: {count}",
        "en": "Total suggestions: {count}",
    },

    # ── 通用 ──
    "common.metric": {
        "zh-CN": "指标",
        "en": "Metric",
    },
    "common.value": {
        "zh-CN": "值",
        "en": "Value",
    },
}

# ── 支持的语言列表 ──
SUPPORTED_LOCALES = ("zh-CN", "en")


def set_locale(locale: str) -> None:
    """设置当前语言。"""
    global _current_locale
    if locale in SUPPORTED_LOCALES:
        _current_locale = locale
    else:
        # 尝试匹配前缀 (如 "zh" → "zh-CN")
        for supported in SUPPORTED_LOCALES:
            if supported.startswith(locale):
                _current_locale = supported
                return
        raise ValueError(f"Unsupported locale: {locale}. Supported: {SUPPORTED_LOCALES}")


def get_locale() -> str:
    """获取当前语言。"""
    return _current_locale


def t(key: str, **kwargs: Any) -> str:
    """翻译消息键。

    Args:
        key: 消息键 (如 "pipeline.banner.title")
        **kwargs: 格式化参数

    Returns:
        翻译后的字符串。如果键不存在，返回键本身。
    """
    messages = _MESSAGES.get(key)
    if not messages:
        return key

    text = messages.get(_current_locale)
    if text is None:
        # 回退到 zh-CN
        text = messages.get("zh-CN", key)

    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass

    return text


def get_stage_name(stage: str) -> str:
    """获取阶段的本地化名称。"""
    return t(f"stage.{stage}")


def register_messages(new_messages: dict[str, dict[str, str]]) -> None:
    """注册额外的消息条目 (供插件使用)。"""
    _MESSAGES.update(new_messages)
