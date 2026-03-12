#!/usr/bin/env python3
"""
pipeline.py — 统一优化流水线调度器
====================================
orchestrates: scan → analyze → collect_refs → refine → format → git → report

替代原有的 daemon.py continuous 模式，提供更清晰的单一入口。

用法:
  python3 pipeline.py                    # 全流程
  python3 pipeline.py --stage scan       # 仅扫描
  python3 pipeline.py --stage analyze    # 仅分析
  python3 pipeline.py --stage refine     # 仅精炼
  python3 pipeline.py --stage format     # 仅格式化
  python3 pipeline.py --max-chapters 5   # 限制优化章节数
  python3 pipeline.py --dry-run          # 干跑模式
"""

from datetime import datetime, timezone
import argparse
import json
import os
import sys
import time

# 确保模块路径
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# ── 导入模块 ──
from modules.tutorial_scanner import scan_repository
from modules.quality_analyzer import analyze_all
from modules.tutorial_refiner import refine_all
from modules.reference_collector import collect_all as collect_references
from modules.formatter import format_all
from modules.link_checker import check_all as check_links, auto_fix_internal as fix_broken_links
from modules.consistency_checker import check_all as check_consistency, auto_fix as fix_consistency
from modules.readability_analyzer import analyze_all as analyze_readability
from modules.optimization_tracker import record_batch, analyze_trends
from modules.compat import setup_logger, cfg, save_json
from base_pipeline import BasePipeline

log = setup_logger("pipeline")

OUTPUT_DIR = cfg("output_dir", os.environ.get(
    "OUTPUT_DIR", "/tmp/openclaw-tutorial-auto-reports"))
PROJECT_DIR = cfg("project_dir", os.environ.get(
    "PROJECT_DIR", "/root/.openclaw/workspace/zxk-private/openclaw-tutorial-auto"))


