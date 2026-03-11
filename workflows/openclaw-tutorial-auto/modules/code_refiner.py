#!/usr/bin/env python3
"""
code_refiner.py — 代码自动优化器
===================================
基于分析报告，对代码文件执行可自动化的优化操作。
当前支持:
  - 添加模块 docstring
  - 添加函数/类 docstring 骨架
  - 添加 if __name__ == '__main__' 保护
  - 修复超长行 (简单拆分)
  - 排序 import (isort 风格)

输出: {OUTPUT_DIR}/code-refine-result.json
"""

from datetime import datetime, timezone
import ast
import json
import os
import re

from modules.types import CodeRefineResult
import sys

from modules.compat import setup_logger, cfg, save_json

log = setup_logger("code_refiner")


def _is_dry_run() -> bool:
    """运行时检查 DRY_RUN 环境变量。"""
    return os.environ.get("DRY_RUN", "").lower() in ("true", "1", "yes")


from modules.compat import read_file_safe
_read_file = read_file_safe


def _write_file(filepath: str, content: str):
    if _is_dry_run():
        return
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)


# ── Python Docstring 生成 ────────────────────────────

def _generate_func_docstring(node) -> str:
    """为函数生成 docstring 骨架。"""
    args = []
    for arg in node.args.args:
        if arg.arg not in ("self", "cls"):
            ann = ""
            if arg.annotation:
                try:
                    ann = f" ({ast.unparse(arg.annotation)})"
                except Exception:
                    pass
            args.append(f"        {arg.arg}{ann}: ...")

    ret = ""
    if node.returns:
        try:
            ret = f"\n\n    Returns:\n        {ast.unparse(node.returns)}: ..."
        except Exception:
            ret = "\n\n    Returns:\n        ..."

    params_section = ""
    if args:
        params_section = "\n\n    Args:\n" + "\n".join(args)

    return f'"""{node.name} 的功能描述。{params_section}{ret}\n    """'


def _generate_class_docstring(node) -> str:
    """为类生成 docstring 骨架。"""
    bases = ""
    if node.bases:
        try:
            bases = f"\n\n    继承: {', '.join(ast.unparse(b) for b in node.bases)}"
        except Exception:
            pass
    return f'"""{node.name} 类的功能描述。{bases}\n    """'


def _generate_module_docstring(filepath: str) -> str:
    """为模块生成 docstring。"""
    name = os.path.basename(filepath)
    return f'"""\n{name} — 模块功能描述。\n"""'


# ── 优化操作 ─────────────────────────────────────────

def add_docstrings(filepath: str, text: str) -> tuple:
    """为缺少 docstring 的函数/类/模块添加 docstring 骨架。"""
    changes = 0

    try:
        tree = ast.parse(text, filename=filepath)
    except SyntaxError:
        return text, 0

    lines = text.split("\n")
    insertions = []  # [(line_index, indent, docstring)]

    # 模块 docstring
    if not ast.get_docstring(tree) and len(lines) > 10:
        # 找第一个非注释非空行
        insert_at = 0
        for i, line in enumerate(lines):
            if line.strip().startswith("#!") or line.strip().startswith("# -*-"):
                insert_at = i + 1
            else:
                break
        doc = _generate_module_docstring(filepath)
        insertions.append((insert_at, "", doc))
        changes += 1

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not ast.get_docstring(node) and not node.name.startswith("_"):
                # 在函数体第一行前插入 docstring
                body_line = node.body[0].lineno - 1  # 0-indexed
                indent = "    " * _get_indent_level(lines, node.lineno - 1)
                doc = _generate_func_docstring(node)
                insertions.append((body_line, indent, doc))
                changes += 1

        elif isinstance(node, ast.ClassDef):
            if not ast.get_docstring(node):
                body_line = node.body[0].lineno - 1
                indent = "    " * _get_indent_level(lines, node.lineno - 1)
                doc = _generate_class_docstring(node)
                insertions.append((body_line, indent, doc))
                changes += 1

    # 从后往前插入，避免行号偏移
    for line_idx, indent, doc in sorted(insertions, reverse=True):
        indented_doc = "\n".join(f"{indent}    {l}" if l.strip() else ""
                                 for l in doc.split("\n"))
        lines.insert(line_idx, indented_doc)

    return "\n".join(lines), changes


