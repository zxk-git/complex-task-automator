#!/usr/bin/env python3
"""
code_scanner.py — 代码仓库扫描器
===================================
扫描代码仓库的所有源文件，提取结构化元数据和质量指标。
支持 Python / JavaScript / TypeScript / Shell 等语言。

输出: {OUTPUT_DIR}/code-scan-report.json
"""

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import ast
import json
import os
import re
import sys

from modules.compat import setup_logger, cfg, save_json

log = setup_logger("code_scanner")

# ── 支持的语言扩展名 ──
LANG_MAP = {
    ".py":   "python",
    ".js":   "javascript",
    ".ts":   "typescript",
    ".mjs":  "javascript",
    ".jsx":  "javascript",
    ".tsx":  "typescript",
    ".go":   "go",
    ".sh":   "shell",
    ".bash": "shell",
    ".zsh":  "shell",
    ".c":    "c",
    ".h":    "c",
    ".cpp":  "cpp",
    ".cxx":  "cpp",
    ".cc":   "cpp",
    ".hpp":  "cpp",
    ".hxx":  "cpp",
    ".java": "java",
    ".yaml": "yaml",
    ".yml":  "yaml",
    ".json": "json",
    ".md":   "markdown",
    ".toml": "toml",
    ".rs":   "rust",
    ".rb":   "ruby",
}

# 默认忽略的目录
IGNORE_DIRS = {
    "node_modules", "__pycache__", ".git", ".venv", "venv",
    "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
    "egg-info", ".task-logs", ".cache",
}

# 默认忽略的文件模式
IGNORE_PATTERNS = [
    r"\.min\.(js|css)$",
    r"package-lock\.json$",
    r"yarn\.lock$",
    r"\.pyc$",
    r"\.bak(\.\d+)?$",
]


def _should_ignore(name: str, ignore_dirs=None) -> bool:
    """判断是否跳过目录/文件。"""
    dirs = ignore_dirs or IGNORE_DIRS
    if name in dirs:
        return True
    for pat in IGNORE_PATTERNS:
        if re.search(pat, name):
            return True
    return False


def _read_file(filepath: str) -> str:
    """安全读取文件内容。"""
    try:
        with open(filepath, encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return ""


# ── Python 专用分析 ──────────────────────────────────

def _analyze_python(filepath: str, text: str) -> dict:
    """深度分析 Python 文件。"""
    result = {
        "functions": [],
        "classes": [],
        "imports": [],
        "global_vars": [],
        "docstring": None,
        "has_main_guard": False,
        "type_hint_coverage": 0.0,
        "complexity_estimate": 0,
    }

    try:
        tree = ast.parse(text, filename=filepath)
    except SyntaxError:
        result["parse_error"] = True
        return result

    # 模块级 docstring
    result["docstring"] = ast.get_docstring(tree)

    total_params = 0
    typed_params = 0

    for node in ast.walk(tree):
        # 函数
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_info = {
                "name": node.name,
                "line": node.lineno,
                "end_line": getattr(node, "end_lineno", node.lineno),
                "args_count": len(node.args.args),
                "has_docstring": ast.get_docstring(node) is not None,
                "has_return_annotation": node.returns is not None,
                "is_private": node.name.startswith("_"),
                "decorators": [_decorator_name(d) for d in node.decorator_list],
                "complexity": _estimate_complexity(node),
            }
            func_info["line_count"] = func_info["end_line"] - func_info["line"] + 1
            result["functions"].append(func_info)

            # 类型提示统计
            for arg in node.args.args:
                if arg.arg != "self" and arg.arg != "cls":
                    total_params += 1
                    if arg.annotation:
                        typed_params += 1
            if node.returns:
                typed_params += 1
            total_params += 1  # return type counts

        # 类
        elif isinstance(node, ast.ClassDef):
            methods = [n for n in ast.walk(node) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            result["classes"].append({
                "name": node.name,
                "line": node.lineno,
                "has_docstring": ast.get_docstring(node) is not None,
                "bases": [_node_name(b) for b in node.bases],
                "method_count": len(methods),
                "decorators": [_decorator_name(d) for d in node.decorator_list],
            })

        # Import
        elif isinstance(node, ast.Import):
            for alias in node.names:
                result["imports"].append({
                    "module": alias.name,
                    "alias": alias.asname,
                    "line": node.lineno,
                })
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                result["imports"].append({
                    "module": f"{module}.{alias.name}",
                    "alias": alias.asname,
                    "line": node.lineno,
                    "from": module,
                })

    # 全局变量 (顶层 Assign)
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    result["global_vars"].append({
                        "name": target.id,
                        "line": node.lineno,
                    })

    # if __name__ == "__main__"
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.If):
            try:
                test = ast.dump(node.test)
                if "__name__" in test and "__main__" in test:
                    result["has_main_guard"] = True
            except Exception:
                pass

    # 类型提示覆盖率
    if total_params > 0:
        result["type_hint_coverage"] = round(typed_params / total_params, 2)

    # 总体复杂度
    result["complexity_estimate"] = sum(
        f.get("complexity", 0) for f in result["functions"]
    )

    return result


def _estimate_complexity(node) -> int:
    """估算函数的 McCabe 复杂度。"""
    complexity = 1  # 基础值
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.IfExp)):
            complexity += 1
        elif isinstance(child, (ast.For, ast.While, ast.AsyncFor)):
            complexity += 1
        elif isinstance(child, ast.ExceptHandler):
            complexity += 1
        elif isinstance(child, (ast.And, ast.Or)):
            complexity += 1
        elif isinstance(child, ast.BoolOp):
            complexity += len(child.values) - 1
        elif isinstance(child, ast.comprehension):
            complexity += 1
            complexity += len(child.ifs)
    return complexity


def _decorator_name(node) -> str:
    """提取装饰器名称。"""
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        return f"{_node_name(node.value)}.{node.attr}"
    elif isinstance(node, ast.Call):
        return _decorator_name(node.func)
    return "?"


def _node_name(node) -> str:
    """提取 AST 节点名称。"""
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        return f"{_node_name(node.value)}.{node.attr}"
    return "?"


# ── JavaScript / TypeScript 深度分析 ─────────────────

