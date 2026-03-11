"""
types.py — 核心数据类型定义
============================
为所有模块间传递的数据结构提供 TypedDict 定义，
确保类型安全和 IDE 补全。

用法:
    from modules.types import ChapterScanResult, ChapterAnalysis, RefineResult
"""
from __future__ import annotations

from typing import List, Optional
try:
    from typing import TypedDict
except ImportError:
    from typing_extensions import TypedDict  # Python 3.7 兼容


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 教程类型
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class HeadingDetail(TypedDict):
    level: int
    line: int
    text: str


class ScoreDetail(TypedDict, total=False):
    total: float
    content_depth: float
    structure: float
    code_quality: float
    pedagogy: float
    references: float
    readability: float
    grade: str


class Defect(TypedDict, total=False):
    type: str
    severity: str       # critical / major / minor
    line: int
    text: str
    message: str
    section: str
    word_count: int
    count: int
    length: int


class H2SectionSummary(TypedDict):
    title: str
    word_count: int
    line: int


class StructureInfo(TypedDict, total=False):
    h1: int
    h2: int
    h3: int
    h4: int
    h5: int
    h6: int
    has_toc: bool
    has_nav: bool
    heading_jumps: List[str]
    headings_detail: List[HeadingDetail]


class ContentInfo(TypedDict, total=False):
    code_blocks: int
    code_languages: List[str]
    unlabeled_code_blocks: int
    tables: int
    images: int
    links_internal: int
    links_external: int
    has_faq: bool
    has_summary: bool
    has_references: bool
    has_cli_examples: bool
    blockquotes: int


class ChapterScanResult(TypedDict, total=False):
    """tutorial_scanner.scan_chapter 的返回类型"""
    file: str
    number: int
    title: str
    word_count: int
    line_count: int
    last_modified: str
    structure: StructureInfo
    content: ContentInfo
    h2_sections: List[H2SectionSummary]
    defects: List[Defect]
    quality_score: float
    score_detail: ScoreDetail


class Improvement(TypedDict, total=False):
    type: str
    priority: str       # high / medium / low
    target: str
    description: str
    current: str
    suggestion: str
    estimated_impact: int


class ChapterAnalysis(TypedDict, total=False):
    """quality_analyzer.analyze_chapter 的返回类型"""
    chapter: int
    file: str
    title: str
    current_score: float
    target_score: float
    priority: str
    improvements: List[Improvement]
    missing_sections: List[str]
    weak_sections: List[str]


class RefineResult(TypedDict, total=False):
    """tutorial_refiner.refine_chapter 的返回类型"""
    chapter: int
    file: str
    status: str         # refined / no_change / file_not_found
    changes_applied: List[str]
    words_before: int
    words_after: int
    change_count: int


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 代码类型
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class CodeScoreDetail(TypedDict, total=False):
    total: float
    structure: float
    documentation: float
    complexity: float
    style: float
    practices: float
    grade: str


class CodeFileScanResult(TypedDict, total=False):
    """code_scanner.scan_file 的返回类型"""
    file: str
    relative_path: str
    language: str
    line_count: int
    function_count: int
    class_count: int
    defects: List[Defect]
    quality_score: float
    score_detail: CodeScoreDetail
    analysis: dict          # 语言特定分析数据


class CodeImprovement(TypedDict, total=False):
    """code_analyzer 生成的优化建议"""
    type: str
    priority: str
    description: str
    target: str
    estimated_impact: int
    auto_fixable: bool
    language: str
    references: List[dict]


class CodeRefineResult(TypedDict, total=False):
    """code_refiner.refine_file 的返回类型"""
    file: str
    status: str         # refined / no_change / error
    changes: List[str]
    original_lines: int
    final_lines: int


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Pipeline 类型
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class StageResult(TypedDict, total=False):
    status: str         # ok / error / skipped
    data: dict
    error: str
    duration: float


class PipelineResult(TypedDict, total=False):
    """Pipeline.run() 的返回类型"""
    version: str
    mode: str
    dry_run: bool
    stages_ok: int
    stages_failed: int
    duration: float
    stage_results: dict     # {stage_name: StageResult}
    summary: dict


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Diff / 通知 / AI 类型
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class DiffResult(TypedDict, total=False):
    total_changed: int
    files: List[dict]
    summary: dict


class NotifyResult(TypedDict, total=False):
    ok: bool
    results: dict       # {channel_name: bool}


class AIRefineResult(TypedDict, total=False):
    ok: bool
    original_length: int
    refined_length: int
    delta: int
    error: str
