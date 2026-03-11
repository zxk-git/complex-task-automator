#!/usr/bin/env python3
"""
code_analyzer.py — 代码质量分析器
====================================
基于扫描报告生成优化建议，按优先级排序。
支持 Python 专项和通用代码分析。

输出: {OUTPUT_DIR}/code-analysis-report.json
"""

from collections import defaultdict
import json
import os
import re
import sys

_SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

try:
    from utils import setup_logger, cfg, save_json
except ImportError:
    import logging
    def setup_logger(name):
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
        return logging.getLogger(name)
    def cfg(key, default=None):
        return os.environ.get(key.replace(".", "_").upper(), default)
    def save_json(path, data):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

log = setup_logger("code_analyzer")

# ── 优化建议模板 ──
IMPROVEMENT_TEMPLATES = {
    # ── Python ──
    "add_docstring": {
        "category": "documentation",
        "description": "为 {target} 添加 docstring",
        "estimated_impact": 3,
        "auto_fixable": True,
        "languages": ["python"],
    },
    "add_module_docstring": {
        "category": "documentation",
        "description": "为模块 {file} 添加 docstring",
        "estimated_impact": 2,
        "auto_fixable": True,
        "languages": ["python"],
    },
    "add_type_hints": {
        "category": "practices",
        "description": "为 {target} 添加类型注解 (覆盖率 {coverage}%)",
        "estimated_impact": 3,
        "auto_fixable": False,
        "languages": ["python"],
    },
    "add_main_guard": {
        "category": "practices",
        "description": "{file} 添加 if __name__ == '__main__' 保护",
        "estimated_impact": 2,
        "auto_fixable": True,
        "languages": ["python"],
    },
    # ── JavaScript / TypeScript ──
    "add_jsdoc": {
        "category": "documentation",
        "description": "为 {target} 添加 JSDoc 注释",
        "estimated_impact": 3,
        "auto_fixable": True,
        "languages": ["javascript", "typescript"],
    },
    "add_ts_types": {
        "category": "practices",
        "description": "{file} 缺少 TypeScript 类型定义 (interface/type)",
        "estimated_impact": 3,
        "auto_fixable": False,
        "languages": ["typescript"],
    },
    "fix_module_consistency": {
        "category": "style",
        "description": "{file} 混合使用 ESM import 和 CJS require",
        "estimated_impact": 3,
        "auto_fixable": False,
        "languages": ["javascript", "typescript"],
    },
    "add_strict_mode": {
        "category": "practices",
        "description": "{file} 添加 'use strict' 声明",
        "estimated_impact": 1,
        "auto_fixable": True,
        "languages": ["javascript"],
    },
    # ── Go ──
    "add_go_doc": {
        "category": "documentation",
        "description": "为导出符号 {target} 添加文档注释",
        "estimated_impact": 3,
        "auto_fixable": True,
        "languages": ["go"],
    },
    "add_error_handling": {
        "category": "practices",
        "description": "{file} 缺少 error 处理 (if err != nil)",
        "estimated_impact": 4,
        "auto_fixable": False,
        "languages": ["go"],
    },
    "add_go_tests": {
        "category": "practices",
        "description": "{file} 缺少测试函数",
        "estimated_impact": 3,
        "auto_fixable": False,
        "languages": ["go"],
    },
    # ── Shell ──
    "add_set_e": {
        "category": "practices",
        "description": "{file} 添加 set -e (错误时退出)",
        "estimated_impact": 4,
        "auto_fixable": True,
        "languages": ["shell"],
    },
    "fix_backticks": {
        "category": "style",
        "description": "{file} 将反引号替换为 $(…)",
        "estimated_impact": 2,
        "auto_fixable": True,
        "languages": ["shell"],
    },
    "add_shebang": {
        "category": "practices",
        "description": "{file} 添加 shebang 行",
        "estimated_impact": 2,
        "auto_fixable": True,
        "languages": ["shell"],
    },
    "quote_variables": {
        "category": "style",
        "description": "{file} 有约 {count} 处未引用的变量",
        "estimated_impact": 2,
        "auto_fixable": False,
        "languages": ["shell"],
    },
    # ── Rust ──
    "add_rust_doc": {
        "category": "documentation",
        "description": "为公共项 {target} 添加 /// 文档注释",
        "estimated_impact": 3,
        "auto_fixable": True,
        "languages": ["rust"],
    },
    "reduce_unsafe": {
        "category": "practices",
        "description": "{file} 有 {count} 个 unsafe 块，建议减少",
        "estimated_impact": 4,
        "auto_fixable": False,
        "languages": ["rust"],
    },
    # ── 通用 ──
    "reduce_complexity": {
        "category": "complexity",
        "description": "简化 {target} (CC={complexity})",
        "estimated_impact": 4,
        "auto_fixable": False,
        "languages": ["*"],
    },
    "split_function": {
        "category": "structure",
        "description": "拆分 {target} ({lines} 行)",
        "estimated_impact": 4,
        "auto_fixable": False,
        "languages": ["*"],
    },
    "split_file": {
        "category": "structure",
        "description": "拆分模块 {file} ({loc} 行)",
        "estimated_impact": 5,
        "auto_fixable": False,
        "languages": ["*"],
    },
    "fix_naming": {
        "category": "style",
        "description": "修正 {target} 的命名约定",
        "estimated_impact": 1,
        "auto_fixable": True,
        "languages": ["*"],
    },
    "remove_todos": {
        "category": "practices",
        "description": "处理 {file} 中 {count} 个 TODO/FIXME",
        "estimated_impact": 2,
        "auto_fixable": False,
        "languages": ["*"],
    },
    "shorten_lines": {
        "category": "style",
        "description": "缩短 {file} 中 {count} 行超长行",
        "estimated_impact": 1,
        "auto_fixable": True,
        "languages": ["*"],
    },
}


