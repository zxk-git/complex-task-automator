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
import sys

_SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

try:
    from utils import setup_logger, cfg, save_json
except ImportError:
    import logging
    def setup_logger(name):
        """setup_logger 的功能描述。

            Args:
                name: ...
            """
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
        return logging.getLogger(name)
    def cfg(key, default=None):
        """cfg 的功能描述。

            Args:
                key: ...
                default: ...
            """
        return os.environ.get(key.replace(".", "_").upper(), default)
    def save_json(path, data):
        """save_json 的功能描述。

            Args:
                path: ...
                data: ...
            """
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

log = setup_logger("code_refiner")


def _is_dry_run() -> bool:
    """运行时检查 DRY_RUN 环境变量。"""
    return os.environ.get("DRY_RUN", "").lower() in ("true", "1", "yes")


def _read_file(filepath: str) -> str:
    with open(filepath, encoding="utf-8") as f:
        return f.read()


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


# ── 主入口 ───────────────────────────────────────────

def refine_file(filepath: str, improvements: list = None) -> dict:
    """对单个文件执行自动优化。"""
    text = _read_file(filepath)
    original = text
    total_changes = 0
    applied = []

    lang = os.path.splitext(filepath)[1].lower()
    is_python = lang == ".py"

    # 1. 行尾空白
    text, n = fix_trailing_whitespace(text)
    if n:
        total_changes += 1
        applied.append("fix_trailing_whitespace")

    # 2. 末尾换行
    text, n = ensure_final_newline(text)
    if n:
        total_changes += 1
        applied.append("ensure_final_newline")

    if is_python:
        # 3. Docstrings
        text, n = add_docstrings(filepath, text)
        if n:
            total_changes += n
            applied.append(f"add_docstrings ({n})")

        # 4. Import 排序
        text, n = sort_imports(text)
        if n:
            total_changes += 1
            applied.append("sort_imports")

        # 5. Main guard
        text, n = add_main_guard(text)
        if n:
            total_changes += 1
            applied.append("add_main_guard")

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
