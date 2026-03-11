#!/usr/bin/env python3
"""
dashboard/server.py — 优化流水线 Dashboard 服务
=================================================
实时查看质量趋势、优化历史、缺陷热图。

基于 Python 内置 http.server + JSON API + 静态 HTML/ECharts 前端。
零依赖部署，无需 Flask/Fastify。

用法:
  python3 dashboard/server.py                # 默认 8686 端口
  python3 dashboard/server.py --port 9090
  python3 dashboard/server.py --report-dir /tmp/openclaw-tutorial-auto-reports
"""

import argparse
import http.server
import json
import os
import socketserver
import sys
import urllib.parse

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from modules.compat import setup_logger, cfg

log = setup_logger("dashboard")

DEFAULT_PORT = 8686
DEFAULT_REPORT_DIR = cfg("output_dir", "/tmp/openclaw-tutorial-auto-reports")
DASHBOARD_DIR = os.path.dirname(os.path.abspath(__file__))


class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    """处理 API 请求和静态文件服务。"""

    report_dir = DEFAULT_REPORT_DIR

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DASHBOARD_DIR, **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # API 路由
        if path.startswith("/api/"):
            self._handle_api(path, parsed.query)
            return

        # 首页重定向
        if path == "/" or path == "":
            self.path = "/index.html"

        return super().do_GET()

    def _handle_api(self, path: str, query: str):
        """处理 JSON API 请求。"""
        try:
            if path == "/api/scan":
                data = self._load_report("scan-report.json")
            elif path == "/api/analysis":
                data = self._load_report("analysis-report.json")
            elif path == "/api/code-scan":
                data = self._load_report("code-scan-report.json")
            elif path == "/api/code-analysis":
                data = self._load_report("code-analysis-report.json")
            elif path == "/api/trends":
                data = self._load_report("optimization-trends.json")
            elif path == "/api/pipeline-result":
                data = self._load_report("pipeline-result.json")
            elif path == "/api/code-pipeline-result":
                data = self._load_report("code-pipeline-result.json")
            elif path == "/api/links":
                data = self._load_report("link-check-report.json")
            elif path == "/api/consistency":
                data = self._load_report("consistency-report.json")
            elif path == "/api/readability":
                data = self._load_report("readability-report.json")
            elif path == "/api/diff":
                data = self._load_report("diff-scan-report.json")
            elif path == "/api/overview":
                data = self._build_overview()
            elif path == "/api/reports":
                data = self._list_reports()
            else:
                self._send_json({"error": "unknown endpoint"}, 404)
                return

            self._send_json(data)
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _load_report(self, filename: str) -> dict:
        filepath = os.path.join(self.report_dir, filename)
        if not os.path.isfile(filepath):
            return {"error": f"{filename} not found", "available": False}
        with open(filepath, encoding="utf-8") as f:
            return json.load(f)

    def _list_reports(self) -> dict:
        files = []
        if os.path.isdir(self.report_dir):
            for f in sorted(os.listdir(self.report_dir)):
                if f.endswith(".json") or f.endswith(".md") or f.endswith(".html"):
                    fp = os.path.join(self.report_dir, f)
                    files.append({
                        "name": f,
                        "size": os.path.getsize(fp),
                        "modified": os.path.getmtime(fp),
                    })
        return {"report_dir": self.report_dir, "files": files}

    def _build_overview(self) -> dict:
        """汇总概览数据。"""
        scan = self._load_report("scan-report.json")
        code = self._load_report("code-scan-report.json")
        trends = self._load_report("optimization-trends.json")
        pipeline = self._load_report("pipeline-result.json")

        return {
            "tutorial": {
                "summary": scan.get("summary", {}),
                "expected": scan.get("expected_chapters", 0),
                "available": "error" not in scan,
            },
            "code": {
                "summary": code.get("summary", {}),
                "available": "error" not in code,
            },
            "trends": {
                "overall": trends.get("overall", {}),
                "available": "error" not in trends,
            },
            "pipeline": {
                "version": pipeline.get("pipeline_version", "?"),
                "last_run": pipeline.get("timestamp", ""),
                "duration": pipeline.get("duration_seconds", 0),
                "stages_ok": pipeline.get("stages_ok", 0),
                "stages_failed": pipeline.get("stages_failed", 0),
                "available": "error" not in pipeline,
            },
        }

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        log.debug(f"{self.client_address[0]} — {format % args}")


def main():
    parser = argparse.ArgumentParser(description="Dashboard Server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--report-dir", type=str, default=DEFAULT_REPORT_DIR)
    args = parser.parse_args()

    DashboardHandler.report_dir = args.report_dir

    with socketserver.TCPServer(("", args.port), DashboardHandler) as httpd:
        log.info(f"Dashboard: http://localhost:{args.port}")
        log.info(f"Reports:   {args.report_dir}")
        log.info(f"API:       http://localhost:{args.port}/api/overview")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            log.info("Shutdown")


if __name__ == "__main__":
    main()