def _analyze_javascript(text: str, lang: str) -> dict:
    """深度分析 JavaScript / TypeScript 文件。"""
    lines = text.split("\n")
    result = {
        "functions": [],
        "classes": [],
        "interfaces": [],      # TypeScript
        "type_aliases": [],     # TypeScript
        "imports": [],
        "exports": [],
        "jsdoc_count": 0,
        "async_count": 0,
        "react_components": [],
        "has_strict_mode": False,
        "module_type": None,    # "esm" / "cjs" / "mixed"
        "complexity_estimate": 0,
    }

    is_ts = lang == "typescript"
    esm_imports = 0
    cjs_requires = 0

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # strict mode
        if stripped in ('"use strict";', "'use strict';"):
            result["has_strict_mode"] = True

        # ── 函数 ──
        # function declarations
        m = re.match(r"^\s*(export\s+)?(default\s+)?(async\s+)?function\s*\*?\s*(\w+)?\s*\(", line)
        if m:
            name = m.group(4) or "<anonymous>"
            result["functions"].append({
                "name": name, "line": i,
                "is_async": bool(m.group(3)),
                "is_exported": bool(m.group(1)),
                "is_generator": "*" in line[:line.index("(")],
                "type": "function_declaration",
            })

        # arrow / const functions
        m = re.match(r"^\s*(export\s+)?(const|let|var)\s+(\w+)\s*(?::\s*[^=]+)?\s*=\s*(async\s+)?(?:\([^)]*\)|[^=])\s*=>", line)
        if m:
            result["functions"].append({
                "name": m.group(3), "line": i,
                "is_async": bool(m.group(4)),
                "is_exported": bool(m.group(1)),
                "type": "arrow_function",
            })

        # method pattern (inside class)
        m = re.match(r"^\s+(async\s+)?(\w+)\s*\([^)]*\)\s*(?::\s*\w[^{]*)?\s*\{", line)
        if m and not stripped.startswith(("if", "for", "while", "switch", "catch")):
            # Skip if already matched as function
            name = m.group(2)
            if name not in ("if", "for", "while", "switch", "catch", "return", "throw"):
                result["functions"].append({
                    "name": name, "line": i,
                    "is_async": bool(m.group(1)),
                    "type": "method",
                })

        # ── 类 ──
        m = re.match(r"^\s*(export\s+)?(default\s+)?(?:abstract\s+)?class\s+(\w+)(?:\s+extends\s+(\w[\w.]*))?(?:\s+implements\s+(.+))?\s*\{", line)
        if m:
            result["classes"].append({
                "name": m.group(3), "line": i,
                "extends": m.group(4),
                "implements": m.group(5).split(",") if m.group(5) else [],
                "is_exported": bool(m.group(1)),
            })

        # ── TypeScript: interface / type ──
        if is_ts:
            m = re.match(r"^\s*(export\s+)?interface\s+(\w+)(?:<[^>]+>)?\s*(?:extends\s+.+)?\s*\{", line)
            if m:
                result["interfaces"].append({
                    "name": m.group(2), "line": i,
                    "is_exported": bool(m.group(1)),
                })

            m = re.match(r"^\s*(export\s+)?type\s+(\w+)(?:<[^>]+>)?\s*=", line)
            if m:
                result["type_aliases"].append({
                    "name": m.group(2), "line": i,
                    "is_exported": bool(m.group(1)),
                })

        # ── 导入 ──
        if stripped.startswith("import "):
            esm_imports += 1
            m = re.match(r"import\s+(?:\{([^}]+)\}|(\w+)|(\*\s+as\s+\w+))\s+from\s+['\"]([^'\"]+)['\"]", stripped)
            if m:
                result["imports"].append({
                    "module": m.group(4) or "",
                    "line": i,
                    "type": "esm",
                })
        elif "require(" in stripped:
            cjs_requires += 1
            m = re.match(r"(?:const|let|var)\s+(?:\{[^}]+\}|(\w+))\s*=\s*require\(['\"]([^'\"]+)['\"]\)", stripped)
            if m:
                result["imports"].append({
                    "module": m.group(2) or "", "line": i,
                    "type": "cjs",
                })

        # ── 导出 ──
        if stripped.startswith("export "):
            m = re.match(r"export\s+(default\s+)?(?:const|let|var|function|class|async\s+function)\s+(\w+)?", stripped)
            if m:
                result["exports"].append({
                    "name": m.group(2) or "default", "line": i,
                    "is_default": bool(m.group(1)),
                })
        if re.match(r"module\.exports\s*=", stripped):
            result["exports"].append({"name": "module.exports", "line": i, "is_default": True})

        # ── JSDoc ──
        if stripped.startswith("/**"):
            result["jsdoc_count"] += 1

        # ── async ──
        if "async " in line:
            result["async_count"] += 1

        # ── React ──
        # Simple heuristic: const Foo = () => ( / return <
        m = re.match(r"^\s*(?:export\s+)?(?:const|function)\s+([A-Z]\w+)", line)
        if m:
            # Likely a React component if name starts with uppercase
            result["react_components"].append({"name": m.group(1), "line": i})

    # Module type
    if esm_imports > 0 and cjs_requires == 0:
        result["module_type"] = "esm"
    elif cjs_requires > 0 and esm_imports == 0:
        result["module_type"] = "cjs"
    elif esm_imports > 0 and cjs_requires > 0:
        result["module_type"] = "mixed"

    # Complexity estimate (branching)
    complexity = 0
    for line in lines:
        s = line.strip()
        if re.match(r"(if|else if|else|switch|case)\s*[\(\{:]", s):
            complexity += 1
        if re.match(r"(for|while|do)\s*[\(\{]", s):
            complexity += 1
        if "? " in s and ":" in s:  # ternary
            complexity += 1
        if ".catch(" in s or "catch " in s:
            complexity += 1
    result["complexity_estimate"] = complexity

    return result


# ── Go 深度分析 ──────────────────────────────────────

def _analyze_go(text: str) -> dict:
    """深度分析 Go 文件。"""
    lines = text.split("\n")
    result = {
        "package": None,
        "functions": [],
        "methods": [],
        "structs": [],
        "interfaces": [],
        "imports": [],
        "goroutines": 0,
        "channels": 0,
        "error_checks": 0,
        "test_functions": [],
        "has_init": False,
        "has_main": False,
        "complexity_estimate": 0,
        "doc_comments": 0,
    }

    in_import_block = False
    prev_comment = False

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # Package declaration
        m = re.match(r"^package\s+(\w+)", stripped)
        if m:
            result["package"] = m.group(1)

        # Imports
        if stripped == "import (":
            in_import_block = True
            continue
        if in_import_block:
            if stripped == ")":
                in_import_block = False
                continue
            m = re.match(r'^\s*(?:(\w+)\s+)?"([^"]+)"', stripped)
            if m:
                result["imports"].append({
                    "alias": m.group(1),
                    "path": m.group(2),
                    "line": i,
                })
        elif re.match(r'^import\s+"([^"]+)"', stripped):
            m = re.match(r'^import\s+"([^"]+)"', stripped)
            result["imports"].append({
                "alias": None, "path": m.group(1), "line": i,
            })

        # Functions
        m = re.match(r"^func\s+(\w+)\s*\(", stripped)
        if m:
            name = m.group(1)
            func_info = {
                "name": name, "line": i,
                "has_doc_comment": prev_comment,
                "is_exported": name[0].isupper(),
            }
            result["functions"].append(func_info)
            if name == "init":
                result["has_init"] = True
            elif name == "main":
                result["has_main"] = True
            if name.startswith("Test"):
                result["test_functions"].append({"name": name, "line": i})
            elif name.startswith("Benchmark"):
                result["test_functions"].append({"name": name, "line": i, "bench": True})

        # Methods (with receiver)
        m = re.match(r"^func\s+\((\w+)\s+\*?(\w+)\)\s+(\w+)\s*\(", stripped)
        if m:
            result["methods"].append({
                "receiver": m.group(2),
                "name": m.group(3),
                "line": i,
                "has_doc_comment": prev_comment,
                "is_exported": m.group(3)[0].isupper(),
            })

        # Structs
        m = re.match(r"^type\s+(\w+)\s+struct\s*\{", stripped)
        if m:
            result["structs"].append({
                "name": m.group(1), "line": i,
                "has_doc_comment": prev_comment,
                "is_exported": m.group(1)[0].isupper(),
            })

        # Interfaces
        m = re.match(r"^type\s+(\w+)\s+interface\s*\{", stripped)
        if m:
            result["interfaces"].append({
                "name": m.group(1), "line": i,
                "has_doc_comment": prev_comment,
                "is_exported": m.group(1)[0].isupper(),
            })

        # Goroutines
        if re.match(r"^\s*go\s+", stripped):
            result["goroutines"] += 1

        # Channels
        if "make(chan " in stripped or "<-" in stripped:
            result["channels"] += 1

        # Error checks
        if re.match(r"^\s*if\s+err\s*!=\s*nil", stripped):
            result["error_checks"] += 1

        # Doc comments (// Comment before exported symbol)
        if stripped.startswith("//"):
            prev_comment = True
            result["doc_comments"] += 1
        else:
            prev_comment = False

        # Complexity
        if re.match(r"^\s*(if|else if|else|switch|case)\s+", stripped):
            result["complexity_estimate"] += 1
        if re.match(r"^\s*for\s+", stripped):
            result["complexity_estimate"] += 1
        if re.match(r"^\s*select\s*\{", stripped):
            result["complexity_estimate"] += 1

    return result


# ── Shell 深度分析 ───────────────────────────────────

