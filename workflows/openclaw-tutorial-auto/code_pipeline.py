#!/usr/bin/env python3
"""
code_pipeline.py — 代码优化流水线
====================================
orchestrates: scan → analyze → refine → report

与 tutorial pipeline 共享相同架构，支持独立运行或由统一入口调度。

用法:
  python3 code_pipeline.py /path/to/project       # 全流程
  python3 code_pipeline.py /path --stage scan      # 仅扫描
  python3 code_pipeline.py /path --dry-run         # 干跑
  python3 code_pipeline.py /path --max-files 10    # 限制优化文件数
  python3 code_pipeline.py /path --ext .py .js     # 仅扫描指定扩展名
"""

from datetime import datetime, timezone
import argparse
import json
import os
import sys
import time

_ROOT = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.join(_ROOT, "scripts")
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from modules.code_scanner import scan_repository as code_scan
from modules.code_analyzer import analyze_all as code_analyze
from modules.code_refiner import refine_all as code_refine

try:
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

log = setup_logger("code_pipeline")


class CodePipeline:
    """代码优化流水线。"""

    STAGES = ["scan", "analyze", "refine", "report"]

    def __init__(self, project_dir: str, output_dir: str = None,
                 max_files: int = None, dry_run: bool = False,
                 stages: list = None, extensions: list = None):
        self.project_dir = os.path.abspath(project_dir)
        self.output_dir = output_dir or os.path.join("/tmp", "openclaw-code-reports",
                                                      os.path.basename(self.project_dir))
        self.max_files = max_files
        self.dry_run = dry_run
        self.stages = stages or self.STAGES
        self.extensions = extensions
        self.results = {}
        self.start_time = None

        if dry_run:
            os.environ["DRY_RUN"] = "true"

    def run(self) -> dict:
        """执行代码优化流水线。"""
        self.start_time = time.time()
        os.makedirs(self.output_dir, exist_ok=True)

        log.info("╔════════════════════════════════════════════════╗")
        log.info("║  🔧 代码自动优化流水线 v1.0                    ║")
        log.info("╚════════════════════════════════════════════════╝")
        log.info(f"项目: {self.project_dir}")
        log.info(f"输出: {self.output_dir}")
        log.info(f"阶段: {' → '.join(self.stages)}")
        log.info(f"模式: {'DRY_RUN' if self.dry_run else 'LIVE'}")
        if self.extensions:
            log.info(f"扩展名: {self.extensions}")
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
                self.results[stage] = {"status": "ok", "data": result}
                log.info(f"  ✅ {stage} 完成")
            except Exception as e:
                log.error(f"  ❌ {stage} 失败: {e}")
                import traceback
                traceback.print_exc()
                self.results[stage] = {"status": "error", "error": str(e)}
                if stage in ("scan",):
                    log.error("  关键阶段失败，中断流水线")
                    break
            log.info("")

        return self._generate_final_report()

    def _stage_scan(self):
        """扫描代码仓库。"""
        ext_list = None
        if self.extensions:
            ext_list = self.extensions
        report = code_scan(self.project_dir, extensions=ext_list)
        save_json(os.path.join(self.output_dir, "code-scan-report.json"), report)
        s = report.get("summary", {})
        log.info(f"  文件: {s.get('total_files', 0)}")
        log.info(f"  总行数: {s.get('total_loc', 0)}")
        log.info(f"  平均分: {s.get('avg_score', 0)}")
        log.info(f"  语言: {s.get('languages', {})}")
        log.info(f"  缺陷: {s.get('total_defects', 0)}")
        return report

    def _stage_analyze(self):
        """代码质量分析。"""
        scan_report = self.results.get("scan", {}).get("data")
        report = code_analyze(scan_report)
        save_json(os.path.join(self.output_dir, "code-analysis-report.json"), report)
        log.info(f"  优化建议: {report.get('total_improvements', 0)}")
        log.info(f"  可自动修复: {report.get('auto_fixable', 0)}")
        log.info(f"  按类别: {report.get('by_category', {})}")
        return report

    def _stage_refine(self):
        """代码自动优化。"""
        analysis_report = self.results.get("analyze", {}).get("data")
        scan_report = self.results.get("scan", {}).get("data")
        report = code_refine(analysis_report, scan_report,
                             max_files=self.max_files)
        save_json(os.path.join(self.output_dir, "code-refine-result.json"), report)
        log.info(f"  优化: {report.get('refined', 0)}/{report.get('total_processed', 0)} 文件")
        log.info(f"  修改: {report.get('total_changes', 0)}")
        return report

    def _stage_report(self):
        """生成报告。"""
        report_text = self._generate_summary_report()
        report_path = os.path.join(self.output_dir, "code-pipeline-report.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_text)
        log.info(f"  报告: {report_path}")
        return {"report_path": report_path}

    def _generate_summary_report(self) -> str:
        """Markdown 格式报告。"""
        scan = self.results.get("scan", {}).get("data", {})
        analysis = self.results.get("analyze", {}).get("data", {})
        refine = self.results.get("refine", {}).get("data", {})
        duration = time.time() - self.start_time if self.start_time else 0

        lines = [
            "# 🔧 代码自动优化报告",
            "",
            f"**项目**: `{self.project_dir}`",
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

        s = scan.get("summary", {})
        lines.extend([
            f"| 总文件数 | {s.get('total_files', 0)} |",
            f"| 总行数 | {s.get('total_loc', 0)} |",
            f"| 平均质量分 | {s.get('avg_score', 0)}/100 |",
            f"| 最高分 | {s.get('max_score', 0)} |",
            f"| 最低分 | {s.get('min_score', 0)} |",
            f"| 缺陷总数 | {s.get('total_defects', 0)} |",
        ])

        # 语言分布
        langs = s.get("languages", {})
        if langs:
            lines.extend(["", "## 📁 语言分布", ""])
            for lang, count in sorted(langs.items(), key=lambda x: -x[1]):
                pct = round(count / max(s.get("total_files", 1), 1) * 100)
                bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
                lines.append(f"- **{lang}**: {count} 文件 ({pct}%) {bar}")

        # 优化建议
        if analysis.get("improvements"):
            lines.extend([
                "",
                "## 📋 优化建议摘要",
                "",
                f"- 总计 **{analysis.get('total_improvements', 0)}** 项建议",
                f"- 可自动修复 **{analysis.get('auto_fixable', 0)}** 项 "
                f"({analysis.get('auto_fixable_ratio', 0)*100:.0f}%)",
                "",
            ])

            by_cat = analysis.get("by_category", {})
            if by_cat:
                lines.append("| 类别 | 数量 |")
                lines.append("|------|------|")
                for cat, cnt in sorted(by_cat.items(), key=lambda x: -x[1]):
                    lines.append(f"| {cat} | {cnt} |")

        # 低分文件
        low_score_files = [f for f in scan.get("files", [])
                           if f.get("quality_score", 100) < 60]
        if low_score_files:
            lines.extend([
                "",
                f"## ⚠️ 低分文件 ({len(low_score_files)} 个, < 60 分)",
                "",
                "| 文件 | 分数 | 等级 | 行数 | 缺陷 |",
                "|------|------|------|------|------|",
            ])
            for f in sorted(low_score_files, key=lambda x: x.get("quality_score", 0))[:15]:
                lines.append(
                    f"| {f.get('relative_path', f.get('file', ''))} "
                    f"| {f.get('quality_score', 0)} "
                    f"| {f.get('score_detail', {}).get('grade', '?')} "
                    f"| {f.get('line_count', 0)} "
                    f"| {len(f.get('defects', []))} |"
                )

        # 精炼结果
        if refine.get("results"):
            lines.extend([
                "",
                "## ✅ 自动修复结果",
                "",
            ])
            for r in refine["results"]:
                if r.get("modified"):
                    lines.append(
                        f"- **{r['file']}**: {r.get('changes', 0)} 项修改 "
                        f"({', '.join(r.get('applied', []))})"
                    )

        # 建议
        if analysis.get("recommendations"):
            lines.extend(["", "## 💡 建议", ""])
            for rec in analysis["recommendations"]:
                emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(
                    rec.get("priority", ""), "")
                lines.append(f"- {emoji} {rec['description']}")

        lines.extend([
            "",
            "---",
            "",
            "> 自动生成 by OpenClaw Code Pipeline v1.0",
        ])

        return "\n".join(lines)

    def _generate_final_report(self) -> dict:
        """JSON 最终结果。"""
        duration = time.time() - self.start_time if self.start_time else 0
        report = {
            "pipeline_version": "1.0",
            "mode": "code",
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "project_dir": self.project_dir,
            "duration_seconds": round(duration, 1),
            "dry_run": self.dry_run,
            "stages_executed": list(self.results.keys()),
            "stages_ok": sum(1 for r in self.results.values() if r["status"] == "ok"),
            "stages_failed": sum(1 for r in self.results.values() if r["status"] == "error"),
            "results": {
                k: {"status": v["status"]}
                for k, v in self.results.items()
            },
        }
        save_json(os.path.join(self.output_dir, "code-pipeline-result.json"), report)
        log.info(f"流水线完成: {report['stages_ok']}/{len(self.results)} 阶段成功, "
                  f"耗时 {duration:.1f}s")
        return report


def main():
    """main 的功能描述。
        """
    parser = argparse.ArgumentParser(description="代码自动优化流水线")
    parser.add_argument("project_dir", nargs="?", default=os.getcwd(),
                        help="目标项目目录 (默认: 当前目录)")
    parser.add_argument("--output-dir", type=str, default=None,
                        help="报告输出目录")
    parser.add_argument("--stage", type=str, default=None,
                        help="仅运行指定阶段")
    parser.add_argument("--max-files", type=int, default=None,
                        help="最大优化文件数")
    parser.add_argument("--dry-run", action="store_true",
                        help="干跑模式")
    parser.add_argument("--ext", nargs="+", default=None,
                        help="仅扫描指定扩展名 (如 .py .js)")
    args = parser.parse_args()

    stages = None
    if args.stage:
        if args.stage in CodePipeline.STAGES:
            idx = CodePipeline.STAGES.index(args.stage)
            stages = CodePipeline.STAGES[:idx + 1]
        else:
            print(f"未知阶段: {args.stage}, 可用: {CodePipeline.STAGES}")
            sys.exit(1)

    pipeline = CodePipeline(
        project_dir=args.project_dir,
        output_dir=args.output_dir,
        max_files=args.max_files,
        dry_run=args.dry_run,
        stages=stages,
        extensions=args.ext,
    )
    result = pipeline.run()

    if result.get("stages_failed", 0) > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
