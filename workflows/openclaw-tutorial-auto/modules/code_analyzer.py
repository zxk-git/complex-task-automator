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

from modules.compat import setup_logger, cfg, save_json

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
        "search_queries": ["{language} docstring best practices", "PEP 257 docstring conventions"],
        "static_references": [
            {"title": "PEP 257 – Docstring Conventions", "url": "https://peps.python.org/pep-0257/", "credibility": "A"},
            {"title": "Google Python Style Guide – Docstrings", "url": "https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings", "credibility": "A"}
        ],
    },
    "add_module_docstring": {
        "category": "documentation",
        "description": "为模块 {file} 添加 docstring",
        "estimated_impact": 2,
        "auto_fixable": True,
        "languages": ["python"],
        "search_queries": ["Python module docstring best practices"],
        "static_references": [
            {"title": "PEP 257 – Module Docstrings", "url": "https://peps.python.org/pep-0257/#multi-line-docstrings", "credibility": "A"}
        ],
    },
    "add_type_hints": {
        "category": "practices",
        "description": "为 {target} 添加类型注解 (覆盖率 {coverage}%)",
        "estimated_impact": 3,
        "auto_fixable": False,
        "languages": ["python"],
        "search_queries": ["Python type hints best practices", "PEP 484 type annotations"],
        "static_references": [
            {"title": "PEP 484 – Type Hints", "url": "https://peps.python.org/pep-0484/", "credibility": "A"},
            {"title": "mypy Documentation", "url": "https://mypy.readthedocs.io/en/stable/", "credibility": "A"}
        ],
    },
    "add_main_guard": {
        "category": "practices",
        "description": "{file} 添加 if __name__ == '__main__' 保护",
        "estimated_impact": 2,
        "auto_fixable": True,
        "languages": ["python"],
        "search_queries": ["Python if __name__ == __main__ best practices"],
        "static_references": [
            {"title": "Python Docs – __main__", "url": "https://docs.python.org/3/library/__main__.html", "credibility": "A"}
        ],
    },
    # ── JavaScript / TypeScript ──
    "add_jsdoc": {
        "category": "documentation",
        "description": "为 {target} 添加 JSDoc 注释",
        "estimated_impact": 3,
        "auto_fixable": True,
        "languages": ["javascript", "typescript"],
        "search_queries": ["JSDoc documentation best practices", "JavaScript documentation comments"],
        "static_references": [
            {"title": "JSDoc Official", "url": "https://jsdoc.app/", "credibility": "A"},
            {"title": "Google JS Style – JSDoc", "url": "https://google.github.io/styleguide/jsguide.html#jsdoc", "credibility": "A"}
        ],
    },
    "add_ts_types": {
        "category": "practices",
        "description": "{file} 缺少 TypeScript 类型定义 (interface/type)",
        "estimated_impact": 3,
        "auto_fixable": False,
        "languages": ["typescript"],
        "search_queries": ["TypeScript type definitions best practices"],
        "static_references": [
            {"title": "TypeScript Handbook – Everyday Types", "url": "https://www.typescriptlang.org/docs/handbook/2/everyday-types.html", "credibility": "A"}
        ],
    },
    "fix_module_consistency": {
        "category": "style",
        "description": "{file} 混合使用 ESM import 和 CJS require",
        "estimated_impact": 3,
        "auto_fixable": False,
        "languages": ["javascript", "typescript"],
        "search_queries": ["ESM vs CJS module consistency JavaScript"],
        "static_references": [
            {"title": "Node.js – ESM vs CJS", "url": "https://nodejs.org/api/esm.html", "credibility": "A"}
        ],
    },
    "add_strict_mode": {
        "category": "practices",
        "description": "{file} 添加 'use strict' 声明",
        "estimated_impact": 1,
        "auto_fixable": True,
        "languages": ["javascript"],
        "search_queries": ["JavaScript use strict best practices"],
        "static_references": [
            {"title": "MDN – Strict mode", "url": "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Strict_mode", "credibility": "A"}
        ],
    },
    # ── Go ──
    "add_go_doc": {
        "category": "documentation",
        "description": "为导出符号 {target} 添加文档注释",
        "estimated_impact": 3,
        "auto_fixable": True,
        "languages": ["go"],
        "search_queries": ["Go documentation comments best practices", "Effective Go documentation"],
        "static_references": [
            {"title": "Effective Go – Commentary", "url": "https://go.dev/doc/effective_go#commentary", "credibility": "A"},
            {"title": "Go Doc Comments", "url": "https://go.dev/doc/comment", "credibility": "A"}
        ],
    },
    "add_error_handling": {
        "category": "practices",
        "description": "{file} 缺少 error 处理 (if err != nil)",
        "estimated_impact": 4,
        "auto_fixable": False,
        "languages": ["go"],
        "search_queries": ["Go error handling best practices", "Go error wrapping"],
        "static_references": [
            {"title": "Effective Go – Errors", "url": "https://go.dev/doc/effective_go#errors", "credibility": "A"},
            {"title": "Go Blog – Error handling and Go", "url": "https://go.dev/blog/error-handling-and-go", "credibility": "A"}
        ],
    },
    "add_go_tests": {
        "category": "practices",
        "description": "{file} 缺少测试函数",
        "estimated_impact": 3,
        "auto_fixable": False,
        "languages": ["go"],
        "search_queries": ["Go testing best practices", "Go table driven tests"],
        "static_references": [
            {"title": "Go Testing Package", "url": "https://pkg.go.dev/testing", "credibility": "A"},
            {"title": "Go Wiki – Table Driven Tests", "url": "https://go.dev/wiki/TableDrivenTests", "credibility": "A"}
        ],
    },
    # ── Shell ──
    "add_set_e": {
        "category": "practices",
        "description": "{file} 添加 set -e (错误时退出)",
        "estimated_impact": 4,
        "auto_fixable": True,
        "languages": ["shell"],
        "search_queries": ["Bash set -e best practices", "Shell script error handling"],
        "static_references": [
            {"title": "Bash Manual – The Set Builtin", "url": "https://www.gnu.org/software/bash/manual/html_node/The-Set-Builtin.html", "credibility": "A"},
            {"title": "Google Shell Style Guide", "url": "https://google.github.io/styleguide/shellguide.html", "credibility": "A"}
        ],
    },
    "fix_backticks": {
        "category": "style",
        "description": "{file} 将反引号替换为 $(…)",
        "estimated_impact": 2,
        "auto_fixable": True,
        "languages": ["shell"],
        "search_queries": ["Shell backtick vs dollar paren substitution"],
        "static_references": [
            {"title": "ShellCheck SC2006", "url": "https://www.shellcheck.net/wiki/SC2006", "credibility": "A"}
        ],
    },
    "add_shebang": {
        "category": "practices",
        "description": "{file} 添加 shebang 行",
        "estimated_impact": 2,
        "auto_fixable": True,
        "languages": ["shell"],
        "search_queries": ["Shell script shebang best practices"],
        "static_references": [
            {"title": "Google Shell Style Guide – File Header", "url": "https://google.github.io/styleguide/shellguide.html#s1.1-which-shell-to-use", "credibility": "A"}
        ],
    },
    "quote_variables": {
        "category": "style",
        "description": "{file} 有约 {count} 处未引用的变量",
        "estimated_impact": 2,
        "auto_fixable": False,
        "languages": ["shell"],
        "search_queries": ["Bash variable quoting best practices"],
        "static_references": [
            {"title": "ShellCheck SC2086", "url": "https://www.shellcheck.net/wiki/SC2086", "credibility": "A"}
        ],
    },
    # ── Rust ──
    "add_rust_doc": {
        "category": "documentation",
        "description": "为公共项 {target} 添加 /// 文档注释",
        "estimated_impact": 3,
        "auto_fixable": True,
        "languages": ["rust"],
        "search_queries": ["Rust documentation comments best practices", "Rust doc comments"],
        "static_references": [
            {"title": "Rust Book – Doc Comments", "url": "https://doc.rust-lang.org/book/ch14-02-publishing-to-crates-io.html#making-useful-documentation-comments", "credibility": "A"},
            {"title": "Rust API Guidelines – Documentation", "url": "https://rust-lang.github.io/api-guidelines/documentation.html", "credibility": "A"}
        ],
    },
    "reduce_unsafe": {
        "category": "practices",
        "description": "{file} 有 {count} 个 unsafe 块，建议减少",
        "estimated_impact": 4,
        "auto_fixable": False,
        "languages": ["rust"],
        "search_queries": ["Rust unsafe code best practices", "Rust minimize unsafe"],
        "static_references": [
            {"title": "Rustonomicon – Unsafe", "url": "https://doc.rust-lang.org/nomicon/", "credibility": "A"},
            {"title": "Rust Book – Unsafe Rust", "url": "https://doc.rust-lang.org/book/ch19-01-unsafe-rust.html", "credibility": "A"}
        ],
    },
    # ── 通用 ──
    "reduce_complexity": {
        "category": "complexity",
        "description": "简化 {target} (CC={complexity})",
        "estimated_impact": 4,
        "auto_fixable": False,
        "languages": ["*"],
        "search_queries": ["{language} reduce cyclomatic complexity", "refactoring complex functions"],
        "static_references": [
            {"title": "Wikipedia – Cyclomatic Complexity", "url": "https://en.wikipedia.org/wiki/Cyclomatic_complexity", "credibility": "B"},
            {"title": "Refactoring.Guru – Extract Method", "url": "https://refactoring.guru/extract-method", "credibility": "A"}
        ],
    },
    "split_function": {
        "category": "structure",
        "description": "拆分 {target} ({lines} 行)",
        "estimated_impact": 4,
        "auto_fixable": False,
        "languages": ["*"],
        "search_queries": ["{language} split large function refactoring"],
        "static_references": [
            {"title": "Refactoring.Guru – Extract Method", "url": "https://refactoring.guru/extract-method", "credibility": "A"},
            {"title": "Clean Code – Functions", "url": "https://www.oreilly.com/library/view/clean-code-a/9780136083238/", "credibility": "A"}
        ],
    },
    "split_file": {
        "category": "structure",
        "description": "拆分模块 {file} ({loc} 行)",
        "estimated_impact": 5,
        "auto_fixable": False,
        "languages": ["*"],
        "search_queries": ["{language} split large file module organization"],
        "static_references": [
            {"title": "Refactoring.Guru – Extract Class", "url": "https://refactoring.guru/extract-class", "credibility": "A"}
        ],
    },
    "fix_naming": {
        "category": "style",
        "description": "修正 {target} 的命名约定",
        "estimated_impact": 1,
        "auto_fixable": True,
        "languages": ["*"],
        "search_queries": ["{language} naming conventions best practices"],
        "static_references": [
            {"title": "Wikipedia – Naming Convention (programming)", "url": "https://en.wikipedia.org/wiki/Naming_convention_(programming)", "credibility": "B"}
        ],
    },
    "remove_todos": {
        "category": "practices",
        "description": "处理 {file} 中 {count} 个 TODO/FIXME",
        "estimated_impact": 2,
        "auto_fixable": False,
        "languages": ["*"],
        "search_queries": ["managing TODO comments in code"],
        "static_references": [
            {"title": "Google Style – TODO Comments", "url": "https://google.github.io/styleguide/cppguide.html#TODO_Comments", "credibility": "A"}
        ],
    },
    "shorten_lines": {
        "category": "style",
        "description": "缩短 {file} 中 {count} 行超长行",
        "estimated_impact": 1,
        "auto_fixable": True,
        "languages": ["*"],
        "search_queries": ["{language} line length limit best practices"],
        "static_references": [
            {"title": "PEP 8 – Maximum Line Length", "url": "https://peps.python.org/pep-0008/#maximum-line-length", "credibility": "A"}
        ],
    },
    # ── C/C++ ──
    "add_doxygen": {
        "category": "documentation",
        "description": "为 {target} 添加 Doxygen 文档注释",
        "estimated_impact": 3,
        "auto_fixable": True,
        "languages": ["c", "cpp"],
        "search_queries": ["Doxygen documentation best practices C C++", "Doxygen comment style"],
        "static_references": [
            {"title": "Doxygen Manual", "url": "https://www.doxygen.nl/manual/docblocks.html", "credibility": "A"},
            {"title": "Google C++ Style – Comments", "url": "https://google.github.io/styleguide/cppguide.html#Comments", "credibility": "A"}
        ],
    },
    "add_header_guard": {
        "category": "practices",
        "description": "为头文件 {file} 添加 include guard",
        "estimated_impact": 4,
        "auto_fixable": True,
        "languages": ["c", "cpp"],
        "search_queries": ["C C++ include guard vs pragma once", "header guard best practices"],
        "static_references": [
            {"title": "Google C++ Style – #define Guard", "url": "https://google.github.io/styleguide/cppguide.html#The__define_Guard", "credibility": "A"},
            {"title": "cppreference – include guard", "url": "https://en.cppreference.com/w/cpp/preprocessor/include", "credibility": "A"}
        ],
    },
    "remove_goto": {
        "category": "practices",
        "description": "消除 {file} 中 {count} 处 goto 使用",
        "estimated_impact": 5,
        "auto_fixable": False,
        "languages": ["c", "cpp"],
        "search_queries": ["C goto alternatives structured programming"],
        "static_references": [
            {"title": "CERT C – Avoid goto", "url": "https://wiki.sei.cmu.edu/confluence/display/c/MEM12-C.+Consider+using+a+goto+chain+when+leaving+a+function+on+error+when+using+and+releasing+resources", "credibility": "A"}
        ],
    },
    "reduce_malloc": {
        "category": "practices",
        "description": "检查 {file} 中 {count} 处手动内存分配",
        "estimated_impact": 4,
        "auto_fixable": False,
        "languages": ["c", "cpp"],
        "search_queries": ["C memory management best practices", "safe malloc usage C"],
        "static_references": [
            {"title": "CERT C – Memory Management", "url": "https://wiki.sei.cmu.edu/confluence/display/c/MEM00-C.+Allocate+and+free+memory+in+the+same+module%2C+at+the+same+level+of+abstraction", "credibility": "A"}
        ],
    },
    # ── Java ──
    "add_javadoc": {
        "category": "documentation",
        "description": "为 {target} 添加 Javadoc",
        "estimated_impact": 3,
        "auto_fixable": True,
        "languages": ["java"],
        "search_queries": ["Java Javadoc best practices", "writing effective Javadoc"],
        "static_references": [
            {"title": "Oracle – Javadoc Guide", "url": "https://www.oracle.com/technical-resources/articles/java/javadoc-tool.html", "credibility": "A"},
            {"title": "Google Java Style – Javadoc", "url": "https://google.github.io/styleguide/javaguide.html#s7-javadoc", "credibility": "A"}
        ],
    },
    "add_class_javadoc": {
        "category": "documentation",
        "description": "为类 {target} 添加 Javadoc",
        "estimated_impact": 3,
        "auto_fixable": True,
        "languages": ["java"],
        "search_queries": ["Java class documentation best practices"],
        "static_references": [
            {"title": "Oracle – Javadoc Guide", "url": "https://www.oracle.com/technical-resources/articles/java/javadoc-tool.html", "credibility": "A"}
        ],
    },
    "add_exception_handling": {
        "category": "practices",
        "description": "为 {file} 添加异常处理",
        "estimated_impact": 4,
        "auto_fixable": False,
        "languages": ["java"],
        "search_queries": ["Java exception handling best practices", "Java try-catch patterns"],
        "static_references": [
            {"title": "Oracle – Lesson: Exceptions", "url": "https://docs.oracle.com/javase/tutorial/essential/exceptions/", "credibility": "A"},
            {"title": "Effective Java – Exceptions", "url": "https://www.oreilly.com/library/view/effective-java-3rd/9780134686097/", "credibility": "A"}
        ],
    },
    "add_override_annotation": {
        "category": "practices",
        "description": "为重写方法添加 @Override 注解",
        "estimated_impact": 2,
        "auto_fixable": True,
        "languages": ["java"],
        "search_queries": ["Java @Override annotation best practices"],
        "static_references": [
            {"title": "Oracle – @Override Annotation", "url": "https://docs.oracle.com/javase/tutorial/java/IandI/override.html", "credibility": "A"}
        ],
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

    # ── C/C++ 专项 ──
    elif lang in ("c", "cpp"):
        c_info = file_info.get("c_analysis", {})
        # Doxygen doc comments
        for fn in c_info.get("functions", []):
            if not fn.get("has_doc_comment"):
                improvements.append(_make_improvement(
                    "add_doxygen", target=f"{fname}::{fn['name']}()", line=fn["line"],
                ))
        # Header guard
        ext = file_info.get("extension", "")
        if ext in (".h", ".hpp", ".hxx") and not c_info.get("has_header_guard"):
            improvements.append(_make_improvement("add_header_guard", file=fname))
        # Goto
        if c_info.get("goto_count", 0) > 0:
            improvements.append(_make_improvement(
                "remove_goto", file=fname, count=c_info["goto_count"],
            ))
        # Malloc
        if c_info.get("malloc_count", 0) > 3:
            improvements.append(_make_improvement(
                "reduce_malloc", file=fname, count=c_info["malloc_count"],
            ))

    # ── Java 专项 ──
    elif lang == "java":
        jv = file_info.get("java_analysis", {})
        # Javadoc for public methods
        for m in jv.get("methods", []):
            if m.get("visibility") == "public" and not m.get("has_doc_comment"):
                improvements.append(_make_improvement(
                    "add_javadoc", target=f"{fname}::{m['name']}()", line=m["line"],
                ))
        # Class Javadoc
        for c in jv.get("classes", []):
            if not c.get("has_doc_comment"):
                improvements.append(_make_improvement(
                    "add_class_javadoc", target=c["name"], line=c["line"],
                ))
        # Exception handling
        if jv.get("exception_handling", 0) == 0 and len(jv.get("methods", [])) > 3:
            improvements.append(_make_improvement("add_exception_handling", file=fname))

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