class Pipeline(BasePipeline):
    """教程优化流水线。"""

    STAGES = [
        "discover", "scan", "analyze", "collect_refs",
        "check_links", "check_consistency", "check_readability",
        "refine", "fix_issues", "format", "track", "update_readme", "git", "report",
    ]
    # 可并行执行的阶段组（组内阶段互相独立，均只依赖 scan 结果）
    PARALLEL_GROUPS = [
        ("collect_refs", "check_links", "check_consistency", "check_readability"),
    ]
    CRITICAL_STAGES = ("discover", "scan", "analyze")
    PIPELINE_NAME = "教程自动优化流水线"
    PIPELINE_VERSION = "5.4"
    PIPELINE_ICON = "📚"

    def __init__(self, max_chapters=None, dry_run=False, stages=None,
                 web_search=True, check_external=False, incremental=False,
                 refine_threshold=None):
        super().__init__(dry_run=dry_run, stages=stages)
        self.max_chapters = max_chapters
        self.web_search = web_search
        self.check_external = check_external
        self.incremental = incremental
        self.refine_threshold = refine_threshold  # 跳过超过此分数的章节
        self.changed_files: set = set()  # 增量模式下的变更文件集合
        self._cache_path = os.path.join(OUTPUT_DIR, "file-cache.json")

    def _save_file_cache(self):
        """保存文件 mtime+size 缓存（用于增量检测）。

        在所有文件修改完成后调用，确保缓存反映最终状态。
        """
        discover_data = self.results.get("discover", {}).get("data", {})
        files = discover_data.get("files", [])
        if not files:
            return

        # 重新读取当前 mtime (文件可能已被 refine/format 修改)
        new_cache = {}
        for f in files:
            path = f["path"]
            if os.path.exists(path):
                new_cache[f["rel_path"]] = {
                    "mtime": os.path.getmtime(path),
                    "size_bytes": os.path.getsize(path),
                }
        save_json(self._cache_path, new_cache)
        log.info(f"  文件缓存已更新: {len(new_cache)} 个文件")

    @property
    def output_dir(self) -> str:
        return OUTPUT_DIR

    @property
    def project_dir(self) -> str:
        return PROJECT_DIR

    @property
    def report_filename(self) -> str:
        return "pipeline-result.json"

    # ──────────────────────────────────────────────────────────
    #  阶段 0: 发现 — 递归扫描教程目录，建立完整文档清单
    # ──────────────────────────────────────────────────────────
    def _stage_discover(self):
        """阶段 0: 递归扫描教程目录，列出所有教程文档。

        目的:
          - 在正式优化前建立完整的文档清单
          - 确保不会遗漏任何教程文档
          - 为后续阶段提供完整的文件路径列表
        """
        import glob

        project_dir = PROJECT_DIR
        log.info(f"  扫描教程目录: {project_dir}")

        # 收集所有 Markdown 文件 (递归)
        all_md_files = []
        tutorial_dirs = [project_dir]

        # 也扫描常见教程子目录
        for subdir_name in ("docs", "tutorial", "tutorials", "guide", "guides", "chapters"):
            subdir = os.path.join(project_dir, subdir_name)
            if os.path.isdir(subdir):
                tutorial_dirs.append(subdir)
                log.info(f"  发现子目录: {subdir_name}/")

        for search_dir in tutorial_dirs:
            for root, dirs, files in os.walk(search_dir):
                # 跳过隐藏目录和常见非教程目录
                dirs[:] = [d for d in dirs if not d.startswith(".") and d not in (
                    "node_modules", "__pycache__", ".git", "assets", "images",
                    "_archive", ".cache", "drafts",
                )]
                for f in sorted(files):
                    if f.endswith(".md") and not f.endswith(".bak"):
                        full_path = os.path.join(root, f)
                        rel_path = os.path.relpath(full_path, project_dir)
                        all_md_files.append({
                            "file": f,
                            "path": full_path,
                            "rel_path": rel_path,
                            "dir": os.path.relpath(root, project_dir),
                            "size_bytes": os.path.getsize(full_path),
                            "mtime": os.path.getmtime(full_path),
                        })

        # 去重 (walk 可能重复包含根目录文件)
        seen_paths = set()
        unique_files = []
        for entry in all_md_files:
            if entry["path"] not in seen_paths:
                seen_paths.add(entry["path"])
                unique_files.append(entry)
        all_md_files = unique_files

        # 分类统计
        import re as _re
        chapter_files = [f for f in all_md_files if _re.match(r"\d+", f["file"])]
        root_chapter_files = [f for f in chapter_files if f["dir"] == "."]
        subdir_chapter_files = [f for f in chapter_files if f["dir"] != "."]
        other_files = [f for f in all_md_files if not _re.match(r"\d+", f["file"])]

        report = {
            "discover_time": datetime.now(tz=timezone.utc).isoformat(),
            "project_dir": project_dir,
            "total_files": len(all_md_files),
            "chapter_files": len(root_chapter_files),
            "subdir_chapter_files": len(subdir_chapter_files),
            "other_files": len(other_files),
            "directories_scanned": [os.path.relpath(d, project_dir) for d in tutorial_dirs],
            "files": all_md_files,
            "chapter_list": [f["rel_path"] for f in root_chapter_files],
            "subdir_chapter_list": [f["rel_path"] for f in subdir_chapter_files],
            "other_list": [f["rel_path"] for f in other_files],
        }

        save_json(os.path.join(OUTPUT_DIR, "discover-report.json"), report)

        # ── 增量检测: 对比缓存，标记变更文件 ──
        if self.incremental:
            cached = {}
            if os.path.exists(self._cache_path):
                try:
                    with open(self._cache_path, encoding="utf-8") as cf:
                        cached = json.load(cf)
                except Exception:
                    cached = {}

            changed = set()
            for f in all_md_files:
                key = f["rel_path"]
                prev = cached.get(key, {})
                if (f["mtime"] != prev.get("mtime") or
                        f["size_bytes"] != prev.get("size_bytes")):
                    changed.add(key)

            # 新文件也算变更
            current_keys = {f["rel_path"] for f in all_md_files}
            new_files = current_keys - set(cached.keys())
            changed |= new_files

            self.changed_files = changed

            report["changed_files"] = sorted(changed)
            report["incremental"] = True
            log.info(f"  增量模式: {len(changed)}/{len(all_md_files)} 个文件有变更")
            if not changed:
                log.info("  🎯 无文件变更，后续阶段将使用快速路径")
        else:
            self.changed_files = {f["rel_path"] for f in all_md_files}
            report["incremental"] = False

        log.info(f"  总文件数: {len(all_md_files)}")
        log.info(f"  根目录章节: {len(root_chapter_files)}")
        log.info(f"  子目录章节: {len(subdir_chapter_files)}")
        log.info(f"  其它文档: {len(other_files)}")
        log.info(f"  扫描目录: {report['directories_scanned']}")

        # 列出所有发现的文件
        for f in all_md_files:
            size_kb = f["size_bytes"] / 1024
            log.info(f"    📄 {f['rel_path']} ({size_kb:.1f} KB)")

        return report

    def _stage_scan(self):
        """阶段 1: 扫描教程仓库 (利用 discover 结果确保完整覆盖)。"""
        # 利用 discover 结果确保扫描完整
        discover_data = self.results.get("discover", {}).get("data", {})
        discovered_files = discover_data.get("files", [])

        if discovered_files:
            log.info(f"  基于 discover 结果扫描 {len(discovered_files)} 个文件")

        report = scan_repository(PROJECT_DIR)

        # 交叉验证：检查 discover 发现但 scan 未覆盖的文件
        if discovered_files:
            scanned_files = {ch.get("file") for ch in report.get("chapters", [])}
            discovered_chapter_files = {f["file"] for f in discovered_files
                                        if f["dir"] == "." and __import__("re").match(r"\d+", f["file"])}
            missed = discovered_chapter_files - scanned_files
            if missed:
                log.warning(f"  ⚠️ discover 发现但 scan 未覆盖的文件: {missed}")
                report.setdefault("global_issues", []).append(
                    f"discover 发现 {len(missed)} 个文件未被 scan 覆盖: {sorted(missed)}"
                )
            report["discover_total"] = len(discovered_files)

        save_json(os.path.join(OUTPUT_DIR, "scan-report.json"), report)
        log.info(f"  章节: {report['summary']['completed']}/{report['expected_chapters']}")
        log.info(f"  平均分: {report['summary']['avg_score']}")
        log.info(f"  总缺陷: {report['summary']['total_defects']}")
        return report

    def _stage_analyze(self):
        """阶段 2: 质量分析。"""
        scan_report = self.results.get("scan", {}).get("data")
        report = analyze_all(scan_report)
        save_json(os.path.join(OUTPUT_DIR, "analysis-report.json"), report)
        log.info(f"  优先级: {report.get('priority_distribution', {})}")
        log.info(f"  总优化项: {report.get('total_improvements', 0)}")
        return report

    def _stage_collect_refs(self):
        """阶段 3: 收集参考来源。"""
        scan_report = self.results.get("scan", {}).get("data")
        report = collect_references(
            scan_report,
            use_web_search=self.web_search and not self.dry_run,
        )
        save_json(os.path.join(OUTPUT_DIR, "references.json"), report)
        log.info(f"  独立来源: {report.get('total_unique_refs', 0)}")
        if report.get('web_search_refs', 0) > 0:
            log.info(f"  Web搜索: {report['web_search_refs']} 条")
        return report

    def _stage_check_links(self):
        """阶段 3b: 断链检测。"""
        scan_report = self.results.get("scan", {}).get("data")
        report = check_links(
            project_dir=PROJECT_DIR,
            check_external=self.check_external and not self.dry_run,
            scan_report=scan_report,
        )
        save_json(os.path.join(OUTPUT_DIR, "link-check-report.json"), report)
        log.info(f"  总链接: {report.get('total_links', 0)}")
        log.info(f"  断链数: {report.get('total_broken', 0)}")
        log.info(f"  健康分: {report.get('health_score', 0)}")
        return report

    def _stage_check_consistency(self):
        """阶段 3c: 跨章节一致性检测。"""
        scan_report = self.results.get("scan", {}).get("data")
        report = check_consistency(
            project_dir=PROJECT_DIR,
            scan_report=scan_report,
        )
        save_json(os.path.join(OUTPUT_DIR, "consistency-report.json"), report)
        log.info(f"  一致性问题: {report.get('total_issues', 0)}")
        log.info(f"  一致性分: {report.get('consistency_score', 0)}")
        return report

    def _stage_check_readability(self):
        """阶段 3d: 阅读时间与难度分析。"""
        scan_report = self.results.get("scan", {}).get("data")
        report = analyze_readability(
            project_dir=PROJECT_DIR,
            scan_report=scan_report,
        )
        save_json(os.path.join(OUTPUT_DIR, "readability-report.json"), report)
        s = report.get("summary", {})
        log.info(f"  总阅读时间: {s.get('total_reading_display', '?')}")
        log.info(f"  难度分布: {s.get('difficulty_distribution', {})}")
        p = report.get("progression", {})
        if p.get("issues"):
            log.warning(f"  递进问题: {len(p['issues'])} 个")
        return report

    # ──────────────────────────────────────────────────────────
    #  阶段 3e: 自动修复检查发现的问题
    # ──────────────────────────────────────────────────────────
    def _stage_fix_issues(self):
        """阶段 3e: 根据检查结果自动修复可修复的问题。

        修复范围:
          - 术语不一致 (open claw → OpenClaw 等)
          - URL 不一致 (http→https, 变体→canonical)
          - 内部断链 (文件名变更导致的链接失效)
        """
        consistency_report = self.results.get("check_consistency", {}).get("data")
        link_report = self.results.get("check_links", {}).get("data")

        total_fixed = 0
        reports = {}

        # 修复一致性问题
        if consistency_report and consistency_report.get("total_issues", 0) > 0:
            log.info(f"  修复一致性问题 ({consistency_report['total_issues']} 个)...")
            c_fix = fix_consistency(
                project_dir=PROJECT_DIR,
                consistency_report=consistency_report,
                dry_run=self.dry_run,
            )
            total_fixed += c_fix.get("total_fixed", 0)
            reports["consistency_fix"] = c_fix
            log.info(f"  术语/URL 修复: {c_fix.get('total_fixed', 0)} 处"
                     f" (跳过: {c_fix.get('skipped', 0)})")
        else:
            log.info("  无一致性问题需要修复")

        # 修复内部断链
        if link_report and link_report.get("total_broken", 0) > 0:
            log.info(f"  修复内部断链 ({link_report['total_broken']} 个)...")
            l_fix = fix_broken_links(
                project_dir=PROJECT_DIR,
                link_report=link_report,
                dry_run=self.dry_run,
            )
            total_fixed += l_fix.get("total_fixed", 0)
            reports["link_fix"] = l_fix
            log.info(f"  链接修复: {l_fix.get('total_fixed', 0)} 处")
        else:
            log.info("  无断链需要修复")

        report = {
            "total_fixed": total_fixed,
            "dry_run": self.dry_run,
            **reports,
        }
        save_json(os.path.join(OUTPUT_DIR, "fix-issues-report.json"), report)
        log.info(f"  总自动修复: {total_fixed} 处")
        return report

    def _stage_refine(self):
        """阶段 4: 内容精炼 (处理所有教程文档，不遗漏)。"""
        analysis_report = self.results.get("analyze", {}).get("data")
        references_report = self.results.get("collect_refs", {}).get("data")

        # 获取 discover 阶段发现的 *根目录* 章节数，用于日志对比
        discover_data = self.results.get("discover", {}).get("data", {})
        discover_total = discover_data.get("chapter_files", 0)  # 仅根目录章节

        # 获取检查阶段结果，传递给 refine 使用
        consistency_report = self.results.get("check_consistency", {}).get("data")
        link_report = self.results.get("check_links", {}).get("data")

        # ── 智能精炼阈值: 跳过已达标章节 ──
        if self.refine_threshold and analysis_report:
            all_chapters = analysis_report.get("chapters", [])
            needs_refine = [
                ch for ch in all_chapters
                if ch.get("current_score", ch.get("quality_score", ch.get("score", 0))) < self.refine_threshold
            ]
            above_threshold = len(all_chapters) - len(needs_refine)
            if above_threshold > 0:
                log.info(f"  智能阈值({self.refine_threshold}): 跳过 {above_threshold} 个已达标章节，精炼 {len(needs_refine)} 个")
                analysis_report = dict(analysis_report)
                analysis_report["chapters"] = needs_refine
            if not needs_refine:
                log.info(f"  智能阈值({self.refine_threshold}): 全部章节已达标，跳过精炼")
                return {
                    "refine_time": None, "total_processed": 0,
                    "refined": 0, "no_change": 0,
                    "threshold_skipped": above_threshold, "results": [],
                    "total_changes": 0,
                }

        # ── 增量模式: 仅精炼变更文件 ──
        incremental_report = None
        if self.incremental and analysis_report:
            all_chapters = analysis_report.get("chapters", [])
            changed_chapters = [
                ch for ch in all_chapters
                if ch.get("file", "") in self.changed_files
            ]
            skipped = len(all_chapters) - len(changed_chapters)
            if skipped > 0:
                log.info(f"  增量模式: 跳过 {skipped} 个未变更章节，仅精炼 {len(changed_chapters)} 个")
                incremental_report = {"skipped_unchanged": skipped}
                analysis_report = dict(analysis_report)
                analysis_report["chapters"] = changed_chapters
            if not changed_chapters:
                log.info("  增量模式: 无变更章节需要精炼")
                return {
                    "refine_time": None,
                    "total_processed": 0,
                    "refined": 0,
                    "no_change": 0,
                    "incremental_skipped": len(all_chapters),
                    "results": [],
                    "total_changes": 0,
                }

        # max_chapters=None 确保处理所有文档，除非用户明确指定了限制
        effective_max = self.max_chapters
        if effective_max is None and discover_total > 0 and not incremental_report:
            log.info(f"  将处理全部 {discover_total} 个根目录章节文档 (无数量限制)")
        elif effective_max:
            log.info(f"  用户指定限制: 最多处理 {effective_max} 个章节")

        report = refine_all(analysis_report, max_chapters=effective_max,
                            references_report=references_report)
        if incremental_report:
            report.update(incremental_report)
        save_json(os.path.join(OUTPUT_DIR, "refine-result.json"), report)

        # 验证完整性 (仅与根目录章节数比较)
        processed = report.get("total_processed", 0)
        if discover_total > 0 and processed < discover_total and effective_max is None and not incremental_report:
            log.warning(f"  ⚠️ 仅处理 {processed}/{discover_total} 个根目录章节，可能存在遗漏")

        log.info(f"  精炼: {report.get('refined', 0)}/{processed}")
        log.info(f"  总修改: {report.get('total_changes', 0)}")
        return report

    def _stage_format(self):
        """阶段 5: 格式统一化。"""
        report = format_all(PROJECT_DIR)
        save_json(os.path.join(OUTPUT_DIR, "format-result.json"), report)
        log.info(f"  修改文件: {report.get('files_changed', 0)}/{report.get('total_files', 0)}")
        log.info(f"  平均格式分: {report.get('average_format_score', 0)}")
        return report

    # ──────────────────────────────────────────────────────────
    #  阶段 5c: 追踪优化历史
    # ──────────────────────────────────────────────────────────
    def _stage_track(self):
        """阶段 5b: 优化历史追踪（增量扫描模式）。"""
        scan_before = self.results.get("scan", {}).get("data")
        refine_result = self.results.get("refine", {}).get("data")

        if not scan_before or not refine_result:
            log.info("  跳过: 缺少 scan 或 refine 数据")
            return {"status": "skipped"}

        # 仅对 refine 实际修改过的文件做增量扫描
        refined_files = set()
        for r in refine_result.get("results", []):
            if r.get("status") == "refined" and r.get("change_count", 0) > 0:
                refined_files.add(r.get("file", ""))

        if not refined_files:
            log.info("  本轮无实际修改，复用原始扫描结果")
            scan_after = scan_before
        else:
            log.info(f"  对 {len(refined_files)} 个已修改文件执行增量扫描...")
            scan_after = scan_repository(PROJECT_DIR)
            # 注: 仍做完整扫描以保持一致性，但记录哪些文件被修改
            scan_after["_incremental_hint"] = list(refined_files)

        # 记录优化前后差异
        import uuid
        run_id = str(uuid.uuid4())[:8]
        entries = record_batch(
            scan_before=scan_before,
            scan_after=scan_after,
            refine_result=refine_result,
            pipeline_run_id=run_id,
        )

        # 生成趋势分析
        trends = analyze_trends()
        save_json(os.path.join(OUTPUT_DIR, "optimization-trends.json"), trends)

        overall = trends.get("overall", {})
        log.info(f"  本轮记录: {len(entries)} 个章节")
        log.info(f"  历史趋势: {overall.get('trend_direction', '?')}")
        log.info(f"  平均提升: {overall.get('avg_improvement', 0):+.1f}")

        return {
            "run_id": run_id,
            "entries_recorded": len(entries),
            "refined_files": list(refined_files),
            "trends": trends,
        }

    # ──────────────────────────────────────────────────────────
    #  阶段 6: 自动更新 README
    # ──────────────────────────────────────────────────────────
    def _stage_update_readme(self):
        """阶段 6: 所有教程文档优化完成后，自动更新 README.md。

        在所有教程文档优化完成后执行，确保 README 反映最新的文档结构。
        包含：项目介绍、教程目录导航、快速开始、示例、教程入口。
        """
        from modules.readme_generator import generate_readme

        scan_report = self.results.get("scan", {}).get("data", {})
        discover_report = self.results.get("discover", {}).get("data", {})
        refine_report = self.results.get("refine", {}).get("data", {})
        analysis_report = self.results.get("analyze", {}).get("data", {})

        report = generate_readme(
            project_dir=PROJECT_DIR,
            scan_report=scan_report,
            discover_report=discover_report,
            refine_report=refine_report,
            analysis_report=analysis_report,
            dry_run=self.dry_run,
        )

        save_json(os.path.join(OUTPUT_DIR, "readme-update-report.json"), report)
        log.info(f"  README 状态: {report.get('status', '?')}")
        log.info(f"  章节目录条目: {report.get('toc_entries', 0)}")
        if report.get("readme_path"):
            log.info(f"  文件路径: {report['readme_path']}")

        return report

    def _stage_git(self):
        """阶段 7: Git 提交推送。"""
        if self.dry_run:
            log.info("  [DRY_RUN] 跳过 Git 操作")
            return {"committed": False, "pushed": False, "dry_run": True}

        try:
            # Import git_ops from our utils/ package
            import importlib.util
            _git_ops_path = os.path.join(_ROOT, "utils", "git_ops.py")
            _spec = importlib.util.spec_from_file_location("git_ops", _git_ops_path)
            _git_ops = importlib.util.module_from_spec(_spec)
            _spec.loader.exec_module(_git_ops)
            result = _git_ops.auto_commit_and_push(cwd=PROJECT_DIR)
            save_json(os.path.join(OUTPUT_DIR, "git-result.json"), result)
            log.info(f"  提交: {'是' if result.get('committed') else '否'}")
            log.info(f"  推送: {'是' if result.get('pushed') else '否'}")
            return result
        except Exception as e:
            log.warning(f"  Git 操作失败 (非致命): {e}")
            return {"committed": False, "pushed": False, "error": str(e)}

    def _stage_report(self):
        """阶段 8: 生成综合报告并推送通知。"""
        report = self._generate_summary_report()
        report_path = os.path.join(OUTPUT_DIR, "pipeline-report.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)
        log.info(f"  报告: {report_path}")

        # ── 增量模式: 保存文件缓存 (所有文件修改已完成) ──
        if self.incremental:
            self._save_file_cache()

        # ── 推送通知 ──
        try:
            from modules.notifier import notify_pipeline
            scan = self.results.get("scan", {}).get("data", {})
            summary = scan.get("summary", {})
            notify_pipeline("tutorial", {
                "version": "5.4",
                "duration": time.time() - self.start_time if self.start_time else 0,
                "summary": summary,
            })
        except Exception as e:
            log.warning(f"  通知发送失败 (非致命): {e}")

        return {"report_path": report_path}

    def _generate_summary_report(self) -> str:
        """生成 Markdown 格式的综合报告。"""
        discover = self.results.get("discover", {}).get("data", {})
        scan = self.results.get("scan", {}).get("data", {})
        analysis = self.results.get("analyze", {}).get("data", {})
        refine = self.results.get("refine", {}).get("data", {})
        fmt = self.results.get("format", {}).get("data", {})
        git = self.results.get("git", {}).get("data", {})
        links = self.results.get("check_links", {}).get("data", {})
        consistency = self.results.get("check_consistency", {}).get("data", {})
        readability = self.results.get("check_readability", {}).get("data", {})
        tracking = self.results.get("track", {}).get("data", {})
        readme_update = self.results.get("update_readme", {}).get("data", {})
        fix_issues = self.results.get("fix_issues", {}).get("data", {})

        duration = time.time() - self.start_time if self.start_time else 0

        lines = [
            "# 📚 教程自动优化报告",
            "",
            f"**时间**: {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"**耗时**: {duration:.1f} 秒",
            f"**模式**: {'DRY_RUN' if self.dry_run else 'LIVE'}",
            "",
            "---",
            "",
            "## 📊 总体概览",
            "",
            "| 指标 | 值 |",
            "|------|-----|",
        ]

        summary = scan.get("summary", {})
        lines.extend([
            f"| 发现文档总数 | {discover.get('total_files', '?')} |",
            f"| 已完成章节 | {summary.get('completed', '?')}/{scan.get('expected_chapters', '?')} |",
            f"| 平均质量分 | {summary.get('avg_score', '?')}/100 |",
            f"| 总字数 | {summary.get('total_words', '?')} |",
            f"| 缺失章节 | {len(scan.get('missing_chapters', []))} |",
            f"| 总缺陷数 | {summary.get('total_defects', '?')} |",
            f"| 断链数 | {links.get('total_broken', '—')} |",
            f"| 链路健康分 | {links.get('health_score', '—')} |",
            f"| 一致性问题 | {consistency.get('total_issues', '—')} |",
            f"| 自动修复 | {fix_issues.get('total_fixed', 0)} 处 |",
            f"| 本轮精炼 | {refine.get('refined', '?')} 章 |",
            f"| 格式修复 | {fmt.get('total_fixes', '?')} 处 |",
            f"| README 更新 | {'是' if readme_update.get('status') == 'updated' else '否'} |",
            f"| Git 提交 | {'是' if git.get('committed') else '否'} |",
        ])

        # 阅读时间与难度
        read_summary = readability.get("summary", {})

        # ── 章节评分仪表板 ──
        chapters = scan.get("chapters", [])
        if chapters:
            lines.extend([
                "",
                "## 🎯 章节评分仪表板",
                "",
                "| # | 章节 | 分数 | 等级 | 缺陷 | 进度条 |",
                "|---|------|------|------|------|--------|",
            ])
            for ch in sorted(chapters, key=lambda c: c.get("number", 0)):
                score = ch.get("quality_score", ch.get("score", 0))
                grade = ch.get("score_detail", {}).get("grade", "")
                defects = len(ch.get("defects", []))
                # 进度条: ████░░ 格式
                full = score // 10
                empty = 10 - full
                bar = "█" * full + "░" * empty
                emoji = "🟢" if score >= 95 else "🟡" if score >= 90 else "🔴"
                title = ch.get("title", ch.get("file", ""))[:30]
                lines.append(
                    f"| {ch.get('number', '?')} | {title} | {emoji} {score} | {grade} | "
                    f"{defects} | `{bar}` |"
                )

            # 分数分布统计
            score_vals = [ch.get("quality_score", ch.get("score", 0)) for ch in chapters]
            if score_vals:
                buckets = {"≥97": 0, "95-96": 0, "93-94": 0, "90-92": 0, "<90": 0}
                for sv in score_vals:
                    if sv >= 97: buckets["≥97"] += 1
                    elif sv >= 95: buckets["95-96"] += 1
                    elif sv >= 93: buckets["93-94"] += 1
                    elif sv >= 90: buckets["90-92"] += 1
                    else: buckets["<90"] += 1
                dist_str = " | ".join(f"{k}: {v}" for k, v in buckets.items() if v)
                lines.extend([
                    "",
                    f"**分数分布**: {dist_str}",
                ])

        if read_summary:
            lines.extend([
                "",
                "## 📖 阅读时间与难度",
                "",
                f"- **总阅读时间**: {read_summary.get('total_reading_display', '?')}",
                f"- **平均阅读**: ~{read_summary.get('avg_reading_time', 0):.0f} 分钟/章",
                f"- **难度分布**: {read_summary.get('difficulty_distribution', {})}",
            ])
            prog = readability.get("progression", {})
            if prog.get("issues"):
                lines.append(f"- **递进问题**: {len(prog['issues'])} 个")
                for issue in prog["issues"][:3]:
                    lines.append(f"  - {issue['message']}")

        # 断链详情
        broken_list = links.get("broken_summary", [])
        if broken_list:
            lines.extend([
                "",
                "## 🔗 断链详情",
                "",
                "| 文件 | 行 | 链接 | 状态 | 问题 |",
                "|------|-----|------|------|------|",
            ])
            for b in broken_list[:15]:
                issues_str = "; ".join(b.get("issues", []))[:50]
                lines.append(
                    f"| {b.get('file', '')} | L{b.get('line', '?')} | "
                    f"`{b.get('target', '')[:40]}` | {b.get('status', '')} | {issues_str} |"
                )

        # 一致性详情
        c_issues = consistency.get("issues", [])
        if c_issues:
            lines.extend([
                "",
                "## 📝 一致性问题",
                "",
            ])
            for ci in c_issues[:10]:
                lines.append(f"- [{ci.get('severity', '')}] {ci.get('message', '')} ({ci.get('file', '')}:L{ci.get('line', '?')})")

        # 优化趋势
        trends_overall = tracking.get("trends", {}).get("overall", {})
        if trends_overall:
            lines.extend([
                "",
                "## 📈 优化趋势",
                "",
                f"- **历史优化次数**: {trends_overall.get('total_optimizations', 0)}",
                f"- **平均提升**: {trends_overall.get('avg_improvement', 0):+.1f} 分/次",
                f"- **趋势方向**: {trends_overall.get('trend_direction', '?')}",
            ])

        # 优化队列
        if analysis.get("optimization_queue"):
            lines.extend([
                "",
                "## 📋 优化队列",
                "",
                "| 章节 | 优先级 | 当前分 | 目标分 | 优化项 |",
                "|------|--------|--------|--------|--------|",
            ])
            for item in analysis["optimization_queue"][:10]:
                emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(item["priority"], "")
                lines.append(
                    f"| 第{item['chapter']}章 | {emoji} {item['priority']} | "
                    f"{item['score']} | {item['target']} | {item['improvements']} |"
                )

        # 精炼结果
        if refine.get("results"):
            lines.extend([
                "",
                "## ✅ 精炼结果",
                "",
            ])
            for r in refine["results"]:
                if r.get("status") == "refined":
                    lines.append(
                        f"- **{r['file']}**: {r.get('change_count', 0)} 项修改, "
                        f"{r.get('words_before', 0)}→{r.get('words_after', 0)} 字"
                    )

        # 建议
        if analysis.get("recommendations"):
            lines.extend([
                "",
                "## 💡 建议",
                "",
            ])
            for rec in analysis["recommendations"]:
                emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(rec.get("priority", ""), "")
                lines.append(f"- {emoji} {rec['description']}")

        lines.extend([
            "",
            "---",
            "",
            "> 自动生成 by OpenClaw Tutorial Auto Pipeline v5.4",
        ])

        return "\n".join(lines)


def main():
    """main 的功能描述。
        """
    parser = argparse.ArgumentParser(description="教程自动优化流水线")
    parser.add_argument("--stage", type=str, default=None,
                        help="仅运行指定阶段 (discover/scan/analyze/collect_refs/refine/format/update_readme/git/report)")
    parser.add_argument("--max-chapters", type=int, default=None,
                        help="最大优化章节数")
    parser.add_argument("--dry-run", action="store_true",
                        help="干跑模式，不写入文件")
    parser.add_argument("--no-web-search", action="store_true",
                        help="禁用 Web 搜索 (默认启用)")
    parser.add_argument("--check-external", action="store_true",
                        help="启用外部 URL 探活检查 (耗时)")
    parser.add_argument("--incremental", action="store_true",
                        help="增量模式: 仅处理自上次运行以来变更的文件")
    args = parser.parse_args()

    # Web 搜索默认启用
    web_search = not getattr(args, "no_web_search", False)

    stages = None
    if args.stage:
        if args.stage in Pipeline.STAGES:
            # 运行指定阶段及其依赖
            stage_idx = Pipeline.STAGES.index(args.stage)
            stages = Pipeline.STAGES[:stage_idx + 1]
        else:
            print(f"未知阶段: {args.stage}")
            print(f"可用阶段: {Pipeline.STAGES}")
            sys.exit(1)

    pipeline = Pipeline(
        max_chapters=args.max_chapters,
        dry_run=args.dry_run,
        stages=stages,
        web_search=web_search,
        check_external=args.check_external,
        incremental=getattr(args, "incremental", False),
    )
    result = pipeline.run()

    # 退出码
    if result.get("stages_failed", 0) > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