def _get_indent_level(lines: list, line_idx: int) -> int:
    """获取行的缩进层级。"""
    if line_idx < len(lines):
        line = lines[line_idx]
        stripped = line.lstrip()
        if stripped:
            indent = len(line) - len(stripped)
            return indent // 4
    return 0


def add_main_guard(text: str) -> tuple:
    """添加 if __name__ == '__main__' 保护。"""
    if 'if __name__' in text:
        return text, 0

    # 检查是否有顶层可执行代码
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return text, 0

    has_top_level_calls = False
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            has_top_level_calls = True
            break

    if not has_top_level_calls:
        # 只添加空框架
        text = text.rstrip() + "\n\n\nif __name__ == \"__main__\":\n    pass\n"
        return text, 1

    return text, 0


def sort_imports(text: str) -> tuple:
    """简化版 import 排序 (stdlib → third-party → local)。"""
    lines = text.split("\n")
    import_block_start = None
    import_block_end = None
    import_lines = []

    # 找到第一个 import 块
    in_block = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(("import ", "from ")):
            if not in_block:
                import_block_start = i
                in_block = True
            import_lines.append(line)
            import_block_end = i
        elif in_block and stripped == "":
            continue  # 允许空行
        elif in_block and not stripped.startswith("#"):
            break

    if not import_lines or len(import_lines) <= 1:
        return text, 0

    # 分组: stdlib, third-party, local
    stdlib = []
    third_party = []
    local = []

    STDLIB_MODULES = {
        "os", "sys", "re", "json", "ast", "math", "time", "datetime",
        "pathlib", "collections", "functools", "itertools", "typing",
        "subprocess", "shutil", "logging", "argparse", "unittest",
        "hashlib", "uuid", "copy", "io", "tempfile", "glob", "fnmatch",
        "importlib", "inspect", "abc", "enum", "dataclasses", "string",
        "textwrap", "difflib", "urllib", "http", "email", "html",
        "xml", "csv", "configparser", "socket", "threading", "multiprocessing",
        "asyncio", "contextlib", "warnings", "traceback", "pprint",
    }

    for line in import_lines:
        stripped = line.strip()
        if stripped.startswith("from .") or stripped.startswith("from .."):
            local.append(line)
        elif stripped.startswith("import ") or stripped.startswith("from "):
            module = stripped.split()[1].split(".")[0]
            if module in STDLIB_MODULES:
                stdlib.append(line)
            elif module.startswith("_") or module == "utils":
                local.append(line)
            else:
                third_party.append(line)

    # 重建
    sorted_imports = []
    if stdlib:
        sorted_imports.extend(sorted(stdlib))
    if third_party:
        if sorted_imports:
            sorted_imports.append("")
        sorted_imports.extend(sorted(third_party))
    if local:
        if sorted_imports:
            sorted_imports.append("")
        sorted_imports.extend(sorted(local))

    # 替换
    new_lines = lines[:import_block_start] + sorted_imports + lines[import_block_end + 1:]
    new_text = "\n".join(new_lines)
    changes = 1 if new_text != text else 0
    return new_text, changes


def fix_trailing_whitespace(text: str) -> tuple:
    """修复行尾空白。"""
    lines = text.split("\n")
    changes = 0
    new_lines = []
    for line in lines:
        stripped = line.rstrip()
        if stripped != line:
            changes += 1
        new_lines.append(stripped)
    return "\n".join(new_lines), changes


def ensure_final_newline(text: str) -> tuple:
    """确保文件以换行结尾。"""
    if not text.endswith("\n"):
        return text + "\n", 1
    return text, 0


# ── JavaScript / TypeScript 自动修复 ─────────────────