def analyze_file(file_info: dict) -> list:
    """分析单个文件，生成优化建议列表。"""
    improvements = []
    lang = file_info.get("language", "")
    py = file_info.get("python_analysis", {})
    js = file_info.get("js_analysis", {})
    go = file_info.get("go_analysis", {})
    sh = file_info.get("shell_analysis", {})
    rs = file_info.get("rust_analysis", {})
    generic = file_info.get("generic_analysis", {})
    fname = file_info.get("relative_path", file_info.get("file", "?"))

    # ── Python 专项 ──
    if lang == "python":
        if not py.get("docstring") and file_info.get("line_count", 0) > 20:
            improvements.append(_make_improvement("add_module_docstring", file=fname))

        for f in py.get("functions", []):
            if not f.get("is_private") and not f.get("has_docstring"):
                improvements.append(_make_improvement(
                    "add_docstring", target=f"{fname}::{f['name']}()", line=f["line"],
                ))

        hint_cov = py.get("type_hint_coverage", 0)
        if hint_cov < 0.5 and len(py.get("functions", [])) > 0:
            improvements.append(_make_improvement(
                "add_type_hints", target=fname, coverage=round(hint_cov * 100),
            ))

        for f in py.get("functions", []):
            cc = f.get("complexity", 0)
            if cc > 10:
                improvements.append(_make_improvement(
                    "reduce_complexity", target=f"{fname}::{f['name']}()",
                    complexity=cc, line=f["line"],
                ))

        for f in py.get("functions", []):
            if f.get("line_count", 0) > 50:
                improvements.append(_make_improvement(
                    "split_function", target=f"{fname}::{f['name']}()",
                    lines=f["line_count"], line=f["line"],
                ))

        if (py.get("functions") and not py.get("has_main_guard")
                and file_info.get("line_count", 0) > 30):
            improvements.append(_make_improvement("add_main_guard", file=fname))

    # ── JavaScript / TypeScript 专项 ──
    elif lang in ("javascript", "typescript"):
        # JSDoc 覆盖
        funcs = js.get("functions", [])
        jsdoc_count = js.get("jsdoc_count", 0)
        if funcs and jsdoc_count < len(funcs) * 0.5:
            for f in funcs[:5]:
                if f.get("type") != "method":
                    improvements.append(_make_improvement(
                        "add_jsdoc", target=f"{fname}::{f['name']}()", line=f["line"],
                    ))

        # TypeScript 类型
        if lang == "typescript":
            types = len(js.get("interfaces", [])) + len(js.get("type_aliases", []))
            if types == 0 and file_info.get("line_count", 0) > 50:
                improvements.append(_make_improvement("add_ts_types", file=fname))

        # Module consistency
        if js.get("module_type") == "mixed":
            improvements.append(_make_improvement("fix_module_consistency", file=fname))

        # Strict mode (CJS only)
        if (lang == "javascript" and not js.get("has_strict_mode")
                and js.get("module_type") == "cjs"):
            improvements.append(_make_improvement("add_strict_mode", file=fname))

        # Complexity
        cc = js.get("complexity_estimate", 0)
        if cc > 15:
            improvements.append(_make_improvement(
                "reduce_complexity", target=fname, complexity=cc,
            ))

    # ── Go 专项 ──
    elif lang == "go":
        # 导出函数文档注释
        exported = [f for f in go.get("functions", []) if f.get("is_exported")]
        exported += [m for m in go.get("methods", []) if m.get("is_exported")]
        for f in exported:
            if not f.get("has_doc_comment"):
                improvements.append(_make_improvement(
                    "add_go_doc", target=f"{fname}::{f['name']}()", line=f["line"],
                ))
        # 导出类型文档
        for s in go.get("structs", []):
            if s.get("is_exported") and not s.get("has_doc_comment"):
                improvements.append(_make_improvement(
                    "add_go_doc", target=f"{fname}::{s['name']}", line=s["line"],
                ))

        # Error handling
        funcs_count = len(go.get("functions", [])) + len(go.get("methods", []))
        if funcs_count > 3 and go.get("error_checks", 0) == 0:
            improvements.append(_make_improvement("add_error_handling", file=fname))

        # Tests
        if not go.get("test_functions") and not fname.endswith("_test.go"):
            improvements.append(_make_improvement("add_go_tests", file=fname))

    # ── Shell 专项 ──
    elif lang == "shell":
        if not sh.get("uses_set_e"):
            improvements.append(_make_improvement("add_set_e", file=fname))
        if sh.get("uses_backticks"):
            improvements.append(_make_improvement("fix_backticks", file=fname))
        if not sh.get("shebang"):
            improvements.append(_make_improvement("add_shebang", file=fname))
        uq = sh.get("unquoted_vars", 0)
        if uq > 3:
            improvements.append(_make_improvement(
                "quote_variables", file=fname, count=uq,
            ))

    # ── Rust 专项 ──
    elif lang == "rust":
        # 公共项文档
        for f in rs.get("functions", []):
            if f.get("is_public") and not f.get("has_doc_comment"):
                improvements.append(_make_improvement(
                    "add_rust_doc", target=f"{fname}::{f['name']}()", line=f["line"],
                ))
        for s in rs.get("structs", []):
            if s.get("is_public") and not s.get("has_doc_comment"):
                improvements.append(_make_improvement(
                    "add_rust_doc", target=f"{fname}::{s['name']}", line=s["line"],
                ))
        # Unsafe
        if rs.get("unsafe_blocks", 0) > 2:
            improvements.append(_make_improvement(
                "reduce_unsafe", file=fname, count=rs["unsafe_blocks"],
            ))

    # ── 通用 ──
    if file_info.get("line_count", 0) > 500:
        improvements.append(_make_improvement(
            "split_file", file=fname, loc=file_info["line_count"]
        ))

    todos = generic.get("todo_count", 0)
    if todos > 0:
        improvements.append(_make_improvement(
            "remove_todos", file=fname, count=todos
        ))

    long = generic.get("long_lines", 0)
    if long > 3:
        improvements.append(_make_improvement(
            "shorten_lines", file=fname, count=long
        ))

    return improvements