def _analyze_shell(text: str) -> dict:
    """深度分析 Shell 脚本。"""
    lines = text.split("\n")
    result = {
        "functions": [],
        "shebang": None,
        "set_options": [],
        "variables": [],
        "sourced_files": [],
        "uses_pipefail": False,
        "uses_set_e": False,
        "uses_set_u": False,
        "subshells": 0,
        "pipe_chains": 0,
        "heredocs": 0,
        "complexity_estimate": 0,
        "unquoted_vars": 0,
        "uses_backticks": False,
    }

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # Shebang
        if i == 1 and stripped.startswith("#!"):
            result["shebang"] = stripped

        # Functions
        m = re.match(r"^\s*(?:function\s+)?(\w+)\s*\(\)\s*\{?", stripped)
        if m and stripped not in ("", "{"):
            name = m.group(1)
            if name not in ("if", "then", "else", "fi", "for", "while", "do", "done", "case", "esac"):
                result["functions"].append({"name": name, "line": i})

        # set options
        m = re.match(r"^\s*set\s+(-\w+)", stripped)
        if m:
            opts = m.group(1)
            result["set_options"].append({"options": opts, "line": i})
            if "e" in opts:
                result["uses_set_e"] = True
            if "u" in opts:
                result["uses_set_u"] = True
        if "set -o pipefail" in stripped:
            result["uses_pipefail"] = True

        # Variables
        m = re.match(r"^(\w+)=", stripped)
        if m:
            result["variables"].append({"name": m.group(1), "line": i})

        # Source
        if stripped.startswith("source ") or stripped.startswith(". "):
            m = re.match(r"^(?:source|\.) +(.+)", stripped)
            if m:
                result["sourced_files"].append({"file": m.group(1).strip(), "line": i})

        # Subshells
        if "$(" in line:
            result["subshells"] += line.count("$(")

        # Pipe chains
        if " | " in line:
            result["pipe_chains"] += 1

        # Heredocs
        if "<<" in stripped and not stripped.startswith("#"):
            result["heredocs"] += 1

        # Backticks (deprecated)
        if "`" in line and not stripped.startswith("#"):
            result["uses_backticks"] = True

        # Unquoted variables ($VAR without quotes)
        for m in re.finditer(r'(?<!")\$\{?\w+\}?(?!")', line):
            # Very rough heuristic: if not inside double quotes on the line
            pos = m.start()
            if line[:pos].count('"') % 2 == 0 and line[pos:].count('"') % 2 == 0:
                result["unquoted_vars"] += 1

        # Complexity
        if re.match(r"^\s*(if|elif|else|case|for|while|until)\s", stripped):
            result["complexity_estimate"] += 1

    return result


# ── Rust 基础分析 ────────────────────────────────────

def _analyze_rust(text: str) -> dict:
    """基础分析 Rust 文件。"""
    lines = text.split("\n")
    result = {
        "functions": [],
        "structs": [],
        "enums": [],
        "traits": [],
        "impl_blocks": [],
        "imports": [],
        "macros": [],
        "unsafe_blocks": 0,
        "doc_comments": 0,
        "complexity_estimate": 0,
    }

    prev_doc = False

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # Functions
        m = re.match(r"^\s*(pub\s+)?(?:async\s+)?fn\s+(\w+)", stripped)
        if m:
            result["functions"].append({
                "name": m.group(2), "line": i,
                "is_public": bool(m.group(1)),
                "has_doc_comment": prev_doc,
            })

        # Structs
        m = re.match(r"^\s*(pub\s+)?struct\s+(\w+)", stripped)
        if m:
            result["structs"].append({
                "name": m.group(2), "line": i,
                "is_public": bool(m.group(1)),
                "has_doc_comment": prev_doc,
            })

        # Enums
        m = re.match(r"^\s*(pub\s+)?enum\s+(\w+)", stripped)
        if m:
            result["enums"].append({
                "name": m.group(2), "line": i,
                "is_public": bool(m.group(1)),
            })

        # Traits
        m = re.match(r"^\s*(pub\s+)?trait\s+(\w+)", stripped)
        if m:
            result["traits"].append({
                "name": m.group(2), "line": i,
                "is_public": bool(m.group(1)),
            })

        # Impl blocks
        m = re.match(r"^\s*impl(?:<[^>]+>)?\s+(?:(\w+)\s+for\s+)?(\w+)", stripped)
        if m:
            result["impl_blocks"].append({
                "trait": m.group(1),
                "target": m.group(2),
                "line": i,
            })

        # use statements
        m = re.match(r"^\s*use\s+(.+);", stripped)
        if m:
            result["imports"].append({"path": m.group(1), "line": i})

        # Macros
        m = re.match(r"^\s*macro_rules!\s+(\w+)", stripped)
        if m:
            result["macros"].append({"name": m.group(1), "line": i})

        # Unsafe
        if "unsafe " in stripped:
            result["unsafe_blocks"] += 1

        # Doc comments
        if stripped.startswith("///") or stripped.startswith("//!"):
            prev_doc = True
            result["doc_comments"] += 1
        else:
            prev_doc = False

        # Complexity
        if re.match(r"^\s*(if|else if|else|match|for|while|loop)\s", stripped):
            result["complexity_estimate"] += 1

    return result


# ── C/C++ 深度分析 ───────────────────────────────────

def _analyze_c_cpp(text: str, lang: str) -> dict:
    """C / C++ 源文件深度分析。"""
    lines = text.split("\n")
    is_cpp = (lang == "cpp")

    result = {
        "functions": [],
        "structs": [],
        "classes": [],        # C++ only
        "enums": [],
        "includes": [],
        "macros": [],
        "typedefs": [],
        "has_main": False,
        "has_header_guard": False,
        "doc_comments": 0,
        "complexity_estimate": 0,
        "goto_count": 0,
        "malloc_count": 0,
        "namespace": None,    # C++ only
    }

    prev_doc = False
    in_comment_block = False
    brace_depth = 0

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # 多行注释追踪
        if "/*" in stripped and "*/" not in stripped:
            in_comment_block = True
        if "*/" in stripped:
            in_comment_block = False
            continue
        if in_comment_block:
            if stripped.startswith("*") or stripped.startswith("/**"):
                pass  # doc comment body
            continue

        # Brace depth tracking
        brace_depth += stripped.count("{") - stripped.count("}")

        # #include
        m = re.match(r'^\s*#include\s+[<"]([^>"]+)[>"]', stripped)
        if m:
            result["includes"].append({"path": m.group(1), "line": i})
            continue

        # #define macros
        m = re.match(r"^\s*#define\s+(\w+)", stripped)
        if m:
            result["macros"].append({"name": m.group(1), "line": i})
            # Header guard detection
            name = m.group(1)
            if name.endswith("_H") or name.endswith("_H_") or name.endswith("_HPP"):
                result["has_header_guard"] = True
            continue

        # typedef
        m = re.match(r"^\s*typedef\s+.+\s+(\w+)\s*;", stripped)
        if m:
            result["typedefs"].append({"name": m.group(1), "line": i})

        # C++ namespace
        if is_cpp:
            m = re.match(r"^\s*namespace\s+(\w+)", stripped)
            if m and result["namespace"] is None:
                result["namespace"] = m.group(1)

        # C++ class
        if is_cpp:
            m = re.match(r"^\s*(?:template\s*<[^>]*>\s*)?class\s+(\w+)(?:\s*:\s*(?:public|protected|private)\s+\w+)?", stripped)
            if m:
                result["classes"].append({
                    "name": m.group(1),
                    "line": i,
                    "has_doc_comment": prev_doc,
                })

        # struct
        m = re.match(r"^\s*(?:typedef\s+)?struct\s+(\w+)", stripped)
        if m:
            result["structs"].append({
                "name": m.group(1),
                "line": i,
                "has_doc_comment": prev_doc,
            })

        # enum
        m = re.match(r"^\s*(?:typedef\s+)?enum\s+(?:class\s+)?(\w+)", stripped)
        if m:
            result["enums"].append({"name": m.group(1), "line": i})

        # Function detection (top-level, brace_depth <= 1)
        if brace_depth <= 1 and not stripped.startswith("#"):
            # Pattern: return_type func_name(params) {  or  return_type func_name(params);
            m = re.match(
                r"^\s*(?:static\s+|inline\s+|extern\s+|virtual\s+|const\s+)*"
                r"(?:(?:unsigned|signed|long|short)\s+)*"
                r"(?:\w[\w:*&<>, ]*?)\s+(\*?\w+)\s*\([^)]*\)\s*(?:const\s*)?(?:override\s*)?(?:noexcept\s*)?[{;]?\s*$",
                stripped
            )
            if m:
                name = m.group(1).lstrip("*")
                # Skip if it looks like a control statement
                if name not in ("if", "else", "for", "while", "switch", "return", "sizeof", "typedef"):
                    result["functions"].append({
                        "name": name,
                        "line": i,
                        "has_doc_comment": prev_doc,
                    })
                    if name == "main":
                        result["has_main"] = True

        # goto detection
        if re.match(r"^\s*goto\s+\w+", stripped):
            result["goto_count"] += 1

        # malloc / calloc / realloc (manual memory management)
        if re.search(r"\b(malloc|calloc|realloc)\s*\(", stripped):
            result["malloc_count"] += 1

        # Doc comments (Doxygen style: /** ... */ or ///)
        if stripped.startswith("/**") or stripped.startswith("///"):
            prev_doc = True
            result["doc_comments"] += 1
        elif stripped.startswith("//") or stripped.startswith("*"):
            pass  # Keep prev_doc if multi-line doc
        else:
            prev_doc = False

        # Complexity: branching
        if re.match(r"^\s*(if|else\s+if|for|while|switch|case|do)\b", stripped):
            result["complexity_estimate"] += 1

    return result