def add_jsdoc(filepath: str, text: str) -> tuple:
    """为缺少 JSDoc 的函数添加 JSDoc 骨架。"""
    lines = text.split("\n")
    insertions = []
    changes = 0

    for i, line in enumerate(lines):
        # function declaration
        m = re.match(r"^(\s*)(export\s+)?(default\s+)?(async\s+)?function\s*\*?\s*(\w+)\s*\(([^)]*)\)", line)
        if m:
            indent = m.group(1)
            name = m.group(5)
            params = m.group(6)
            # Check if previous line is already a JSDoc
            if i > 0 and lines[i - 1].strip().endswith("*/"):
                continue
            jsdoc = _build_jsdoc(indent, name, params)
            insertions.append((i, jsdoc))
            changes += 1
            continue

        # arrow / const functions
        m = re.match(r"^(\s*)(export\s+)?(const|let|var)\s+(\w+)\s*=\s*(async\s+)?(?:\(([^)]*)\)|(\w+))\s*=>", line)
        if m:
            indent = m.group(1)
            name = m.group(4)
            params = m.group(6) or m.group(7) or ""
            if i > 0 and lines[i - 1].strip().endswith("*/"):
                continue
            jsdoc = _build_jsdoc(indent, name, params)
            insertions.append((i, jsdoc))
            changes += 1

    # Insert from bottom to top
    for line_idx, doc in sorted(insertions, reverse=True):
        lines.insert(line_idx, doc)

    return "\n".join(lines), changes


def _build_jsdoc(indent: str, name: str, params_str: str) -> str:
    """构建 JSDoc 注释。"""
    parts = [f"{indent}/**", f"{indent} * {name} — TODO: add description."]
    if params_str.strip():
        for p in params_str.split(","):
            p = p.strip()
            if not p:
                continue
            # Handle TS type annotations: name: Type
            pname = re.split(r"[=:\s]", p)[0].strip()
            if pname:
                parts.append(f"{indent} * @param {{{pname}}} {pname} — TODO")
    parts.append(f"{indent} * @returns TODO")
    parts.append(f"{indent} */")
    return "\n".join(parts)


def add_strict_mode(text: str) -> tuple:
    """为 CJS 文件添加 'use strict'。"""
    if "'use strict'" in text or '"use strict"' in text:
        return text, 0
    lines = text.split("\n")
    insert_at = 0
    # Skip shebang or initial comments
    for i, line in enumerate(lines):
        if line.strip().startswith("#!") or line.strip().startswith("//"):
            insert_at = i + 1
        else:
            break
    lines.insert(insert_at, "'use strict';")
    lines.insert(insert_at + 1, "")
    return "\n".join(lines), 1


# ── Go 自动修复 ──────────────────────────────────────

def add_go_doc_comments(text: str) -> tuple:
    """为缺少文档注释的导出符号添加注释。"""
    lines = text.split("\n")
    insertions = []
    changes = 0

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Exported function
        m = re.match(r"^func\s+(\w+)\s*\(", stripped)
        if m and m.group(1)[0].isupper():
            if i > 0 and lines[i - 1].strip().startswith("//"):
                continue
            name = m.group(1)
            insertions.append((i, f"// {name} — TODO: add documentation."))
            changes += 1
            continue

        # Exported method
        m = re.match(r"^func\s+\(\w+\s+\*?\w+\)\s+(\w+)\s*\(", stripped)
        if m and m.group(1)[0].isupper():
            if i > 0 and lines[i - 1].strip().startswith("//"):
                continue
            name = m.group(1)
            insertions.append((i, f"// {name} — TODO: add documentation."))
            changes += 1
            continue

        # Exported type
        m = re.match(r"^type\s+(\w+)\s+(struct|interface)\s*\{", stripped)
        if m and m.group(1)[0].isupper():
            if i > 0 and lines[i - 1].strip().startswith("//"):
                continue
            name = m.group(1)
            insertions.append((i, f"// {name} — TODO: add documentation."))
            changes += 1

    for line_idx, doc in sorted(insertions, reverse=True):
        lines.insert(line_idx, doc)

    return "\n".join(lines), changes


# ── Shell 自动修复 ───────────────────────────────────

def add_shell_set_e(text: str) -> tuple:
    """添加 set -euo pipefail。"""
    if "set -e" in text:
        return text, 0
    lines = text.split("\n")
    insert_at = 0
    # After shebang
    if lines and lines[0].startswith("#!"):
        insert_at = 1
    # After initial comment block
    for i in range(insert_at, min(len(lines), 10)):
        if lines[i].strip().startswith("#") or not lines[i].strip():
            insert_at = i + 1
        else:
            break
    lines.insert(insert_at, "set -euo pipefail")
    lines.insert(insert_at + 1, "")
    return "\n".join(lines), 1