def _make_improvement(template_key: str, **kwargs) -> dict:
    """根据模板创建优化建议。"""
    tmpl = IMPROVEMENT_TEMPLATES.get(template_key, {})
    desc = tmpl.get("description", template_key)
    try:
        desc = desc.format(**kwargs)
    except KeyError:
        pass

    return {
        "type": template_key,
        "category": tmpl.get("category", "other"),
        "description": desc,
        "estimated_impact": tmpl.get("estimated_impact", 1),
        "auto_fixable": tmpl.get("auto_fixable", False),
        "file": kwargs.get("file", kwargs.get("target", "")),
        "line": kwargs.get("line"),
    }


def analyze_all(scan_report: dict) -> dict:
    """分析整个扫描报告，生成优先级排列的优化队列。"""
    if not scan_report:
        log.warning("无扫描数据")
        return {"optimization_queue": [], "total_improvements": 0}

    all_improvements = []
    file_analyses = []

    for f in scan_report.get("files", []):
        if "error" in f:
            continue

        improvements = analyze_file(f)
        file_analyses.append({
            "file": f.get("relative_path", f.get("file", "?")),
            "score": f.get("quality_score", 0),
            "grade": f.get("score_detail", {}).get("grade", "?"),
            "improvements": len(improvements),
            "defects": len(f.get("defects", [])),
        })

        for imp in improvements:
            imp["file_score"] = f.get("quality_score", 0)
            all_improvements.append(imp)

    # 按优先级排序: 低分文件优先, 高影响优先
    all_improvements.sort(
        key=lambda x: (-x.get("estimated_impact", 0), x.get("file_score", 100))
    )

    # 按文件分组的优化队列
    file_queue = sorted(file_analyses, key=lambda x: x.get("score", 100))

    # 分类统计
    by_category = defaultdict(int)
    for imp in all_improvements:
        by_category[imp["category"]] += 1

    # 自动修复比例
    auto_fixable = sum(1 for i in all_improvements if i.get("auto_fixable"))

    # 优先级分布
    priority_dist = {"high": 0, "medium": 0, "low": 0}
    for fa in file_analyses:
        score = fa.get("score", 100)
        if score < 50:
            priority_dist["high"] += 1
        elif score < 75:
            priority_dist["medium"] += 1
        else:
            priority_dist["low"] += 1

    report = {
        "total_files": len(file_analyses),
        "total_improvements": len(all_improvements),
        "auto_fixable": auto_fixable,
        "auto_fixable_ratio": round(auto_fixable / max(len(all_improvements), 1), 2),
        "by_category": dict(by_category),
        "priority_distribution": priority_dist,
        "optimization_queue": file_queue,
        "improvements": all_improvements,
        "recommendations": _generate_recommendations(
            file_analyses, all_improvements, scan_report
        ),
    }

    log.info(f"  分析完成: {len(all_improvements)} 项优化建议, "
             f"{auto_fixable} 项可自动修复")
    return report


