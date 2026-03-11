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
from modules.suggestion_enricher import enrich_suggestions as code_enrich

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

    STAGES = ["scan", "analyze", "enrich", "refine", "report"]

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

    def _stage_enrich(self):
        """为优化建议附加最佳实践参考链接。"""
        analysis_report = self.results.get("analyze", {}).get("data")
        use_web = not self.dry_run  # dry-run 模式不做 web 搜索
        enriched = code_enrich(analysis_report, use_web_search=use_web)
        save_json(os.path.join(self.output_dir, "code-analysis-report.json"), enriched)
        e = enriched.get("enrichment", {})
        log.info(f"  引用: {e.get('total_references', 0)} 条 "
                 f"(静态:{e.get('static_refs', 0)}, Web:{e.get('web_search_refs', 0)})")
        log.info(f"  覆盖: {e.get('unique_templates_enriched', 0)} 种建议类型")
        return enriched

    def _stage_refine(self):
        """代码自动优化。"""
        analysis_report = (self.results.get("enrich", {}).get("data")
                           or self.results.get("analyze", {}).get("data"))
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
        log.info(f"  Markdown 报告: {report_path}")

        # HTML 报告
        html_text = self._generate_html_report()
        html_path = os.path.join(self.output_dir, "code-pipeline-report.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_text)
        log.info(f"  HTML 报告: {html_path}")

        return {"report_path": report_path, "html_report_path": html_path}

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

        # 按语言分组分数表
        files_list = scan.get("files", [])
        if files_list:
            lang_groups = {}
            for f in files_list:
                flang = f.get("language", "unknown")
                lang_groups.setdefault(flang, []).append(f)
            if len(lang_groups) > 1:
                lines.extend(["", "## 📊 按语言质量分数", ""])
                lines.append("| 语言 | 文件数 | 平均分 | 最高分 | 最低分 | 结构 | 文档 | 复杂度 | 风格 | 实践 |")
                lines.append("|------|--------|--------|--------|--------|------|------|--------|------|------|")
                for lang_name, lang_files in sorted(lang_groups.items(), key=lambda x: -len(x[1])):
                    scores = [f.get("quality_score", 0) for f in lang_files]
                    avg_s = round(sum(scores) / max(len(scores), 1), 1)
                    max_s = max(scores) if scores else 0
                    min_s = min(scores) if scores else 0
                    # 按维度平均
                    dim_sums = {"structure": 0, "documentation": 0, "complexity": 0, "style": 0, "practices": 0}
                    for f in lang_files:
                        dims = f.get("score_detail", {}).get("dimensions", {})
                        for d in dim_sums:
                            dim_sums[d] += dims.get(d, 0)
                    n = max(len(lang_files), 1)
                    lines.append(
                        f"| {lang_name} | {len(lang_files)} | {avg_s} | {max_s} | {min_s} "
                        f"| {dim_sums['structure']/n:.1f} | {dim_sums['documentation']/n:.1f} "
                        f"| {dim_sums['complexity']/n:.1f} | {dim_sums['style']/n:.1f} "
                        f"| {dim_sums['practices']/n:.1f} |"
                    )

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
                "## \u2705 自动修复结果",
                "",
            ])
            for r in refine["results"]:
                if r.get("modified"):
                    lines.append(
                        f"- **{r['file']}**: {r.get('changes', 0)} 项修改 "
                        f"({', '.join(r.get('applied', []))})"
                    )

        # 最佳实践参考
        enrichment = analysis.get("enrichment", {})
        if enrichment.get("total_references", 0) > 0:
            lines.extend([
                "",
                f"## \U0001f4da 最佳实践参考 ({enrichment.get('total_references', 0)} 条)",
                "",
                f"- 静态引用: **{enrichment.get('static_refs', 0)}** 条",
                f"- Web 搜索: **{enrichment.get('web_search_refs', 0)}** 条",
                "",
            ])
            seen_urls = set()
            ref_by_type = {}
            for imp in analysis.get("improvements", []):
                for ref in imp.get("references", []):
                    url = ref.get("url", "")
                    if url not in seen_urls:
                        seen_urls.add(url)
                        key = imp.get("type", "other")
                        ref_by_type.setdefault(key, []).append(ref)
            for ttype, trefs in sorted(ref_by_type.items()):
                lines.append(f"**{ttype}**:")
                for ref in trefs[:3]:
                    cred = ref.get("credibility", "?")
                    lines.append(f"- [{ref.get('title', '')}]({ref.get('url', '')}) `[{cred}]`")
                lines.append("")

        # 建议
        if analysis.get("recommendations"):
            lines.extend(["", "## \U0001f4a1 建议", ""])
            for rec in analysis["recommendations"]:
                emoji = {"high": "\U0001f534", "medium": "\U0001f7e1", "low": "\U0001f7e2"}.get(
                    rec.get("priority", ""), "")
                lines.append(f"- {emoji} {rec['description']}")

        lines.extend([
            "",
            "---",
            "",
            "> 自动生成 by OpenClaw Code Pipeline v2.0",
        ])

        return "\n".join(lines)

    def _generate_html_report(self) -> str:
        """HTML 格式报告（含样式和图表）。"""
        scan = self.results.get("scan", {}).get("data", {})
        analysis = (self.results.get("enrich", {}).get("data")
                     or self.results.get("analyze", {}).get("data", {}))
        refine = self.results.get("refine", {}).get("data", {})

        duration = time.time() - self.start_time if self.start_time else 0
        s = scan.get("summary", {})
        files_list = scan.get("files", [])
        ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        # ── 按语言分组 ──
        lang_groups = {}
        for f in files_list:
            lang_groups.setdefault(f.get("language", "unknown"), []).append(f)

        # ── 等级颜色 ──
        def _grade_color(grade):
            return {"A": "#22c55e", "B": "#84cc16", "C": "#eab308",
                    "D": "#f97316", "F": "#ef4444"}.get(grade, "#6b7280")

        def _score_badge(score, grade):
            c = _grade_color(grade)
            return f'<span class="badge" style="background:{c}">{score} ({grade})</span>'

        # ── CSS ──
        css = """
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
       max-width: 1100px; margin: 0 auto; padding: 24px; background: #f8fafc; color: #1e293b; }
h1 { border-bottom: 3px solid #3b82f6; padding-bottom: 8px; }
h2 { color: #1e40af; margin-top: 32px; }
table { border-collapse: collapse; width: 100%; margin: 12px 0; }
th { background: #1e40af; color: #fff; padding: 10px 14px; text-align: left; font-size: 13px; }
td { padding: 8px 14px; border-bottom: 1px solid #e2e8f0; font-size: 13px; }
tr:hover td { background: #f1f5f9; }
.badge { display: inline-block; padding: 2px 10px; border-radius: 12px; color: #fff;
         font-weight: 600; font-size: 12px; }
.card { background: #fff; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,.1);
        padding: 20px; margin: 16px 0; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; }
.stat-card { background: #fff; border-radius: 10px; padding: 16px; text-align: center;
             box-shadow: 0 1px 3px rgba(0,0,0,.08); }
.stat-val { font-size: 28px; font-weight: 700; color: #1e40af; }
.stat-label { font-size: 12px; color: #64748b; margin-top: 4px; }
.bar-container { display: flex; align-items: center; gap: 8px; }
.bar { height: 14px; border-radius: 7px; }
.dim-bar { display: inline-block; height: 10px; border-radius: 5px; background: #3b82f6; }
.tag { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px;
       background: #e0e7ff; color: #3730a3; margin: 2px; }
.sev-critical { color: #dc2626; font-weight: 700; }
.sev-major { color: #ea580c; font-weight: 600; }
.sev-minor { color: #ca8a04; }
footer { margin-top: 40px; padding-top: 16px; border-top: 1px solid #e2e8f0;
         font-size: 12px; color: #94a3b8; text-align: center; }
"""

        # ── 构建 HTML ──
        h = [f"<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>",
             f"<meta name='viewport' content='width=device-width,initial-scale=1'>",
             f"<title>代码优化报告 — {os.path.basename(self.project_dir)}</title>",
             f"<style>{css}</style></head><body>"]

        # 标题
        h.append(f"<h1>🔧 代码自动优化报告</h1>")
        h.append(f"<p><strong>项目</strong>: <code>{self.project_dir}</code> &nbsp; "
                 f"<strong>时间</strong>: {ts} &nbsp; "
                 f"<strong>耗时</strong>: {duration:.1f}s &nbsp; "
                 f"<strong>模式</strong>: {'DRY_RUN' if self.dry_run else 'LIVE'}</p>")

        # 概览卡片
        h.append('<div class="grid">')
        stats = [
            ("📄", "文件数", s.get("total_files", 0)),
            ("📏", "总行数", s.get("total_loc", 0)),
            ("⭐", "平均分", f'{s.get("avg_score", 0)}/100'),
            ("🏆", "最高分", s.get("max_score", 0)),
            ("⚠️", "最低分", s.get("min_score", 0)),
            ("🐛", "缺陷数", s.get("total_defects", 0)),
        ]
        for emoji, label, val in stats:
            h.append(f'<div class="stat-card"><div class="stat-val">{val}</div>'
                     f'<div class="stat-label">{emoji} {label}</div></div>')
        h.append('</div>')

        # 语言分布
        langs = s.get("languages", {})
        if langs:
            total_files = max(s.get("total_files", 1), 1)
            colors = ["#3b82f6", "#22c55e", "#eab308", "#ef4444", "#8b5cf6",
                      "#ec4899", "#14b8a6", "#f97316", "#6366f1", "#06b6d4"]
            h.append('<h2>📁 语言分布</h2><div class="card">')
            for i, (lang, count) in enumerate(sorted(langs.items(), key=lambda x: -x[1])):
                pct = round(count / total_files * 100)
                c = colors[i % len(colors)]
                h.append(f'<div class="bar-container"><strong style="min-width:100px">{lang}</strong>'
                         f'<div class="bar" style="width:{max(pct,2)}%;background:{c}"></div>'
                         f'<span>{count} ({pct}%)</span></div>')
            h.append('</div>')

        # 按语言质量分数表
        if len(lang_groups) > 1:
            h.append('<h2>📊 按语言质量分数</h2><div class="card"><table>')
            h.append('<tr><th>语言</th><th>文件数</th><th>平均分</th><th>最高</th><th>最低</th>'
                     '<th>结构</th><th>文档</th><th>复杂度</th><th>风格</th><th>实践</th></tr>')
            for lang_name, lang_files in sorted(lang_groups.items(), key=lambda x: -len(x[1])):
                scores = [f.get("quality_score", 0) for f in lang_files]
                avg_s = round(sum(scores) / max(len(scores), 1), 1)
                max_s = max(scores) if scores else 0
                min_s = min(scores) if scores else 0
                dim_sums = {"structure": 0, "documentation": 0, "complexity": 0,
                            "style": 0, "practices": 0}
                for f in lang_files:
                    dims = f.get("score_detail", {}).get("dimensions", {})
                    for d in dim_sums:
                        dim_sums[d] += dims.get(d, 0)
                n = max(len(lang_files), 1)
                dim_cells = "".join(
                    f'<td><div class="dim-bar" style="width:{dim_sums[d]/n/20*80}px"></div> '
                    f'{dim_sums[d]/n:.1f}/20</td>'
                    for d in ["structure", "documentation", "complexity", "style", "practices"]
                )
                # avg grade
                avg_grade = "A" if avg_s >= 90 else "B" if avg_s >= 75 else "C" if avg_s >= 60 else "D" if avg_s >= 40 else "F"
                h.append(f'<tr><td><strong>{lang_name}</strong></td><td>{len(lang_files)}</td>'
                         f'<td>{_score_badge(avg_s, avg_grade)}</td>'
                         f'<td>{max_s}</td><td>{min_s}</td>{dim_cells}</tr>')
            h.append('</table></div>')

        # 文件详情表
        if files_list:
            h.append('<h2>📋 文件质量详情</h2><div class="card"><table>')
            h.append('<tr><th>文件</th><th>语言</th><th>行数</th><th>分数</th>'
                     '<th>结构</th><th>文档</th><th>复杂度</th><th>风格</th><th>实践</th><th>缺陷</th></tr>')
            for f in sorted(files_list, key=lambda x: x.get("quality_score", 0)):
                rp = f.get("relative_path", f.get("file", ""))
                score = f.get("quality_score", 0)
                grade = f.get("score_detail", {}).get("grade", "?")
                dims = f.get("score_detail", {}).get("dimensions", {})
                defect_count = len(f.get("defects", []))
                dim_cells = "".join(
                    f'<td>{dims.get(d, 0)}</td>'
                    for d in ["structure", "documentation", "complexity", "style", "practices"]
                )
                h.append(f'<tr><td><code>{rp}</code></td><td>{f.get("language", "")}</td>'
                         f'<td>{f.get("line_count", 0)}</td><td>{_score_badge(score, grade)}</td>'
                         f'{dim_cells}<td>{defect_count}</td></tr>')
            h.append('</table></div>')

        # 优化建议
        if analysis.get("improvements"):
            h.append(f'<h2>💡 优化建议 ({analysis.get("total_improvements", 0)} 项)</h2>')
            h.append(f'<p>可自动修复: <strong>{analysis.get("auto_fixable", 0)}</strong> 项 '
                     f'({analysis.get("auto_fixable_ratio", 0)*100:.0f}%)</p>')
            # 按类别
            by_cat = analysis.get("by_category", {})
            if by_cat:
                h.append('<div class="card"><table><tr><th>类别</th><th>数量</th></tr>')
                for cat, cnt in sorted(by_cat.items(), key=lambda x: -x[1]):
                    h.append(f'<tr><td>{cat}</td><td>{cnt}</td></tr>')
                h.append('</table></div>')

        # 自动修复结果
        if refine.get("results"):
            modified = [r for r in refine["results"] if r.get("modified")]
            if modified:
                h.append(f'<h2>✅ 自动修复结果 ({len(modified)} 文件)</h2><div class="card"><table>')
                h.append('<tr><th>文件</th><th>修改数</th><th>应用</th></tr>')
                for r in modified:
                    applied = ", ".join(f'<span class="tag">{a}</span>' for a in r.get("applied", []))
                    h.append(f'<tr><td><code>{r["file"]}</code></td>'
                             f'<td>{r.get("changes", 0)}</td><td>{applied}</td></tr>')
                h.append('</table></div>')

        # 缺陷详情
        all_defects = []
        for f in files_list:
            for d in f.get("defects", []):
                all_defects.append({**d, "_file": f.get("relative_path", f.get("file", ""))})
        if all_defects:
            h.append(f'<h2>🐛 缺陷详情 ({len(all_defects)} 个)</h2><div class="card"><table>')
            h.append('<tr><th>文件</th><th>类型</th><th>严重度</th><th>描述</th></tr>')
            for d in sorted(all_defects, key=lambda x: {"critical": 0, "major": 1, "minor": 2}.get(x.get("severity", "minor"), 3))[:30]:
                sev_cls = f'sev-{d.get("severity", "minor")}'
                h.append(f'<tr><td><code>{d["_file"]}</code></td>'
                         f'<td>{d.get("type", "")}</td>'
                         f'<td class="{sev_cls}">{d.get("severity", "")}</td>'
                         f'<td>{d.get("message", "")}</td></tr>')
            h.append('</table></div>')

        h.append(f'<footer>自动生成 by OpenClaw Code Pipeline v1.0 | {ts}</footer>')
        h.append('</body></html>')
        return "\n".join(h)

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