def add_shell_shebang(text: str) -> tuple:
    """添加 shebang 行。"""
    if text.startswith("#!"):
        return text, 0
    return "#!/usr/bin/env bash\n" + text, 1


def fix_shell_backticks(text: str) -> tuple:
    """将反引号替换为 $(…)。"""
    changes = 0
    result = []
    for line in text.split("\n"):
        if line.strip().startswith("#"):
            result.append(line)
            continue
        # Replace `cmd` with $(cmd) — simple cases only
        new_line = line
        while "`" in new_line:
            m = re.search(r"`([^`]+)`", new_line)
            if m:
                cmd = m.group(1)
                new_line = new_line[:m.start()] + "$(" + cmd + ")" + new_line[m.end():]
                changes += 1
            else:
                break
        result.append(new_line)
    return "\n".join(result), min(changes, 1)  # count as 1 change


# ── Rust 自动修复 ────────────────────────────────────

def add_rust_doc_comments(text: str) -> tuple:
    """为缺少文档注释的公共项添加 /// 注释。"""
    lines = text.split("\n")
    insertions = []
    changes = 0

    for i, line in enumerate(lines):
        stripped = line.strip()
        indent = line[:len(line) - len(line.lstrip())]

        # pub fn
        m = re.match(r"^\s*pub\s+(?:async\s+)?fn\s+(\w+)", stripped)
        if m:
            if i > 0 and lines[i - 1].strip().startswith("///"):
                continue
            name = m.group(1)
            insertions.append((i, f"{indent}/// {name} — TODO: add documentation."))
            changes += 1
            continue

        # pub struct / pub enum
        m = re.match(r"^\s*pub\s+(?:struct|enum)\s+(\w+)", stripped)
        if m:
            if i > 0 and lines[i - 1].strip().startswith("///"):
                continue
            name = m.group(1)
            insertions.append((i, f"{indent}/// {name} — TODO: add documentation."))
            changes += 1

    for line_idx, doc in sorted(insertions, reverse=True):
        lines.insert(line_idx, doc)

    return "\n".join(lines), changes


# ── C/C++ 自动修复 ────────────────────────────────────

def add_doxygen_comments(text: str) -> tuple:
    """为缺少 Doxygen 文档的函数添加 /** */ 注释。"""
    lines = text.split("\n")
    insertions = []
    changes = 0

    for i, line in enumerate(lines):
        stripped = line.strip()
        indent = line[:len(line) - len(line.lstrip())]

        # Function definition pattern (skip macros and control flow)
        m = re.match(
            r"^\s*(?:static\s+|inline\s+|extern\s+|virtual\s+|const\s+)*"
            r"(?:(?:unsigned|signed|long|short)\s+)*"
            r"(?:\w[\w:*&<>, ]*?)\s+(\*?\w+)\s*\(([^)]*)\)\s*(?:const\s*)?(?:override\s*)?(?:noexcept\s*)?[{]?\s*$",
            stripped
        )
        if m:
            name = m.group(1).lstrip("*")
            if name in ("if", "else", "for", "while", "switch", "return", "sizeof"):
                continue
            # Check if already has doc comment
            if i > 0 and (lines[i - 1].strip().startswith("/**")
                          or lines[i - 1].strip().startswith("*/")):
                continue
            params = m.group(2).strip()
            doc_lines = [f"{indent}/**"]
            doc_lines.append(f"{indent} * @brief TODO: describe {name}.")
            if params:
                for p in params.split(","):
                    p = p.strip()
                    parts = p.split()
                    if parts:
                        pname = parts[-1].lstrip("*&")
                        if pname:
                            doc_lines.append(f"{indent} * @param {pname} TODO: description")
            doc_lines.append(f"{indent} */")
            insertions.append((i, "\n".join(doc_lines)))
            changes += 1

    for line_idx, doc in sorted(insertions, reverse=True):
        lines.insert(line_idx, doc)

    return "\n".join(lines), changes


