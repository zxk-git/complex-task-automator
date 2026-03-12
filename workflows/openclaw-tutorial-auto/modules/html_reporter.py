#!/usr/bin/env python3
"""
modules/html_reporter.py — 静态 HTML 报告生成器
====================================================
将 Pipeline 运行结果生成独立的 HTML 报告文件，内嵌 ECharts 图表。

功能:
  - 分数分布雷达图
  - 章节得分柱状图
  - 维度热力图
  - 趋势折线图
  - 扩写建议面板

用法:
  from modules.html_reporter import generate_html_report
  generate_html_report(pipeline_results, output_path)
"""

import json
import os
from datetime import datetime, timezone
from typing import Any

from modules.compat import setup_logger

log = setup_logger("html_reporter")


def generate_html_report(
    pipeline_results: dict,
    scan_report: dict,
    output_path: str,
    expansion_report: dict = None,
    readability_report: dict = None,
    title: str = "教程自动优化报告",
) -> dict:
    """生成静态 HTML 报告。

    Args:
        pipeline_results: Pipeline 的 results 字典
        scan_report: tutorial_scanner 的扫描结果
        output_path: HTML 文件输出路径
        expansion_report: LLM 扩写分析结果 (可选)
        readability_report: 可读性分析结果 (可选)
        title: 报告标题

    Returns:
        dict: 生成结果 {"path": ..., "size": ...}
    """
    chapters = scan_report.get("chapters", [])
    summary = scan_report.get("summary", {})

    # 准备图表数据
    chart_data = _prepare_chart_data(chapters, summary)

    # 生成 HTML
    html = _render_html(
        title=title,
        chart_data=chart_data,
        chapters=chapters,
        summary=summary,
        pipeline_results=pipeline_results,
        expansion_report=expansion_report,
        readability_report=readability_report,
    )

    # 写入文件
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    size = os.path.getsize(output_path)
    log.info(f"  HTML 报告已生成: {output_path} ({size // 1024} KB)")

    return {"path": output_path, "size": size}


def _prepare_chart_data(chapters: list, summary: dict) -> dict:
    """从扫描结果提取图表数据。"""
    # 1. 章节得分列表
    scores = []
    labels = []
    for ch in sorted(chapters, key=lambda c: c.get("number", 0)):
        scores.append(ch.get("quality_score", ch.get("score", 0)))
        labels.append(f"ch{ch.get('number', '?'):02d}")

    # 2. 维度平均分 (用于雷达图)
    dim_totals = {}
    dim_counts = {}
    for ch in chapters:
        dims = ch.get("score_detail", {}).get("dimensions", {})
        for dim, val in dims.items():
            dim_totals[dim] = dim_totals.get(dim, 0) + val
            dim_counts[dim] = dim_counts.get(dim, 0) + 1

    dim_avg = {k: round(dim_totals[k] / dim_counts[k], 1)
               for k in dim_totals}

    # 3. 分数分布 (用于饼图)
    buckets = {"100": 0, "95-99": 0, "90-94": 0, "<90": 0}
    for s in scores:
        if s == 100:
            buckets["100"] += 1
        elif s >= 95:
            buckets["95-99"] += 1
        elif s >= 90:
            buckets["90-94"] += 1
        else:
            buckets["<90"] += 1

    # 4. 字数分布
    word_counts = [ch.get("word_count", 0) for ch in chapters]

    return {
        "scores": scores,
        "labels": labels,
        "dim_avg": dim_avg,
        "buckets": buckets,
        "word_counts": word_counts,
        "total_chapters": len(chapters),
        "avg_score": summary.get("avg_score", 0),
        "min_score": summary.get("min_score", 0),
        "max_score": summary.get("max_score", 0),
    }


