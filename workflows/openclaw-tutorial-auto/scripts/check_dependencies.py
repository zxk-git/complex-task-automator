#!/usr/bin/env python3
"""
openclaw-tutorial-auto 项目 — 依赖与链接检查
检查文档中的外部链接、文件引用、跨章引用完整性

重构：统一使用 utils 共享模块。
"""
import re
from datetime import datetime
from pathlib import Path

from utils import (
    find_completed_chapters,
    get_encoding,
    get_output_dir,
    get_project_dir,
    run_git,
    save_json,
    setup_logger,
)

log = setup_logger("check_dependencies")


# ═══════════════════════════════════════════════════════
# GitHub 风格锚点生成
# ═══════════════════════════════════════════════════════

def _heading_to_anchor(heading: str) -> str:
    """
    将标题文本转换为 GitHub 风格锚点：
    小写 → 空格转连字符 → 仅保留字母/数字/连字符/中文
    """
    anchor = heading.strip().lower()
    anchor = anchor.replace(" ", "-")
    # 保留中文、字母、数字、连字符
    anchor = re.sub(r"[^\w\u4e00-\u9fff-]", "", anchor)
    # 多个连续连字符合并
    anchor = re.sub(r"-{2,}", "-", anchor)
    return anchor.strip("-")


# ═══════════════════════════════════════════════════════
# 单文件链接检查
# ═══════════════════════════════════════════════════════

def check_links_in_file(filepath: Path) -> dict:
    """检查单个文件中的链接（外部 / 内部文件引用 / 锚点）"""
    text = filepath.read_text(encoding=get_encoding())
    links = re.findall(r"\[([^\]]*)\]\(([^)]+)\)", text)

    result = {
        "file": filepath.name,
        "total_links": len(links),
        "external_links": [],
        "internal_links": [],
        "broken_internal": [],
        "issues": [],
    }

    proj = filepath.parent

    # 预计算文件中所有标题的锚点（只算一次）
    headings = re.findall(r"^#{1,6}\s+(.+)", text, re.MULTILINE)
    heading_anchors = {_heading_to_anchor(h) for h in headings}

    for label, url in links:
        if url.startswith("http://") or url.startswith("https://"):
            result["external_links"].append({"label": label, "url": url})
        elif url.startswith("#"):
            # 锚点链接 — 用 GitHub 风格锚点校验
            anchor = url[1:]  # 去掉前导 #
            # url 本身已经是锚点格式，直接比较
            if anchor not in heading_anchors:
                result["issues"].append(f"可能的无效锚点: [{label}]({url})")
        else:
            # 内部文件链接
            ref_file = url.split("#")[0]
            ref_path = proj / ref_file
            result["internal_links"].append({"label": label, "url": url})
            if not ref_path.exists():
                result["broken_internal"].append({"label": label, "url": url})
                result["issues"].append(f"文件引用不存在: [{label}]({url})")

    return result


# ═══════════════════════════════════════════════════════
# 跨章节引用检查（上一章 + 下一章）
# ═══════════════════════════════════════════════════════

def check_cross_references(proj: Path, chapter_files: list[Path]) -> list[dict]:
    """检查跨章节 '上一章' / '下一章' 引用一致性"""
    issues: list[dict] = []
    max_chapter = max(
        (int(re.match(r"^(\d+)", f.name).group(1)) for f in chapter_files if re.match(r"^(\d+)", f.name)),
        default=0,
    )

    for f in chapter_files:
        text = f.read_text(encoding=get_encoding())
        m = re.match(r"^(\d+)", f.name)
        if not m:
            continue
        cur_num = int(m.group(1))

        # ── 下一章引用 ──
        next_ref = re.search(r"下一章[：:]\s*(.+)", text)
        if next_ref:
            next_title = next_ref.group(1).strip()
            next_num = cur_num + 1
            next_exists = any(cf.name.startswith(f"{next_num:02d}") for cf in chapter_files)
            if not next_exists and next_num <= max_chapter:
                issues.append({
                    "file": f.name,
                    "type": "missing_next_chapter",
                    "detail": f"引用了下一章 '{next_title}' 但对应章节文件不存在",
                })

        # ── 上一章引用 ──
        prev_ref = re.search(r"上一章[：:]\s*(.+)", text)
        if prev_ref:
            prev_title = prev_ref.group(1).strip()
            prev_num = cur_num - 1
            prev_exists = any(cf.name.startswith(f"{prev_num:02d}") for cf in chapter_files)
            if not prev_exists and prev_num >= 1:
                issues.append({
                    "file": f.name,
                    "type": "missing_prev_chapter",
                    "detail": f"引用了上一章 '{prev_title}' 但对应章节文件不存在",
                })

    return issues


# ═══════════════════════════════════════════════════════
# Git 状态（委托 utils.run_git）
# ═══════════════════════════════════════════════════════

def _check_git_status() -> dict:
    """通过 run_git 获取 git 状态"""
    proj = Path(get_project_dir())
    git_info: dict = {"is_git_repo": (proj / ".git").is_dir()}
    if not git_info["is_git_repo"]:
        return git_info

    res = run_git(["status", "--porcelain"])
    if res["ok"]:
        changes = [l for l in res["stdout"].splitlines() if l.strip()]
        git_info["uncommitted_changes"] = len(changes)
        git_info["changes"] = changes[:20]
    else:
        git_info["error"] = res["stderr"]

    return git_info


# ═══════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════

def run():
    proj = Path(get_project_dir())
    log.info("开始依赖与链接检查: %s", proj)

    # 获取章节文件列表（利用 find_completed_chapters 获取元数据，再拿 Path）
    completed = find_completed_chapters()
    chapter_files = sorted(
        [proj / ch["file"] for ch in completed],
        key=lambda p: p.name,
    )
    log.info("共发现 %d 个章节文件", len(chapter_files))

    results = {
        "timestamp": datetime.now().isoformat(),
        "files_checked": len(chapter_files),
        "link_checks": [],
        "cross_references": [],
        "git_status": {},
        "summary": {},
    }

    total_links = 0
    total_issues = 0
    total_broken = 0

    for f in chapter_files:
        check = check_links_in_file(f)
        results["link_checks"].append(check)
        total_links += check["total_links"]
        total_issues += len(check["issues"])
        total_broken += len(check["broken_internal"])
        if check["issues"]:
            log.warning("%s — %d 个问题", f.name, len(check["issues"]))

    results["cross_references"] = check_cross_references(proj, chapter_files)
    results["git_status"] = _check_git_status()

    xref_issues = len(results["cross_references"])
    results["summary"] = {
        "total_links": total_links,
        "total_broken_internal": total_broken,
        "total_issues": total_issues + xref_issues,
        "cross_reference_issues": xref_issues,
        "all_pass": total_issues == 0 and xref_issues == 0,
    }

    # 保存报告
    out_file = Path(get_output_dir()) / "04-dependency-check.json"
    save_json(out_file, results)
    log.info("报告已保存: %s", out_file)
    log.info(
        "汇总 — 链接: %d | 断链: %d | 跨章问题: %d | 全部通过: %s",
        total_links, total_broken, xref_issues, results["summary"]["all_pass"],
    )
    print(__import__("json").dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run()
