#!/usr/bin/env python3
"""
diff_scanner.py — 增量 diff 扫描器
====================================
基于 git diff 仅分析变更文件，大幅减少全量扫描开销。
支持教程和代码两种模式。

用法:
  # 作为模块导入
  from modules.diff_scanner import scan_diff

  # 独立运行
  python3 -m modules.diff_scanner /path/to/project --since HEAD~3
  python3 -m modules.diff_scanner /path/to/project --since 2026-03-01
  python3 -m modules.diff_scanner /path/to/project --staged  # 仅暂存区
"""

import os
import re
import subprocess
import sys

from modules.compat import setup_logger, cfg, save_json

log = setup_logger("diff_scanner")

# ── 扩展名分类 ──
MD_EXTS = {".md"}
CODE_EXTS = {".py", ".js", ".ts", ".mjs", ".jsx", ".tsx", ".sh",
             ".go", ".rs", ".c", ".h", ".cpp", ".hpp", ".java"}


def _run_git(args: list, cwd: str) -> str:
    """运行 git 命令并返回 stdout。"""
    try:
        r = subprocess.run(
            ["git"] + args, cwd=cwd,
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0:
            log.warning(f"git {' '.join(args)} failed: {r.stderr.strip()}")
            return ""
        return r.stdout
    except Exception as e:
        log.warning(f"git error: {e}")
        return ""


def get_changed_files(
    project_dir: str,
    since: str = "HEAD~1",
    staged: bool = False,
    extensions: list = None,
) -> list[dict]:
    """
    获取 git 变更文件列表。

    Args:
        project_dir: 项目根目录
        since: git 起始点 (commit/tag/date)
        staged: 是否仅检查暂存区
        extensions: 限制文件扩展名列表

    Returns:
        [{"file": 相对路径, "status": A/M/D/R, "ext": 扩展名, "mode": tutorial/code}]
    """
    if staged:
        raw = _run_git(["diff", "--cached", "--name-status"], project_dir)
    else:
        # 支持日期格式 (YYYY-MM-DD)
        if re.match(r"^\d{4}-\d{2}-\d{2}", since):
            raw = _run_git(["log", f"--since={since}", "--name-status",
                            "--pretty=format:"], project_dir)
        else:
            raw = _run_git(["diff", "--name-status", since], project_dir)

    files = []
    seen = set()
    for line in raw.strip().splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue

        status = parts[0][0]  # A, M, D, R
        filepath = parts[-1]   # 重命名取新路径

        if filepath in seen:
            continue
        seen.add(filepath)

        ext = os.path.splitext(filepath)[1].lower()
        if extensions and ext not in extensions:
            continue

        # 忽略已删除的文件
        if status == "D":
            continue

        mode = "unknown"
        if ext in MD_EXTS:
            mode = "tutorial"
        elif ext in CODE_EXTS:
            mode = "code"

        files.append({
            "file": filepath,
            "status": status,
            "ext": ext,
            "mode": mode,
        })

    return files


def scan_diff(
    project_dir: str,
    since: str = "HEAD~1",
    staged: bool = False,
    extensions: list = None,
    output_dir: str = None,
) -> dict:
    """
    增量扫描入口。

    Returns:
        {
            "since": str,
            "total_changed": int,
            "tutorial_files": [...],
            "code_files": [...],
            "summary": {...}
        }
    """
    project_dir = os.path.abspath(project_dir)
    output_dir = output_dir or cfg("output_dir", "/tmp/openclaw-tutorial-auto-reports")

    log.info(f"增量扫描: {project_dir}")
    log.info(f"  基准: {'暂存区' if staged else since}")

    changed = get_changed_files(project_dir, since=since, staged=staged, extensions=extensions)

    tutorial_files = [f for f in changed if f["mode"] == "tutorial"]
    code_files = [f for f in changed if f["mode"] == "code"]
    other_files = [f for f in changed if f["mode"] == "unknown"]

    log.info(f"  变更文件: {len(changed)} (教程: {len(tutorial_files)}, "
             f"代码: {len(code_files)}, 其他: {len(other_files)})")

    # 对教程文件提取章节号
    for f in tutorial_files:
        m = re.match(r"^(\d+)", os.path.basename(f["file"]))
        if m:
            f["chapter"] = int(m.group(1))

    # 对代码文件标注语言
    lang_map = {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".go": "go", ".rs": "rust", ".sh": "shell",
        ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp",
        ".java": "java",
    }
    for f in code_files:
        f["language"] = lang_map.get(f["ext"], "unknown")

    # 统计
    status_counts = {}
    for f in changed:
        s = f["status"]
        status_counts[s] = status_counts.get(s, 0) + 1

    result = {
        "since": "staged" if staged else since,
        "project_dir": project_dir,
        "total_changed": len(changed),
        "tutorial_files": tutorial_files,
        "code_files": code_files,
        "other_files": other_files,
        "summary": {
            "tutorial_count": len(tutorial_files),
            "code_count": len(code_files),
            "other_count": len(other_files),
            "status_distribution": status_counts,
            "chapters_affected": sorted(set(
                f.get("chapter", 0) for f in tutorial_files if "chapter" in f
            )),
            "languages_affected": sorted(set(
                f.get("language", "") for f in code_files
            )),
        },
    }

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        save_json(os.path.join(output_dir, "diff-scan-report.json"), result)

    return result


def filter_scan_report(full_scan: dict, diff_result: dict) -> dict:
    """
    基于 diff 结果过滤全量扫描报告，仅保留变更的文件/章节。

    Args:
        full_scan: 全量扫描报告 (tutorial_scanner/code_scanner 的输出)
        diff_result: diff_scanner.scan_diff 的输出

    Returns:
        过滤后的扫描报告
    """
    changed_files = set()
    for f in diff_result.get("tutorial_files", []):
        changed_files.add(f["file"])
    for f in diff_result.get("code_files", []):
        changed_files.add(f["file"])

    # 教程模式: 过滤 chapters
    if "chapters" in full_scan:
        filtered_chapters = []
        for ch in full_scan["chapters"]:
            ch_file = ch.get("file", "")
            if ch_file in changed_files or os.path.basename(ch_file) in changed_files:
                filtered_chapters.append(ch)
        result = {**full_scan, "chapters": filtered_chapters}
        result["summary"] = {
            **full_scan.get("summary", {}),
            "filtered_from": full_scan.get("summary", {}).get("completed", 0),
            "filtered_to": len(filtered_chapters),
            "incremental": True,
        }
        return result

    # 代码模式: 过滤 files
    if "files" in full_scan:
        filtered_files = []
        for f in full_scan["files"]:
            fp = f.get("relative_path", f.get("file", ""))
            if fp in changed_files or os.path.basename(fp) in changed_files:
                filtered_files.append(f)
        result = {**full_scan, "files": filtered_files}
        result["summary"] = {
            **full_scan.get("summary", {}),
            "filtered_from": full_scan.get("summary", {}).get("total_files", 0),
            "filtered_to": len(filtered_files),
            "incremental": True,
        }
        return result

    return full_scan


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="增量 diff 扫描器")
    parser.add_argument("project_dir", nargs="?",
                        default=cfg("project_dir", os.getcwd()),
                        help="项目目录")
    parser.add_argument("--since", default="HEAD~1",
                        help="Git 起始点 (默认: HEAD~1)")
    parser.add_argument("--staged", action="store_true",
                        help="仅扫描暂存区")
    parser.add_argument("--ext", nargs="+", default=None,
                        help="限制文件扩展名")
    args = parser.parse_args()

    result = scan_diff(
        project_dir=args.project_dir,
        since=args.since,
        staged=args.staged,
        extensions=args.ext,
    )

    import json
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