def _generate_recommendations(files: list, improvements: list,
                              scan_report: dict) -> list:
    """生成高级建议。"""
    recs = []

    # 整体得分建议
    avg_score = scan_report.get("average_score", 0)
    if avg_score < 50:
        recs.append({
            "priority": "high",
            "description": f"代码整体质量偏低 (平均 {avg_score}分)，建议全面重构",
        })
    elif avg_score < 75:
        recs.append({
            "priority": "medium",
            "description": f"代码质量中等 ({avg_score}分)，建议优先处理高影响项",
        })

    # 文档建议
    doc_issues = sum(1 for i in improvements if i["category"] == "documentation")
    if doc_issues > 5:
        recs.append({
            "priority": "medium",
            "description": f"文档缺失较多 ({doc_issues} 项)，建议统一补充 docstring",
        })

    # 复杂度建议
    cc_issues = [i for i in improvements if i["category"] == "complexity"]
    if cc_issues:
        recs.append({
            "priority": "high",
            "description": f"存在 {len(cc_issues)} 个高复杂度函数，建议优先简化",
        })

    # 结构建议
    large_files = [f for f in files if f.get("score", 100) < 40]
    if large_files:
        recs.append({
            "priority": "high",
            "description": f"{len(large_files)} 个文件质量低于 40 分，建议重构",
        })

    return recs


def run():
    """主入口。"""
    output_dir = cfg("output_dir", "/tmp/openclaw-code-reports")
    scan_path = os.path.join(output_dir, "code-scan-report.json")
    if not os.path.exists(scan_path):
        log.error(f"扫描报告不存在: {scan_path}")
        return

    with open(scan_path) as f:
        scan_report = json.load(f)

    report = analyze_all(scan_report)
    out_path = os.path.join(output_dir, "code-analysis-report.json")
    save_json(out_path, report)
    log.info(f"分析报告已保存: {out_path}")
    return report


if __name__ == "__main__":
    run()