# ── Java 深度分析 ────────────────────────────────────

def _analyze_java(text: str) -> dict:
    """Java 源文件深度分析。"""
    lines = text.split("\n")

    result = {
        "package": None,
        "classes": [],
        "interfaces": [],
        "enums": [],
        "methods": [],
        "fields": [],
        "imports": [],
        "annotations": [],
        "has_main": False,
        "implements_count": 0,
        "extends_count": 0,
        "doc_comments": 0,
        "complexity_estimate": 0,
        "exception_handling": 0,   # try-catch count
        "synchronized_count": 0,
        "is_abstract_class": False,
    }

    prev_doc = False
    in_comment_block = False
    brace_depth = 0
    current_class = None

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # 多行注释追踪
        if "/*" in stripped and "*/" not in stripped:
            in_comment_block = True
            if stripped.startswith("/**"):
                prev_doc = True
                result["doc_comments"] += 1
            continue
        if "*/" in stripped:
            in_comment_block = False
            continue
        if in_comment_block:
            if stripped.startswith("*"):
                result["doc_comments"] += 1
            continue

        brace_depth += stripped.count("{") - stripped.count("}")

        # package
        m = re.match(r"^\s*package\s+([\w.]+)\s*;", stripped)
        if m:
            result["package"] = m.group(1)
            continue

        # import
        m = re.match(r"^\s*import\s+(?:static\s+)?([\w.*]+)\s*;", stripped)
        if m:
            result["imports"].append({"path": m.group(1), "line": i, "is_static": "static" in line})
            continue

        # annotations
        m = re.match(r"^\s*@(\w+)", stripped)
        if m:
            result["annotations"].append({"name": m.group(1), "line": i})
            continue

        # class declaration
        m = re.match(
            r"^\s*(?:public\s+|private\s+|protected\s+)?(?:static\s+)?(?:final\s+)?(?:abstract\s+)?"
            r"class\s+(\w+)(?:<[^>]+>)?\s*(?:extends\s+(\w+))?\s*(?:implements\s+(.+?))?\s*\{?",
            stripped
        )
        if m:
            cls_name = m.group(1)
            result["classes"].append({
                "name": cls_name,
                "line": i,
                "has_doc_comment": prev_doc,
                "extends": m.group(2),
                "implements": [x.strip() for x in m.group(3).split(",")] if m.group(3) else [],
            })
            if m.group(2):
                result["extends_count"] += 1
            if m.group(3):
                result["implements_count"] += len(result["classes"][-1]["implements"])
            if "abstract " in stripped:
                result["is_abstract_class"] = True
            current_class = cls_name
            prev_doc = False
            continue

        # interface declaration
        m = re.match(
            r"^\s*(?:public\s+|private\s+|protected\s+)?interface\s+(\w+)",
            stripped
        )
        if m:
            result["interfaces"].append({
                "name": m.group(1),
                "line": i,
                "has_doc_comment": prev_doc,
            })
            prev_doc = False
            continue

        # enum declaration
        m = re.match(
            r"^\s*(?:public\s+|private\s+|protected\s+)?enum\s+(\w+)",
            stripped
        )
        if m:
            result["enums"].append({"name": m.group(1), "line": i})
            prev_doc = False
            continue

        # method declaration
        m = re.match(
            r"^\s*(?:public|private|protected)?\s*(?:static\s+)?(?:final\s+)?(?:synchronized\s+)?(?:abstract\s+)?"
            r"(?:[\w<>\[\],.? ]+?)\s+(\w+)\s*\([^)]*\)\s*(?:throws\s+[\w,\s]+)?\s*[{;]",
            stripped
        )
        if m:
            name = m.group(1)
            if name not in ("if", "for", "while", "switch", "catch", "return", "new", "class"):
                result["methods"].append({
                    "name": name,
                    "line": i,
                    "has_doc_comment": prev_doc,
                    "is_static": "static " in stripped,
                    "visibility": "public" if "public " in stripped else
                                  "private" if "private " in stripped else
                                  "protected" if "protected " in stripped else "package",
                })
                if name == "main" and "static " in stripped:
                    result["has_main"] = True
                if "synchronized " in stripped:
                    result["synchronized_count"] += 1
            prev_doc = False
            continue

        # try-catch
        if re.match(r"^\s*try\s*\{", stripped) or re.match(r"^\s*catch\s*\(", stripped):
            result["exception_handling"] += 1

        # Javadoc / doc comment lines
        if stripped.startswith("/**"):
            prev_doc = True
            result["doc_comments"] += 1
        elif stripped.startswith("*/") or stripped.startswith("*"):
            pass  # keep prev_doc
        elif stripped.startswith("//"):
            pass
        else:
            prev_doc = False

        # Complexity
        if re.match(r"^\s*(if|else\s+if|for|while|switch|case|do|catch)\b", stripped):
            result["complexity_estimate"] += 1

    return result


# ── 通用分析 (fallback) ──────────────────────────────

def _analyze_generic(text: str, lang: str) -> dict:
    """通用源文件分析（所有语言的基础指标）。"""
    lines = text.split("\n")
    result = {
        "functions": [],
        "todo_count": 0,
        "comment_lines": 0,
        "blank_lines": 0,
        "max_line_length": 0,
        "long_lines": 0,
    }

    # 基础函数检测 (仅在没有专用分析器的语言上提取)
    if lang in ("javascript", "typescript"):
        # 简单 fallback, 前面有深度分析
        pass
    elif lang == "shell":
        pass
    elif lang == "go":
        pass
    elif lang == "rust":
        pass
    elif lang in ("c", "cpp"):
        pass
    elif lang == "java":
        pass
    elif lang == "ruby":
        for i, line in enumerate(lines, 1):
            m = re.match(r"^\s*def\s+(\w+[!?]?)", line)
            if m:
                result["functions"].append({"name": m.group(1), "line": i})
    else:
        # Generic function detection
        for i, line in enumerate(lines, 1):
            if re.match(r"^\s*(export\s+)?(async\s+)?function\s+(\w+)", line):
                m = re.match(r"^\s*(export\s+)?(async\s+)?function\s+(\w+)", line)
                result["functions"].append({"name": m.group(3), "line": i})

    # 通用指标
    comment_prefixes = ("#", "//", "*", "/*", "///", "//!", ";")
    for line in lines:
        stripped = line.strip()
        if not stripped:
            result["blank_lines"] += 1
        elif any(stripped.startswith(p) for p in comment_prefixes):
            result["comment_lines"] += 1
        if re.search(r"TODO|FIXME|HACK|XXX|TEMP", line, re.IGNORECASE):
            result["todo_count"] += 1
        line_len = len(line)
        result["max_line_length"] = max(result["max_line_length"], line_len)
        if line_len > 120:
            result["long_lines"] += 1

    return result


