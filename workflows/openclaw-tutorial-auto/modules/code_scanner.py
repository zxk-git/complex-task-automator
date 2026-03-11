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

log = setup_logger("code_scanner")

# ── 支持的语言扩展名 ──
LANG_MAP = {
    ".py":   "python",
    ".js":   "javascript",
    ".ts":   "typescript",
    ".mjs":  "javascript",
    ".jsx":  "javascript",
    ".tsx":  "typescript",
    ".sh":   "shell",
    ".bash": "shell",
    ".zsh":  "shell",
    ".yaml": "yaml",
    ".yml":  "yaml",
    ".json": "json",
    ".md":   "markdown",
    ".toml": "toml",
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


# ── 通用分析 ─────────────────────────────────────────

def _analyze_generic(text: str, lang: str) -> dict:
    """通用源文件分析（非 Python）。"""
    lines = text.split("\n")
    result = {
        "functions": [],
        "todo_count": 0,
        "comment_lines": 0,
        "blank_lines": 0,
        "max_line_length": 0,
        "long_lines": 0,
    }

    # 函数检测 (正则)
    if lang in ("javascript", "typescript"):
        # JS/TS functions
        for i, line in enumerate(lines, 1):
            if re.match(r"^\s*(export\s+)?(async\s+)?function\s+(\w+)", line):
                m = re.match(r"^\s*(export\s+)?(async\s+)?function\s+(\w+)", line)
                result["functions"].append({"name": m.group(3), "line": i})
            elif re.match(r"^\s*(export\s+)?(const|let|var)\s+(\w+)\s*=\s*(async\s+)?\(", line):
                m = re.match(r"^\s*(export\s+)?(const|let|var)\s+(\w+)", line)
                result["functions"].append({"name": m.group(3), "line": i})
    elif lang == "shell":
        for i, line in enumerate(lines, 1):
            m = re.match(r"^\s*(\w+)\s*\(\)\s*\{", line)
            if m:
                result["functions"].append({"name": m.group(1), "line": i})

    # 通用指标
    for line in lines:
        stripped = line.strip()
        if not stripped:
            result["blank_lines"] += 1
        elif stripped.startswith("#") or stripped.startswith("//") or stripped.startswith("*"):
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
    generic = file_info.get("generic_analysis", {})

    # ── D1: 模块结构 (20 分) ──
    d1 = 0
    funcs = py.get("functions", []) or generic.get("functions", [])
    if 1 <= len(funcs) <= 20:
        d1 += 5
    elif len(funcs) > 0:
        d1 += 2
    # 模块大小适中
    if 50 <= loc <= 500:
        d1 += 5
    elif 10 <= loc <= 1000:
        d1 += 3
    elif loc > 0:
        d1 += 1
    # 函数长度合理 (Python)
    if py.get("functions"):
        avg_len = sum(f.get("line_count", 0) for f in py["functions"]) / max(len(py["functions"]), 1)
        if avg_len <= 30:
            d1 += 5
        elif avg_len <= 60:
            d1 += 3
        else:
            d1 += 1
    else:
        d1 += 3
    # 类数量合理
    classes = py.get("classes", [])
    if 0 <= len(classes) <= 5:
        d1 += 5
    elif len(classes) <= 10:
        d1 += 3
    else:
        d1 += 1
    dims["structure"] = min(d1, 20)

    # ── D2: 文档完整性 (20 分) ──
    d2 = 0
    if lang == "python":
        # 模块 docstring
        if py.get("docstring"):
            d2 += 5
        # 函数 docstring 覆盖率
        pub_funcs = [f for f in py.get("functions", []) if not f.get("is_private")]
        if pub_funcs:
            doc_ratio = sum(1 for f in pub_funcs if f.get("has_docstring")) / len(pub_funcs)
            d2 += round(8 * doc_ratio)
        else:
            d2 += 4
        # 类 docstring
        if classes:
            cls_doc = sum(1 for c in classes if c.get("has_docstring")) / len(classes)
            d2 += round(4 * cls_doc)
        else:
            d2 += 2
        # 注释行比例
        comment_ratio = generic.get("comment_lines", 0) / max(loc, 1)
        if 0.05 <= comment_ratio <= 0.3:
            d2 += 3
        elif comment_ratio > 0:
            d2 += 1
    else:
        # 非 Python: 注释密度
        comment_ratio = generic.get("comment_lines", 0) / max(loc, 1)
        if comment_ratio >= 0.1:
            d2 += 10
        elif comment_ratio >= 0.05:
            d2 += 6
        elif comment_ratio > 0:
            d2 += 3
        # 无 TODO
        if generic.get("todo_count", 0) == 0:
            d2 += 5
        elif generic.get("todo_count", 0) <= 3:
            d2 += 2
        d2 += 5  # baseline for non-python
    dims["documentation"] = min(d2, 20)

    # ── D3: 复杂度 (20 分) ──
    d3 = 20  # 起始满分，复杂度高扣分
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
    # 嵌套层级（通用）
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
    d4 = 15  # 基线
    long_lines = generic.get("long_lines", 0)
    if long_lines == 0:
        d4 += 5
    elif long_lines <= 5:
        d4 += 2
    else:
        d4 -= min(5, long_lines // 5)
    # Python: 命名规范
    if lang == "python":
        bad_names = 0
        for f in py.get("functions", []):
            if not re.match(r"^_?[a-z][a-z0-9_]*$", f["name"]):
                bad_names += 1
        for c in py.get("classes", []):
            if not re.match(r"^[A-Z][a-zA-Z0-9]*$", c["name"]):
                bad_names += 1
        if bad_names == 0:
            pass  # keep baseline
        else:
            d4 -= min(5, bad_names)
    dims["style"] = max(0, min(d4, 20))

    # ── D5: 工程实践 (20 分) ──
    d5 = 0
    if lang == "python":
        # Type hints
        hint_cov = py.get("type_hint_coverage", 0)
        d5 += round(6 * hint_cov)
        # Main guard
        if py.get("has_main_guard") or not py.get("functions"):
            d5 += 3
        # No parse errors
        if not py.get("parse_error"):
            d5 += 3
        # TODO count
        todos = generic.get("todo_count", 0)
        if todos == 0:
            d5 += 4
        elif todos <= 2:
            d5 += 2
        # No star imports
        star_imports = [i for i in py.get("imports", []) if i.get("module", "").endswith(".*")]
        if not star_imports:
            d5 += 4
        elif len(star_imports) <= 1:
            d5 += 2
    else:
        # Non-python baseline
        d5 += 10
        if generic.get("todo_count", 0) == 0:
            d5 += 5
        if generic.get("long_lines", 0) <= 3:
            d5 += 5
    dims["practices"] = min(d5, 20)

    total = sum(dims.values())

    # 缺陷惩罚
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

    # 通用分析
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