def add_header_guard(filepath: str, text: str) -> tuple:
    """为头文件添加 #ifndef include guard。"""
    lines = text.split("\n")

    # Check if already has guard
    for line in lines[:10]:
        stripped = line.strip()
        if stripped.startswith("#ifndef ") or stripped.startswith("#pragma once"):
            return text, 0

    # Generate guard name from filename
    fname = os.path.basename(filepath)
    guard = re.sub(r"[^A-Z0-9]", "_", fname.upper()) + "_"

    header = [f"#ifndef {guard}", f"#define {guard}", ""]
    footer = ["", f"#endif  // {guard}"]

    new_text = "\n".join(header) + "\n" + text.rstrip("\n") + "\n".join(footer) + "\n"
    return new_text, 1


# ── Java 自动修复 ─────────────────────────────────────

def add_javadoc(filepath: str, text: str) -> tuple:
    """为缺少 Javadoc 的公共方法和类添加文档注释。"""
    lines = text.split("\n")
    insertions = []
    changes = 0

    for i, line in enumerate(lines):
        stripped = line.strip()
        indent = line[:len(line) - len(line.lstrip())]

        # Class / interface
        m = re.match(
            r"^\s*(?:public\s+)?(?:abstract\s+|final\s+)?(?:class|interface|enum)\s+(\w+)",
            stripped
        )
        if m:
            if i > 0 and lines[i - 1].strip().endswith("*/"):
                continue
            name = m.group(1)
            doc = [f"{indent}/**", f"{indent} * {name} — TODO: add description.", f"{indent} */"]
            insertions.append((i, "\n".join(doc)))
            changes += 1
            continue

        # Public method
        m = re.match(
            r"^\s*public\s+(?:static\s+)?(?:final\s+)?(?:synchronized\s+)?(?:abstract\s+)?"
            r"(?:[\w<>\[\],.? ]+?)\s+(\w+)\s*\(([^)]*)\)\s*(?:throws\s+[\w,\s]+)?\s*[{;]",
            stripped
        )
        if m:
            name = m.group(1)
            if name in ("if", "for", "while", "switch", "return", "new", "class"):
                continue
            if i > 0 and lines[i - 1].strip().endswith("*/"):
                continue
            params_str = m.group(2).strip()
            doc = [f"{indent}/**", f"{indent} * {name} — TODO: add description."]
            if params_str:
                for p in params_str.split(","):
                    p = p.strip()
                    parts = p.split()
                    if len(parts) >= 2:
                        pname = parts[-1]
                        doc.append(f"{indent} * @param {pname} TODO: description")
            doc.append(f"{indent} */")
            insertions.append((i, "\n".join(doc)))
            changes += 1

    for line_idx, doc in sorted(insertions, reverse=True):
        lines.insert(line_idx, doc)

    return "\n".join(lines), changes


# ── 主入口 ───────────────────────────────────────────