# ── 质量评分 ─────────────────────────────────────────

CODE_SCORING = {
    "dim_structure":     20,   # 模块结构
    "dim_documentation": 20,   # 文档完整性
    "dim_complexity":    20,   # 复杂度
    "dim_style":         20,   # 代码风格
    "dim_practices":     20,   # 工程实践
}


def compute_code_score(file_info: dict) -> dict:
    """计算单个代码文件质量分数 (0-100)。"""
    dims = {}
    lang = file_info.get("language", "")
    loc = file_info.get("line_count", 0)
    py = file_info.get("python_analysis", {})
    js = file_info.get("js_analysis", {})
    go = file_info.get("go_analysis", {})
    sh = file_info.get("shell_analysis", {})
    rs = file_info.get("rust_analysis", {})
    cc = file_info.get("c_analysis", {})
    jv = file_info.get("java_analysis", {})
    generic = file_info.get("generic_analysis", {})

    # ── Helper: 获取所有函数列表 ──
    if lang == "python":
        all_funcs = py.get("functions", [])
    elif lang in ("javascript", "typescript"):
        all_funcs = js.get("functions", [])
    elif lang == "go":
        all_funcs = go.get("functions", []) + go.get("methods", [])
    elif lang == "shell":
        all_funcs = sh.get("functions", [])
    elif lang == "rust":
        all_funcs = rs.get("functions", [])
    elif lang in ("c", "cpp"):
        all_funcs = cc.get("functions", [])
    elif lang == "java":
        all_funcs = jv.get("methods", [])
    else:
        all_funcs = generic.get("functions", [])

    # ── D1: 模块结构 (20 分) ──
    d1 = 0
    if 1 <= len(all_funcs) <= 20:
        d1 += 5
    elif len(all_funcs) > 0:
        d1 += 2
    if 50 <= loc <= 500:
        d1 += 5
    elif 10 <= loc <= 1000:
        d1 += 3
    elif loc > 0:
        d1 += 1
    if all_funcs:
        avg_len = sum(f.get("line_count", 0) for f in all_funcs) / max(len(all_funcs), 1)
        if avg_len <= 30:
            d1 += 5
        elif avg_len <= 60:
            d1 += 3
        else:
            d1 += 1
    else:
        d1 += 3
    # 类 / 结构体数量合理
    type_count = len(py.get("classes", [])) + len(go.get("structs", [])) + \
                 len(js.get("classes", [])) + len(rs.get("structs", [])) + \
                 len(cc.get("structs", [])) + len(cc.get("classes", [])) + \
                 len(jv.get("classes", [])) + len(jv.get("interfaces", []))
    if 0 <= type_count <= 5:
        d1 += 5
    elif type_count <= 10:
        d1 += 3
    else:
        d1 += 1
    # JS/TS: module type consistency
        d1 += 1
    # JS/TS: module type consistency
    if lang in ("javascript", "typescript"):
        if js.get("module_type") == "mixed":
            d1 -= 2
    # Go: package declaration
    if lang == "go" and go.get("package"):
        d1 += 2
    # C/C++: header guard
    if lang in ("c", "cpp") and cc.get("has_header_guard"):
        d1 += 2
    # C++: namespace usage
    if lang == "cpp" and cc.get("namespace"):
        d1 += 1
    # Java: package declaration
    if lang == "java" and jv.get("package"):
        d1 += 2
    dims["structure"] = min(d1, 20)

    # ── D2: 文档完整性 (20 分) ──
    d2 = 0
    if lang == "python":
        if py.get("docstring"):
            d2 += 5
        pub_funcs = [f for f in py.get("functions", []) if not f.get("is_private")]
        if pub_funcs:
            doc_ratio = sum(1 for f in pub_funcs if f.get("has_docstring")) / len(pub_funcs)
            d2 += round(8 * doc_ratio)
        else:
            d2 += 4
        classes = py.get("classes", [])
        if classes:
            cls_doc = sum(1 for c in classes if c.get("has_docstring")) / len(classes)
            d2 += round(4 * cls_doc)
        else:
            d2 += 2
        comment_ratio = generic.get("comment_lines", 0) / max(loc, 1)
        if 0.05 <= comment_ratio <= 0.3:
            d2 += 3
        elif comment_ratio > 0:
            d2 += 1
    elif lang in ("javascript", "typescript"):
        jsdoc = js.get("jsdoc_count", 0)
        func_count = len(js.get("functions", []))
        if func_count > 0:
            jsdoc_ratio = min(jsdoc / func_count, 1.0)
            d2 += round(10 * jsdoc_ratio)
        else:
            d2 += 5
        if lang == "typescript":
            has_types = len(js.get("interfaces", [])) + len(js.get("type_aliases", []))
            d2 += 5 if has_types > 0 else 2
        comment_ratio = generic.get("comment_lines", 0) / max(loc, 1)
        if comment_ratio >= 0.05:
            d2 += 5
        elif comment_ratio > 0:
            d2 += 2
    elif lang == "go":
        exported = [f for f in go.get("functions", []) if f.get("is_exported")]
        exported += [m for m in go.get("methods", []) if m.get("is_exported")]
        exported_types = [s for s in go.get("structs", []) if s.get("is_exported")]
        exported_types += [i for i in go.get("interfaces", []) if i.get("is_exported")]
        all_exported = exported + exported_types
        if all_exported:
            doc_ratio = sum(1 for x in all_exported if x.get("has_doc_comment")) / len(all_exported)
            d2 += round(12 * doc_ratio)
        else:
            d2 += 6
        comment_ratio = generic.get("comment_lines", 0) / max(loc, 1)
        if comment_ratio >= 0.1:
            d2 += 8
        elif comment_ratio >= 0.05:
            d2 += 4
        elif comment_ratio > 0:
            d2 += 2
    elif lang == "rust":
        pub_items = [f for f in rs.get("functions", []) if f.get("is_public")]
        pub_items += [s for s in rs.get("structs", []) if s.get("is_public")]
        if pub_items:
            doc_ratio = sum(1 for x in pub_items if x.get("has_doc_comment")) / len(pub_items)
            d2 += round(12 * doc_ratio)
        else:
            d2 += 6
        doc_count = rs.get("doc_comments", 0)
        if doc_count >= 5:
            d2 += 8
        elif doc_count > 0:
            d2 += 4
    elif lang in ("c", "cpp"):
        doc_count = cc.get("doc_comments", 0)
        funcs = cc.get("functions", [])
        if funcs:
            doc_ratio = sum(1 for f in funcs if f.get("has_doc_comment")) / len(funcs)
            d2 += round(10 * doc_ratio)
        else:
            d2 += 5
        if doc_count >= 5:
            d2 += 5
        elif doc_count > 0:
            d2 += 3
        comment_ratio = generic.get("comment_lines", 0) / max(loc, 1)
        if comment_ratio >= 0.1:
            d2 += 5
        elif comment_ratio >= 0.05:
            d2 += 3
        elif comment_ratio > 0:
            d2 += 1
    elif lang == "java":
        methods = jv.get("methods", [])
        classes = jv.get("classes", [])
        all_items = methods + classes
        if all_items:
            doc_ratio = sum(1 for x in all_items if x.get("has_doc_comment")) / len(all_items)
            d2 += round(12 * doc_ratio)
        else:
            d2 += 6
        doc_count = jv.get("doc_comments", 0)
        if doc_count >= 5:
            d2 += 5
        elif doc_count > 0:
            d2 += 3
        comment_ratio = generic.get("comment_lines", 0) / max(loc, 1)
        if comment_ratio >= 0.05:
            d2 += 3
        elif comment_ratio > 0:
            d2 += 1
    elif lang == "shell":
        comment_ratio = generic.get("comment_lines", 0) / max(loc, 1)
        if comment_ratio >= 0.15:
            d2 += 12
        elif comment_ratio >= 0.08:
            d2 += 8
        elif comment_ratio >= 0.03:
            d2 += 4
        if sh.get("shebang"):
            d2 += 4
        d2 += 4
    else:
        comment_ratio = generic.get("comment_lines", 0) / max(loc, 1)
        if comment_ratio >= 0.1:
            d2 += 10
        elif comment_ratio >= 0.05:
            d2 += 6
        elif comment_ratio > 0:
            d2 += 3
        if generic.get("todo_count", 0) == 0:
            d2 += 5
        elif generic.get("todo_count", 0) <= 3:
            d2 += 2
        d2 += 5
    dims["documentation"] = min(d2, 20)

    # ── D3: 复杂度 (20 分) ──
    d3 = 20
    if lang == "python":
        max_cc = max((f.get("complexity", 0) for f in py.get("functions", [])), default=0)
        avg_cc = (sum(f.get("complexity", 0) for f in py.get("functions", []))
                  / max(len(py.get("functions", [])), 1))
        if max_cc > 20:
            d3 -= 10
        elif max_cc > 10:
            d3 -= 5
        elif max_cc > 7:
            d3 -= 2
        if avg_cc > 10:
            d3 -= 5
        elif avg_cc > 5:
            d3 -= 2
    elif lang in ("javascript", "typescript"):
        cc_val = js.get("complexity_estimate", 0)
        if cc_val > 30:
            d3 -= 10
        elif cc_val > 15:
            d3 -= 5
        elif cc_val > 8:
            d3 -= 2
    elif lang == "go":
        cc_val = go.get("complexity_estimate", 0)
        if cc_val > 25:
            d3 -= 10
        elif cc_val > 12:
            d3 -= 5
        elif cc_val > 6:
            d3 -= 2
    elif lang == "shell":
        cc_val = sh.get("complexity_estimate", 0)
        if cc_val > 20:
            d3 -= 10
        elif cc_val > 10:
            d3 -= 5
    elif lang == "rust":
        cc_val = rs.get("complexity_estimate", 0)
        if cc_val > 25:
            d3 -= 10
        elif cc_val > 12:
            d3 -= 5
    elif lang in ("c", "cpp"):
        cc_val = cc.get("complexity_estimate", 0)
        if cc_val > 30:
            d3 -= 10
        elif cc_val > 15:
            d3 -= 5
        elif cc_val > 8:
            d3 -= 2
        if cc.get("goto_count", 0) > 0:
            d3 -= min(5, cc["goto_count"] * 2)
    elif lang == "java":
        cc_val = jv.get("complexity_estimate", 0)
        if cc_val > 30:
            d3 -= 10
        elif cc_val > 15:
            d3 -= 5
        elif cc_val > 8:
            d3 -= 2
    max_indent = 0
    for line in file_info.get("_text", "").split("\n"):
        if line.strip():
            indent = len(line) - len(line.lstrip())
            max_indent = max(max_indent, indent)
    if max_indent > 24:
        d3 -= 5
    elif max_indent > 16:
        d3 -= 2
    dims["complexity"] = max(0, min(d3, 20))

    # ── D4: 代码风格 (20 分) ──
    d4 = 15
    long_lines = generic.get("long_lines", 0)
    if long_lines == 0:
        d4 += 5
    elif long_lines <= 5:
        d4 += 2
    else:
        d4 -= min(5, long_lines // 5)
    if lang == "python":
        bad_names = 0
        for f in py.get("functions", []):
            if not re.match(r"^_?[a-z][a-z0-9_]*$", f["name"]):
                bad_names += 1
        for c in py.get("classes", []):
            if not re.match(r"^[A-Z][a-zA-Z0-9]*$", c["name"]):
                bad_names += 1
        if bad_names > 0:
            d4 -= min(5, bad_names)
    elif lang == "go":
        bad = 0
        for f in go.get("functions", []):
            n = f["name"]
            if n[0].isupper() and "_" in n:
                bad += 1
        if bad > 0:
            d4 -= min(3, bad)
    elif lang == "shell":
        if sh.get("uses_backticks"):
            d4 -= 2
    elif lang in ("c", "cpp"):
        bad = 0
        for m in cc.get("macros", []):
            if not re.match(r"^[A-Z][A-Z0-9_]*$", m["name"]):
                bad += 1
        if bad > 0:
            d4 -= min(3, bad)
        if cc.get("goto_count", 0) > 0:
            d4 -= 2
    elif lang == "java":
        bad = 0
        for c in jv.get("classes", []):
            if not re.match(r"^[A-Z][a-zA-Z0-9]*$", c["name"]):
                bad += 1
        for m in jv.get("methods", []):
            if not re.match(r"^[a-z][a-zA-Z0-9]*$", m["name"]):
                bad += 1
        if bad > 0:
            d4 -= min(5, bad)
    dims["style"] = max(0, min(d4, 20))

    # ── D5: 工程实践 (20 分) ──
    d5 = 0
    if lang == "python":
        hint_cov = py.get("type_hint_coverage", 0)
        d5 += round(6 * hint_cov)
        if py.get("has_main_guard") or not py.get("functions"):
            d5 += 3
        if not py.get("parse_error"):
            d5 += 3
        todos = generic.get("todo_count", 0)
        if todos == 0:
            d5 += 4
        elif todos <= 2:
            d5 += 2
        star_imports = [i for i in py.get("imports", []) if i.get("module", "").endswith(".*")]
        if not star_imports:
            d5 += 4
        elif len(star_imports) <= 1:
            d5 += 2
    elif lang in ("javascript", "typescript"):
        if js.get("has_strict_mode") or js.get("module_type") == "esm":
            d5 += 4
        if lang == "typescript":
            types_count = len(js.get("interfaces", [])) + len(js.get("type_aliases", []))
            d5 += 4 if types_count > 0 else 1
        else:
            d5 += 2
        todos = generic.get("todo_count", 0)
        if todos == 0:
            d5 += 4
        elif todos <= 2:
            d5 += 2
        if js.get("exports"):
            d5 += 3
        if js.get("module_type") in ("esm", "cjs"):
            d5 += 3
        elif js.get("module_type") is None:
            d5 += 2
    elif lang == "go":
        funcs_count = len(go.get("functions", [])) + len(go.get("methods", []))
        err_checks = go.get("error_checks", 0)
        if funcs_count > 0 and err_checks > 0:
            d5 += 5
        elif err_checks > 0:
            d5 += 3
        if go.get("test_functions"):
            d5 += 5
        if generic.get("todo_count", 0) == 0:
            d5 += 4
        elif generic.get("todo_count", 0) <= 2:
            d5 += 2
        if go.get("has_init"):
            d5 += 3
        if go.get("package"):
            d5 += 3
    elif lang == "shell":
        if sh.get("uses_set_e"):
            d5 += 5
        if sh.get("uses_pipefail"):
            d5 += 3
        if sh.get("uses_set_u"):
            d5 += 3
        if not sh.get("uses_backticks"):
            d5 += 3
        uq = sh.get("unquoted_vars", 0)
        if uq == 0:
            d5 += 4
        elif uq <= 3:
            d5 += 2
        if sh.get("shebang"):
            d5 += 2
    elif lang == "rust":
        if rs.get("unsafe_blocks", 0) == 0:
            d5 += 6
        elif rs.get("unsafe_blocks", 0) <= 1:
            d5 += 3
        if rs.get("doc_comments", 0) >= 3:
            d5 += 4
        if rs.get("traits"):
            d5 += 3
        if generic.get("todo_count", 0) == 0:
            d5 += 4
        elif generic.get("todo_count", 0) <= 2:
            d5 += 2
        d5 += 3
    elif lang in ("c", "cpp"):
        if cc.get("has_header_guard"):
            d5 += 3
        if cc.get("goto_count", 0) == 0:
            d5 += 4
        elif cc.get("goto_count", 0) <= 1:
            d5 += 2
        if cc.get("malloc_count", 0) == 0:
            d5 += 4
        elif cc.get("malloc_count", 0) <= 3:
            d5 += 2
        if lang == "cpp":
            if cc.get("namespace"):
                d5 += 3
            if cc.get("classes"):
                d5 += 2
        if generic.get("todo_count", 0) == 0:
            d5 += 4
        elif generic.get("todo_count", 0) <= 2:
            d5 += 2
    elif lang == "java":
        if jv.get("exception_handling", 0) > 0:
            d5 += 4
        if jv.get("has_main"):
            d5 += 2
        if jv.get("interfaces"):
            d5 += 3
        if jv.get("implements_count", 0) > 0:
            d5 += 3
        if generic.get("todo_count", 0) == 0:
            d5 += 4
        elif generic.get("todo_count", 0) <= 2:
            d5 += 2
        if jv.get("annotations"):
            d5 += 2
        d5 += 2
    else:
        d5 += 10
        if generic.get("todo_count", 0) == 0:
            d5 += 5
        if generic.get("long_lines", 0) <= 3:
            d5 += 5
    dims["practices"] = min(d5, 20)

    total = sum(dims.values())

    penalties = 0
    defects = file_info.get("defects", [])
    for d in defects:
        sev = d.get("severity", "minor")
        if sev == "critical":
            penalties += 5
        elif sev == "major":
            penalties += 3
        else:
            penalties += 1

    total = max(0, min(100, total - penalties))

    if total >= 90:
        grade = "A"
    elif total >= 75:
        grade = "B"
    elif total >= 60:
        grade = "C"
    elif total >= 40:
        grade = "D"
    else:
        grade = "F"

    return {
        "total": total,
        "dimensions": dims,
        "penalties": penalties,
        "grade": grade,
    }

# ── 缺陷检测 ────────────────────────────────────────

def _detect_defects(file_info: dict) -> list:
    """检测代码文件中的缺陷。"""
    defects = []
    py = file_info.get("python_analysis", {})
    js = file_info.get("js_analysis", {})
    go = file_info.get("go_analysis", {})
    sh = file_info.get("shell_analysis", {})
    rs = file_info.get("rust_analysis", {})
    cc = file_info.get("c_analysis", {})
    jv = file_info.get("java_analysis", {})
    generic = file_info.get("generic_analysis", {})
    loc = file_info.get("line_count", 0)
    lang = file_info.get("language", "")

    # 文件过大
    if loc > 1000:
        defects.append({
            "type": "large_file", "severity": "major",
            "message": f"文件过大 ({loc} 行)，建议拆分",
        })

    # Python 专项
    if lang == "python":
        # 语法错误
        if py.get("parse_error"):
            defects.append({
                "type": "syntax_error", "severity": "critical",
                "message": "Python 语法错误",
            })

        # 函数过长
        for f in py.get("functions", []):
            if f.get("line_count", 0) > 100:
                defects.append({
                    "type": "long_function", "severity": "major",
                    "message": f"函数 {f['name']}() 过长 ({f['line_count']} 行)",
                    "line": f["line"],
                })
            elif f.get("line_count", 0) > 50:
                defects.append({
                    "type": "long_function", "severity": "minor",
                    "message": f"函数 {f['name']}() 较长 ({f['line_count']} 行)",
                    "line": f["line"],
                })

        # 高复杂度函数
        for f in py.get("functions", []):
            cc = f.get("complexity", 0)
            if cc > 15:
                defects.append({
                    "type": "high_complexity", "severity": "major",
                    "message": f"函数 {f['name']}() 复杂度过高 (CC={cc})",
                    "line": f["line"],
                })
            elif cc > 10:
                defects.append({
                    "type": "high_complexity", "severity": "minor",
                    "message": f"函数 {f['name']}() 复杂度较高 (CC={cc})",
                    "line": f["line"],
                })

        # 公共函数缺少 docstring
        for f in py.get("functions", []):
            if not f.get("is_private") and not f.get("has_docstring"):
                defects.append({
                    "type": "missing_docstring", "severity": "minor",
                    "message": f"公共函数 {f['name']}() 缺少 docstring",
                    "line": f["line"],
                })

        # 缺少模块 docstring
        if not py.get("docstring") and loc > 20:
            defects.append({
                "type": "missing_module_docstring", "severity": "minor",
                "message": "模块缺少 docstring",
            })

    # JavaScript / TypeScript 专项
    elif lang in ("javascript", "typescript"):
        # 函数过多
        if len(js.get("functions", [])) > 30:
            defects.append({
                "type": "too_many_functions", "severity": "major",
                "message": f"函数过多 ({len(js['functions'])} 个)，建议拆分模块",
            })
        # 混合模块类型
        if js.get("module_type") == "mixed":
            defects.append({
                "type": "mixed_module_system", "severity": "major",
                "message": "混合使用 ESM import 和 CJS require",
            })
        # 缺少 JSDoc
        funcs_without_doc = len(js.get("functions", []))
        jsdoc = js.get("jsdoc_count", 0)
        if funcs_without_doc > 5 and jsdoc < funcs_without_doc * 0.3:
            defects.append({
                "type": "low_jsdoc_coverage", "severity": "minor",
                "message": f"JSDoc 覆盖率低：{jsdoc}/{funcs_without_doc} 函数",
            })
    # ── C/C++ 专项 ──
    elif lang in ("c", "cpp"):
        # goto 使用
        if cc.get("goto_count", 0) > 0:
            defects.append({
                "type": "uses_goto", "severity": "major",
                "message": f"使用了 goto ({cc['goto_count']} 次)，破坏控制流",
            })
        # 大量手动内存管理
        if cc.get("malloc_count", 0) > 5:
            defects.append({
                "type": "excessive_malloc", "severity": "major",
                "message": f"大量手动内存分配 ({cc['malloc_count']} 处)，注意内存泄漏",
            })
        # 缺少头文件保护
        ext = file_info.get("extension", "")
        if ext in (".h", ".hpp", ".hxx") and not cc.get("has_header_guard"):
            defects.append({
                "type": "missing_header_guard", "severity": "major",
                "message": "头文件缺少 include guard (#ifndef / #pragma once)",
            })
        # 函数缺少文档注释
        undoc = [f for f in cc.get("functions", []) if not f.get("has_doc_comment")]
        if len(undoc) > 5:
            defects.append({
                "type": "low_doc_coverage", "severity": "minor",
                "message": f"{len(undoc)} 个函数缺少 Doxygen 文档注释",
            })

    # Java 专项
    elif lang == "java":
        # 缺少 Javadoc
        methods = jv.get("methods", [])
        pub_no_doc = [m for m in methods if m.get("visibility") == "public" and not m.get("has_doc_comment")]
        if pub_no_doc:
            for m in pub_no_doc[:3]:
                defects.append({
                    "type": "missing_javadoc", "severity": "minor",
                    "message": f"公共方法 {m['name']}() 缺少 Javadoc",
                    "line": m["line"],
                })
        # 类缺少 Javadoc
        for c in jv.get("classes", []):
            if not c.get("has_doc_comment"):
                defects.append({
                    "type": "missing_class_javadoc", "severity": "minor",
                    "message": f"类 {c['name']} 缺少 Javadoc",
                    "line": c["line"],
                })
        # 未处理异常
        if jv.get("exception_handling", 0) == 0 and len(methods) > 3:
            defects.append({
                "type": "no_exception_handling", "severity": "minor",
                "message": "未发现 try-catch 异常处理",
            })
        # 方法过多
        if len(methods) > 30:
            defects.append({
                "type": "too_many_methods", "severity": "major",
                "message": f"方法过多 ({len(methods)} 个)，建议拆分类",
            })

    # Go 专项
    elif lang == "go":
        # 导出符号缺少文档注释
        exported = [f for f in go.get("functions", []) if f.get("is_exported")]
        undoc = [f for f in exported if not f.get("has_doc_comment")]
        if undoc:
            for f in undoc[:3]:
                defects.append({
                    "type": "missing_doc_comment", "severity": "minor",
                    "message": f"导出函数 {f['name']} 缺少文档注释",
                    "line": f["line"],
                })
        # error 未处理 (heuristic)
        funcs_count = len(go.get("functions", [])) + len(go.get("methods", []))
        if funcs_count > 3 and go.get("error_checks", 0) == 0:
            defects.append({
                "type": "no_error_handling", "severity": "major",
                "message": "未发现 error 处理 (if err != nil)",
            })

    # Shell 专项
    elif lang == "shell":
        if not sh.get("uses_set_e"):
            defects.append({
                "type": "no_set_e", "severity": "major",
                "message": "缺少 set -e (不会在错误时退出)",
            })
        if sh.get("uses_backticks"):
            defects.append({
                "type": "uses_backticks", "severity": "minor",
                "message": "使用了反引号 (建议改用 $(...))",
            })
        uq = sh.get("unquoted_vars", 0)
        if uq > 5:
            defects.append({
                "type": "unquoted_variables", "severity": "minor",
                "message": f"约 {uq} 处未引用的变量 (可能导致分词问题)",
            })
        if not sh.get("shebang"):
            defects.append({
                "type": "missing_shebang", "severity": "minor",
                "message": "缺少 shebang 行",
            })

    # Rust 专项
    elif lang == "rust":
        if rs.get("unsafe_blocks", 0) > 3:
            defects.append({
                "type": "excessive_unsafe", "severity": "major",
                "message": f"unsafe 块过多 ({rs['unsafe_blocks']} 个)",
            })
        pub_no_doc = [f for f in rs.get("functions", [])
                      if f.get("is_public") and not f.get("has_doc_comment")]
        for f in pub_no_doc[:3]:
            defects.append({
                "type": "missing_doc_comment", "severity": "minor",
                "message": f"公共函数 {f['name']} 缺少 /// 文档注释",
                "line": f["line"],
            })

    # 通用: TODO 过多
    todos = generic.get("todo_count", 0)
    if todos > 5:
        defects.append({
            "type": "excessive_todos", "severity": "major",
            "message": f"TODO/FIXME 过多 ({todos} 个)",
        })
    elif todos > 2:
        defects.append({
            "type": "excessive_todos", "severity": "minor",
            "message": f"TODO/FIXME 较多 ({todos} 个)",
        })

    # 通用: 超长行
    if generic.get("long_lines", 0) > 10:
        defects.append({
            "type": "many_long_lines", "severity": "minor",
            "message": f"{generic['long_lines']} 行超过 120 字符",
        })

    return defects


# ── 主扫描入口 ───────────────────────────────────────

def scan_file(filepath: str) -> dict:
    """扫描单个代码文件。"""
    text = _read_file(filepath)
    if not text:
        return {"file": filepath, "error": "empty_or_unreadable"}

    fname = os.path.basename(filepath)
    ext = os.path.splitext(fname)[1].lower()
    lang = LANG_MAP.get(ext, "other")
    lines = text.split("\n")

    info = {
        "file": fname,
        "path": filepath,
        "language": lang,
        "extension": ext,
        "line_count": len(lines),
        "byte_size": os.path.getsize(filepath),
        "last_modified": datetime.fromtimestamp(
            os.path.getmtime(filepath), tz=timezone.utc
        ).isoformat(),
        "_text": text,  # 临时，评分后删除
    }

    # Python 深度分析
    if lang == "python":
        info["python_analysis"] = _analyze_python(filepath, text)
    # JavaScript / TypeScript 深度分析
    elif lang in ("javascript", "typescript"):
        info["js_analysis"] = _analyze_javascript(text, lang)
    # Go 深度分析
    elif lang == "go":
        info["go_analysis"] = _analyze_go(text)
    elif lang == "rust":
        info["rust_analysis"] = _analyze_rust(text)
    # C/C++ 深度分析
    elif lang in ("c", "cpp"):(text)

    # 通用分析（所有语言基础指标）
    info["generic_analysis"] = _analyze_generic(text, lang)

    # 缺陷检测
    info["defects"] = _detect_defects(info)

    # 质量评分
    score_result = compute_code_score(info)
    info["quality_score"] = score_result["total"]
    info["score_detail"] = score_result

    # 移除临时数据
    del info["_text"]

    return info


def scan_repository(project_dir: str, extensions: list = None,
                    ignore_dirs: set = None) -> dict:
    """扫描整个代码仓库。"""
    log.info(f"扫描代码仓库: {project_dir}")

    if extensions is None:
        extensions = list(LANG_MAP.keys())

    files = []
    total_loc = 0
    lang_stats = Counter()
    errors = []

    for root, dirs, filenames in os.walk(project_dir):
        # 过滤忽略目录
        dirs[:] = [d for d in dirs if not _should_ignore(d, ignore_dirs)]

        for fname in sorted(filenames):
            ext = os.path.splitext(fname)[1].lower()
            if ext not in extensions:
                continue
            if _should_ignore(fname):
                continue

            filepath = os.path.join(root, fname)
            try:
                info = scan_file(filepath)
                # 转为相对路径
                info["relative_path"] = os.path.relpath(filepath, project_dir)
                files.append(info)
                total_loc += info.get("line_count", 0)
                lang_stats[info.get("language", "other")] += 1
                log.info(f"  [{info.get('quality_score', 0):3d}] {info['relative_path']}")
            except Exception as e:
                log.error(f"  扫描失败: {filepath} — {e}")
                errors.append({"file": filepath, "error": str(e)})

    # 汇总统计
    valid = [f for f in files if "error" not in f]
    avg_score = (sum(f.get("quality_score", 0) for f in valid) / max(len(valid), 1))

    report = {
        "scan_time": datetime.now(tz=timezone.utc).isoformat(),
        "project_dir": project_dir,
        "total_files": len(files),
        "total_loc": total_loc,
        "languages": dict(lang_stats),
        "average_score": round(avg_score, 1),
        "files": files,
        "errors": errors,
        "summary": {
            "total_files": len(files),
            "total_loc": total_loc,
            "avg_score": round(avg_score, 1),
            "min_score": min((f.get("quality_score", 100) for f in valid), default=0),
            "max_score": max((f.get("quality_score", 0) for f in valid), default=0),
            "total_defects": sum(len(f.get("defects", [])) for f in valid),
            "files_with_errors": len(errors),
            "languages": dict(lang_stats),
        },
    }

    log.info(f"  扫描完成: {len(files)} 文件, {total_loc} 行, 平均分 {avg_score:.1f}")
    return report


def run():
    """主入口。"""
    from pathlib import Path
    output_dir = cfg("output_dir", "/tmp/openclaw-code-reports")
    project_dir = cfg("project_dir", os.getcwd())
    os.makedirs(output_dir, exist_ok=True)
    report = scan_repository(project_dir)
    out_path = os.path.join(output_dir, "code-scan-report.json")
    save_json(out_path, report)
    log.info(f"报告已保存: {out_path}")
    return report


if __name__ == "__main__":
    run()