def _render_html(
    title: str,
    chart_data: dict,
    chapters: list,
    summary: dict,
    pipeline_results: dict,
    expansion_report: dict = None,
    readability_report: dict = None,
) -> str:
    """渲染完整 HTML 报告。"""
    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    scores_json = json.dumps(chart_data["scores"])
    labels_json = json.dumps(chart_data["labels"])
    dim_avg_json = json.dumps(chart_data["dim_avg"])
    buckets_json = json.dumps(chart_data["buckets"])
    word_counts_json = json.dumps(chart_data["word_counts"])

    # 维度名映射
    dim_name_map = {
        "content_depth": "内容深度",
        "structure": "结构",
        "code_quality": "代码质量",
        "pedagogy": "教学性",
        "references": "参考来源",
        "readability": "可读性",
    }
    dim_names_json = json.dumps(dim_name_map, ensure_ascii=False)

    # 章节表格行
    table_rows = ""
    for ch in sorted(chapters, key=lambda c: c.get("number", 0)):
        score = ch.get("quality_score", ch.get("score", 0))
        grade = ch.get("score_detail", {}).get("grade", "")
        defects = len(ch.get("defects", []))
        words = ch.get("word_count", 0)
        ch_title = ch.get("title", ch.get("file", ""))
        color = "#52c41a" if score >= 95 else "#faad14" if score >= 90 else "#f5222d"
        table_rows += f"""
        <tr>
          <td>{ch.get("number", "?")}</td>
          <td>{_html_escape(ch_title)}</td>
          <td style="color:{color};font-weight:bold">{score}</td>
          <td>{grade}</td>
          <td>{defects}</td>
          <td>{words:,}</td>
        </tr>"""

    # 扩写建议面板
    expansion_html = ""
    if expansion_report and expansion_report.get("chapters"):
        expansion_html = '<div class="panel"><h2>📝 扩写建议</h2><table><tr><th>章节</th><th>类型</th><th>优先级</th><th>建议</th></tr>'
        for ch_sug in expansion_report["chapters"][:10]:
            for sug in ch_sug.get("suggestions", [])[:3]:
                pcolor = {"high": "#f5222d", "medium": "#faad14", "low": "#52c41a"}.get(sug.get("priority"), "#999")
                expansion_html += f"""
                <tr>
                  <td>ch{ch_sug["chapter"]:02d}</td>
                  <td>{sug["type"]}</td>
                  <td style="color:{pcolor}">{sug.get("priority","")}</td>
                  <td>{_html_escape(sug.get("prompt","")[:120])}</td>
                </tr>"""
        expansion_html += "</table></div>"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{_html_escape(title)}</title>
  <script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
  <style>
    :root {{ --bg: #f5f5f5; --card: #fff; --text: #333; --border: #e8e8e8; }}
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
           background: var(--bg); color: var(--text); padding: 20px; }}
    .header {{ text-align: center; padding: 30px 0; }}
    .header h1 {{ font-size: 28px; margin-bottom: 8px; }}
    .header .meta {{ color: #999; font-size: 14px; }}
    .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
              gap: 16px; margin: 20px 0; }}
    .stat-card {{ background: var(--card); border-radius: 8px; padding: 20px; text-align: center;
                  box-shadow: 0 1px 3px rgba(0,0,0,.1); }}
    .stat-card .value {{ font-size: 32px; font-weight: bold; color: #1890ff; }}
    .stat-card .label {{ font-size: 13px; color: #999; margin-top: 4px; }}
    .charts {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
               gap: 20px; margin: 20px 0; }}
    .chart-card {{ background: var(--card); border-radius: 8px; padding: 20px;
                   box-shadow: 0 1px 3px rgba(0,0,0,.1); }}
    .chart-card h3 {{ margin-bottom: 12px; font-size: 16px; }}
    .chart {{ width: 100%; height: 350px; }}
    .panel {{ background: var(--card); border-radius: 8px; padding: 20px; margin: 20px 0;
              box-shadow: 0 1px 3px rgba(0,0,0,.1); }}
    .panel h2 {{ margin-bottom: 16px; font-size: 18px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid var(--border); text-align: left; }}
    th {{ background: #fafafa; font-weight: 600; }}
    tr:hover {{ background: #f0f7ff; }}
    .footer {{ text-align: center; padding: 30px 0; color: #999; font-size: 12px; }}
    @media (max-width: 768px) {{
      .charts {{ grid-template-columns: 1fr; }}
      .stats {{ grid-template-columns: repeat(2, 1fr); }}
    }}
  </style>
</head>
<body>
  <div class="header">
    <h1>📚 {_html_escape(title)}</h1>
    <div class="meta">{now} · Pipeline v5.5</div>
  </div>

  <div class="stats">
    <div class="stat-card">
      <div class="value">{chart_data["total_chapters"]}</div>
      <div class="label">章节总数</div>
    </div>
    <div class="stat-card">
      <div class="value">{chart_data["avg_score"]}</div>
      <div class="label">平均分</div>
    </div>
    <div class="stat-card">
      <div class="value">{chart_data["min_score"]}</div>
      <div class="label">最低分</div>
    </div>
    <div class="stat-card">
      <div class="value">{chart_data["max_score"]}</div>
      <div class="label">最高分</div>
    </div>
    <div class="stat-card">
      <div class="value">{summary.get("total_words", 0):,}</div>
      <div class="label">总字数</div>
    </div>
    <div class="stat-card">
      <div class="value">{summary.get("total_defects", 0)}</div>
      <div class="label">总缺陷</div>
    </div>
  </div>

  <div class="charts">
    <div class="chart-card">
      <h3>📊 章节得分分布</h3>
      <div id="scoreBar" class="chart"></div>
    </div>
    <div class="chart-card">
      <h3>🎯 分数区间分布</h3>
      <div id="scorePie" class="chart"></div>
    </div>
    <div class="chart-card">
      <h3>🕸️ 维度均分雷达</h3>
      <div id="dimRadar" class="chart"></div>
    </div>
    <div class="chart-card">
      <h3>📏 章节字数分布</h3>
      <div id="wordBar" class="chart"></div>
    </div>
  </div>

  <div class="panel">
    <h2>🎯 章节评分明细</h2>
    <table>
      <tr><th>#</th><th>章节</th><th>分数</th><th>等级</th><th>缺陷</th><th>字数</th></tr>
      {table_rows}
    </table>
  </div>

  {expansion_html}

  <div class="footer">
    Generated by OpenClaw Tutorial Auto Pipeline v5.5 · ECharts 5
  </div>

  <script>
    const scores = {scores_json};
    const labels = {labels_json};
    const dimAvg = {dim_avg_json};
    const buckets = {buckets_json};
    const wordCounts = {word_counts_json};
    const dimNames = {dim_names_json};

    // 1. 章节得分柱状图
    const scoreBar = echarts.init(document.getElementById('scoreBar'));
    scoreBar.setOption({{
      tooltip: {{ trigger: 'axis' }},
      xAxis: {{ type: 'category', data: labels, axisLabel: {{ rotate: 45 }} }},
      yAxis: {{ type: 'value', min: 80, max: 100 }},
      series: [{{
        type: 'bar',
        data: scores.map(s => ({{
          value: s,
          itemStyle: {{ color: s >= 95 ? '#52c41a' : s >= 90 ? '#faad14' : '#f5222d' }}
        }})),
        label: {{ show: true, position: 'top', fontSize: 10 }}
      }}]
    }});

    // 2. 分数区间饼图
    const scorePie = echarts.init(document.getElementById('scorePie'));
    scorePie.setOption({{
      tooltip: {{ trigger: 'item' }},
      legend: {{ bottom: 10 }},
      series: [{{
        type: 'pie',
        radius: ['35%', '65%'],
        data: Object.entries(buckets).map(([k, v]) => ({{ name: k, value: v }})),
        itemStyle: {{ borderRadius: 6 }},
        label: {{ formatter: '{{b}}: {{c}}' }}
      }}]
    }});

    // 3. 维度雷达图
    const dimRadar = echarts.init(document.getElementById('dimRadar'));
    const dimKeys = Object.keys(dimAvg);
    const dimMaxMap = {{
      content_depth: 25, structure: 20, code_quality: 15,
      pedagogy: 15, references: 10, readability: 15
    }};
    dimRadar.setOption({{
      tooltip: {{}},
      radar: {{
        indicator: dimKeys.map(k => ({{
          name: dimNames[k] || k,
          max: dimMaxMap[k] || 25
        }})),
        shape: 'polygon'
      }},
      series: [{{
        type: 'radar',
        data: [{{ value: dimKeys.map(k => dimAvg[k]), name: '平均分' }}],
        areaStyle: {{ opacity: 0.2 }}
      }}]
    }});

    // 4. 字数柱状图
    const wordBar = echarts.init(document.getElementById('wordBar'));
    wordBar.setOption({{
      tooltip: {{ trigger: 'axis' }},
      xAxis: {{ type: 'category', data: labels, axisLabel: {{ rotate: 45 }} }},
      yAxis: {{ type: 'value' }},
      series: [{{
        type: 'bar',
        data: wordCounts,
        itemStyle: {{ color: '#1890ff' }},
        label: {{ show: false }}
      }}]
    }});

    // 响应式
    window.addEventListener('resize', () => {{
      scoreBar.resize();
      scorePie.resize();
      dimRadar.resize();
      wordBar.resize();
    }});
  </script>
</body>
</html>"""

    return html


def _html_escape(s: str) -> str:
    """简单 HTML 转义。"""
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;"))
