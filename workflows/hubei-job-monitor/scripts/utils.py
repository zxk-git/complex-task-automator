#!/usr/bin/env python3
"""
湖北招聘监控 — 共享工具库
"""
import os
import sys
import json
import logging
import hashlib
from pathlib import Path
from datetime import datetime

import yaml

# ── 路径 ────────────────────────────────────────────
_SCRIPT_DIR = str(Path(__file__).resolve().parent)
_WORKFLOW_DIR = str(Path(_SCRIPT_DIR).parent)

# ── 配置 ────────────────────────────────────────────
_config = None


def load_config() -> dict:
    global _config
    if _config is not None:
        return _config

    config_file = os.environ.get(
        "CONFIG_FILE",
        os.path.join(_WORKFLOW_DIR, "config.yaml"),
    )
    try:
        with open(config_file, encoding="utf-8") as f:
            _config = yaml.safe_load(f) or {}
    except FileNotFoundError:
        _config = {}
    return _config


def cfg(key: str, default=None):
    """点分路径读取配置: cfg('filter.education_keywords', [])"""
    d = load_config()
    for k in key.split("."):
        if isinstance(d, dict):
            d = d.get(k)
        else:
            return default
        if d is None:
            return default
    return d


# ── 路径工具 ────────────────────────────────────────
def get_data_dir() -> str:
    return os.environ.get(
        "DATA_DIR",
        cfg("data_dir", os.path.join(_WORKFLOW_DIR, "data")),
    )


def get_output_dir() -> str:
    d = os.environ.get(
        "OUTPUT_DIR",
        cfg("output_dir", "/tmp/hubei-job-monitor-reports"),
    )
    Path(d).mkdir(parents=True, exist_ok=True)
    return d


# ── 日志 ────────────────────────────────────────────
def setup_logger(name: str) -> logging.Logger:
    level = getattr(logging, cfg("log_level", "INFO").upper(), logging.INFO)
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(name)s] %(levelname)s — %(message)s", "%H:%M:%S")
        )
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger


# ── HTTP 工具 ───────────────────────────────────────
def get_http_session():
    """返回配置好的 requests.Session"""
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    session = requests.Session()
    retries = cfg("http.retry", 2)
    timeout = cfg("http.timeout", 30)
    ua = cfg("http.user_agent", "Mozilla/5.0")

    retry = Retry(total=retries, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers["User-Agent"] = ua
    session.timeout = timeout

    return session


# ── JSON 工具 ───────────────────────────────────────
def save_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else {}


# ── 去重 ID 生成 ────────────────────────────────────
def make_job_id(source_id: str, title: str, url: str = "") -> str:
    """根据来源+标题+URL生成唯一ID"""
    raw = f"{source_id}:{title}:{url}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]


# ── 时间工具 ────────────────────────────────────────
def now_iso() -> str:
    return datetime.now().isoformat()


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")