def refine_file(filepath: str, improvements: list = None) -> CodeRefineResult:
    """对单个文件执行自动优化。"""
    text = _read_file(filepath)
    original = text
    total_changes = 0
    applied = []

    ext = os.path.splitext(filepath)[1].lower()

    # 1. 行尾空白 (所有语言)
    text, n = fix_trailing_whitespace(text)
    if n:
        total_changes += 1
        applied.append("fix_trailing_whitespace")

    # 2. 末尾换行 (所有语言)
    text, n = ensure_final_newline(text)
    if n:
        total_changes += 1
        applied.append("ensure_final_newline")

    # ── Python ──
    if ext == ".py":
        text, n = add_docstrings(filepath, text)
        if n:
            total_changes += n
            applied.append(f"add_docstrings ({n})")

        text, n = sort_imports(text)
        if n:
            total_changes += 1
            applied.append("sort_imports")

        text, n = add_main_guard(text)
        if n:
            total_changes += 1
            applied.append("add_main_guard")

    # ── JavaScript / TypeScript ──
    elif ext in (".js", ".mjs", ".jsx", ".ts", ".tsx"):
        text, n = add_jsdoc(filepath, text)
        if n:
            total_changes += n
            applied.append(f"add_jsdoc ({n})")

        # Strict mode for CJS files only
        if ext == ".js":
            text, n = add_strict_mode(text)
            if n:
                total_changes += 1
                applied.append("add_strict_mode")

    # ── Go ──
    elif ext == ".go":
        text, n = add_go_doc_comments(text)
        if n:
            total_changes += n
            applied.append(f"add_go_doc ({n})")

    # ── Shell ──
    elif ext in (".sh", ".bash", ".zsh"):
        text, n = add_shell_shebang(text)
        if n:
            total_changes += 1
            applied.append("add_shebang")

        text, n = add_shell_set_e(text)
        if n:
            total_changes += 1
            applied.append("add_set_e")

        text, n = fix_shell_backticks(text)
        if n:
            total_changes += 1
            applied.append("fix_backticks")

    # ── Rust ──
    elif ext == ".rs":
        text, n = add_rust_doc_comments(text)
        if n:
            total_changes += n
            applied.append(f"add_rust_doc ({n})")

    # ── C/C++ ──
    elif ext in (".c", ".cpp", ".cxx", ".cc", ".h", ".hpp", ".hxx"):
        text, n = add_doxygen_comments(text)
        if n:
            total_changes += n
            applied.append(f"add_doxygen ({n})")

        # Header guard for header files
        if ext in (".h", ".hpp", ".hxx"):
            text, n = add_header_guard(filepath, text)
            if n:
                total_changes += 1
                applied.append("add_header_guard")

    # ── Java ──
    elif ext == ".java":
        text, n = add_javadoc(filepath, text)
        if n:
            total_changes += n
            applied.append(f"add_javadoc ({n})")

    # 写回
    if text != original:
        _write_file(filepath, text)

    return {
        "file": os.path.basename(filepath),
        "relative_path": filepath,
        "changes": total_changes,
        "applied": applied,
        "modified": text != original,
    }


def refine_all(analysis_report: dict, scan_report: dict = None,
               max_files: int = None) -> dict:
    """基于分析报告执行批量代码优化。"""
    if not analysis_report:
        return {"total_processed": 0, "refined": 0, "total_changes": 0}

    # 获取文件列表
    files_to_process = []
    for imp in analysis_report.get("improvements", []):
        if imp.get("auto_fixable"):
            fpath = imp.get("file", "")
            if fpath and fpath not in [f[0] for f in files_to_process]:
                score = imp.get("file_score", 100)
                files_to_process.append((fpath, score))

    # 也把低分文件加入
    if scan_report:
        for f in scan_report.get("files", []):
            fpath = f.get("path", "")
            if fpath and fpath not in [fp[0] for fp in files_to_process]:
                if f.get("quality_score", 100) < 75:
                    files_to_process.append((fpath, f.get("quality_score", 0)))

    # 按分数排序（低分优先）
    files_to_process.sort(key=lambda x: x[1])

    if max_files:
        files_to_process = files_to_process[:max_files]

    results = []
    total_changes = 0

    for fpath, score in files_to_process:
        if not os.path.exists(fpath):
            continue
        try:
            result = refine_file(fpath)
            results.append(result)
            total_changes += result.get("changes", 0)
            if result.get("modified"):
                log.info(f"  ✅ {result['file']}: {result['changes']} 项修改")
        except Exception as e:
            log.error(f"  ❌ {fpath}: {e}")
            results.append({"file": os.path.basename(fpath), "error": str(e)})

    refined = sum(1 for r in results if r.get("modified"))

    report = {
        "total_processed": len(results),
        "refined": refined,
        "total_changes": total_changes,
        "results": results,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }

    log.info(f"  代码精炼完成: {refined}/{len(results)} 文件, {total_changes} 项修改")
    return report


def run():
    """主入口。"""
    output_dir = cfg("output_dir", "/tmp/openclaw-code-reports")

    analysis_path = os.path.join(output_dir, "code-analysis-report.json")
    scan_path = os.path.join(output_dir, "code-scan-report.json")

    analysis = {}
    scan = {}
    if os.path.exists(analysis_path):
        with open(analysis_path) as f:
            analysis = json.load(f)
    if os.path.exists(scan_path):
        with open(scan_path) as f:
            scan = json.load(f)

    report = refine_all(analysis, scan)
    out_path = os.path.join(output_dir, "code-refine-result.json")
    save_json(out_path, report)
    log.info(f"精炼报告已保存: {out_path}")
    return report


if __name__ == "__main__":
    run()
