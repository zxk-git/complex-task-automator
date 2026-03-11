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
_MODULES = os.path.join(_ROOT, "modules")
_UTILS = os.path.join(_ROOT, "utils")
_SCRIPTS = os.path.join(_ROOT, "scripts")

if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
# scripts/ must be in path for legacy utils.py
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

# ── 导入模块 ──
from modules.tutorial_scanner import scan_repository
from modules.quality_analyzer import analyze_all
from modules.tutorial_refiner import refine_all
from modules.reference_collector import collect_all as collect_references
from modules.formatter import format_all
from modules.link_checker import check_all as check_links
from modules.consistency_checker import check_all as check_consistency
from modules.readability_analyzer import analyze_all as analyze_readability
from modules.optimization_tracker import record_batch, analyze_trends

# Import from scripts/utils.py (legacy shared utils)
try:
    # scripts/utils.py provides setup_logger, cfg, save_json
    import importlib
    _utils_mod = importlib.import_module("utils")
    setup_logger = _utils_mod.setup_logger
    cfg = _utils_mod.cfg
    save_json = _utils_mod.save_json
except (ImportError, AttributeError):
    import logging
    def setup_logger(name):
        """setup_logger 的功能描述。

            Args:
                name: ...
            """
        logging.basicConfig(level=logging.INFO,
                            format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
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

log = setup_logger("pipeline")

OUTPUT_DIR = cfg("output_dir", os.environ.get(
    "OUTPUT_DIR", "/tmp/openclaw-tutorial-auto-reports"))
PROJECT_DIR = cfg("project_dir", os.environ.get(
    "PROJECT_DIR", "/root/.openclaw/workspace/zxk-private/openclaw-tutorial-auto"))


class Pipeline:
    """教程优化流水线。"""

    STAGES = [
        "scan", "analyze", "collect_refs",
        "check_links", "check_consistency", "check_readability",
        "refine", "format", "track", "git", "report",
    ]

    def __init__(self, max_chapters=None, dry_run=False, stages=None,
                 web_search=False, check_external=False):
        self.max_chapters = max_chapters
        self.dry_run = dry_run
        self.web_search = web_search
        self.check_external = check_external
        self.stages = stages or self.STAGES
        self.results = {}
        self.start_time = None

        if dry_run:
            os.environ["DRY_RUN"] = "true"

    def run(self) -> dict:
        """执行流水线。"""
        self.start_time = time.time()
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        log.info("╔════════════════════════════════════════════════╗")
        log.info("║  📚 教程自动优化流水线 v4.0                    ║")
        log.info("╚════════════════════════════════════════════════╝")
        log.info(f"项目: {PROJECT_DIR}")
        log.info(f"输出: {OUTPUT_DIR}")
        log.info(f"阶段: {' → '.join(self.stages)}")
        log.info(f"模式: {'DRY_RUN' if self.dry_run else 'LIVE'}")
        log.info("")

        for stage in self.stages:
            handler = getattr(self, f"_stage_{stage}", None)
            if not handler:
                log.warning(f"未知阶段: {stage}，跳过")
                continue

            log.info(f"{'='*50}")
            log.info(f"  Stage: {stage.upper()}")
            log.info(f"{'='*50}")

            try:
                result = handler()
                self.results[stage] = {
                    "status": "ok",
                    "data": result,
                    "duration": time.time() - self.start_time,
                }
                log.info(f"  ✅ {stage} 完成")
            except Exception as e:
                log.error(f"  ❌ {stage} 失败: {e}")
                self.results[stage] = {
                    "status": "error",
                    "error": str(e),
                    "duration": time.time() - self.start_time,
                }
                # 非关键阶段失败不中断流水线
                if stage in ("scan", "analyze"):
                    log.error("  关键阶段失败，中断流水线")
                    break

            log.info("")

        # 生成最终报告
        return self._generate_final_report()

    def _stage_scan(self):
        """阶段 1: 扫描教程仓库。"""
        report = scan_repository(PROJECT_DIR)
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

    def _stage_refine(self):
        """阶段 4: 内容精炼。"""
        analysis_report = self.results.get("analyze", {}).get("data")
        references_report = self.results.get("collect_refs", {}).get("data")
        report = refine_all(analysis_report, max_chapters=self.max_chapters,
                            references_report=references_report)
        save_json(os.path.join(OUTPUT_DIR, "refine-result.json"), report)
        log.info(f"  精炼: {report.get('refined', 0)}/{report.get('total_processed', 0)}")
        log.info(f"  总修改: {report.get('total_changes', 0)}")
        return report

    def _stage_format(self):
        """阶段 5: 格式统一化。"""
        report = format_all(PROJECT_DIR)
        save_json(os.path.join(OUTPUT_DIR, "format-result.json"), report)
        log.info(f"  修改文件: {report.get('files_changed', 0)}/{report.get('total_files', 0)}")
        log.info(f"  平均格式分: {report.get('average_format_score', 0)}")
        return report

    def _stage_track(self):
        """阶段 5b: 优化历史追踪。"""
        scan_before = self.results.get("scan", {}).get("data")
        refine_result = self.results.get("refine", {}).get("data")

        if not scan_before or not refine_result:
            log.info("  跳过: 缺少 scan 或 refine 数据")
            return {"status": "skipped"}

        # 二次扫描获取优化后分数
        log.info("  执行二次扫描以获取优化后分数...")
        scan_after = scan_repository(PROJECT_DIR)

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
            "trends": trends,
        }

    def _stage_git(self):
        """阶段 6: Git 提交推送。"""
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
        """阶段 7: 生成综合报告。"""
        report = self._generate_summary_report()
        report_path = os.path.join(OUTPUT_DIR, "pipeline-report.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)
        log.info(f"  报告: {report_path}")
        return {"report_path": report_path}

    def _generate_summary_report(self) -> str:
        """生成 Markdown 格式的综合报告。"""
        scan = self.results.get("scan", {}).get("data", {})
        analysis = self.results.get("analyze", {}).get("data", {})
        refine = self.results.get("refine", {}).get("data", {})
        fmt = self.results.get("format", {}).get("data", {})
        git = self.results.get("git", {}).get("data", {})
        links = self.results.get("check_links", {}).get("data", {})
        consistency = self.results.get("check_consistency", {}).get("data", {})
        readability = self.results.get("check_readability", {}).get("data", {})
        tracking = self.results.get("track", {}).get("data", {})

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
            f"| 已完成章节 | {summary.get('completed', '?')}/{scan.get('expected_chapters', '?')} |",
            f"| 平均质量分 | {summary.get('avg_score', '?')}/100 |",
            f"| 总字数 | {summary.get('total_words', '?')} |",
            f"| 缺失章节 | {len(scan.get('missing_chapters', []))} |",
            f"| 总缺陷数 | {summary.get('total_defects', '?')} |",
            f"| 断链数 | {links.get('total_broken', '—')} |",
            f"| 链路健康分 | {links.get('health_score', '—')} |",
            f"| 一致性问题 | {consistency.get('total_issues', '—')} |",
            f"| 本轮精炼 | {refine.get('refined', '?')} 章 |",
            f"| 格式修复 | {fmt.get('total_fixes', '?')} 处 |",
            f"| Git 提交 | {'是' if git.get('committed') else '否'} |",
        ])

        # 阅读时间与难度
        read_summary = readability.get("summary", {})
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
            "> 自动生成 by OpenClaw Tutorial Auto Pipeline v4.0",
        ])

        return "\n".join(lines)

    def _generate_final_report(self) -> dict:
        """生成最终的 JSON 结果。"""
        duration = time.time() - self.start_time if self.start_time else 0
        report = {
            "pipeline_version": "4.0",
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "duration_seconds": round(duration, 1),
            "dry_run": self.dry_run,
            "stages_executed": list(self.results.keys()),
            "stages_ok": sum(1 for r in self.results.values() if r["status"] == "ok"),
            "stages_failed": sum(1 for r in self.results.values() if r["status"] == "error"),
            "results": {
                k: {"status": v["status"], "duration": v.get("duration", 0)}
                for k, v in self.results.items()
            },
        }

        save_json(os.path.join(OUTPUT_DIR, "pipeline-result.json"), report)
        log.info(f"流水线完成: {report['stages_ok']}/{len(self.results)} 阶段成功, "
                  f"耗时 {duration:.1f}s")

        return report


def main():
    """main 的功能描述。
        """
    parser = argparse.ArgumentParser(description="教程自动优化流水线")
    parser.add_argument("--stage", type=str, default=None,
                        help="仅运行指定阶段 (scan/analyze/collect_refs/refine/format/git/report)")
    parser.add_argument("--max-chapters", type=int, default=None,
                        help="最大优化章节数")
    parser.add_argument("--dry-run", action="store_true",
                        help="干跑模式，不写入文件")
    parser.add_argument("--web-search", action="store_true",
                        help="启用 Web 搜索更新参考来源")
    parser.add_argument("--check-external", action="store_true",
                        help="启用外部 URL 探活检查 (耗时)")
    args = parser.parse_args()

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
        web_search=args.web_search,
        check_external=args.check_external,
    )
    result = pipeline.run()

    # 退出码
    if result.get("stages_failed", 0) > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
