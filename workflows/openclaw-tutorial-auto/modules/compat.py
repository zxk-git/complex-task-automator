#!/usr/bin/env python3
"""
compat.py — 模块兼容层
========================
统一为所有 modules/* 提供 scripts/utils.py 中的核心函数。
如果完整 utils 可用则直接导入，否则提供最小化降级实现。

用法 (在其他模块中):
    from modules.compat import setup_logger, cfg, save_json, load_json, word_count
"""

import json
import logging
import os
import re
import sys

# ── 确保 scripts/ 在路径中 ──────────────────────────
_SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

# ── 尝试导入完整 utils ─────────────────────────────
_FULL_UTILS = False
try:
    from utils import (  # type: ignore
        setup_logger,
        cfg,
        load_config,
        load_json,
        save_json,
        word_count,
        parse_outline,
        find_completed_chapters,
        read_chapter,
        run_git,
        get_project_dir,
        get_output_dir,
        progress_bar,
    )
    _FULL_UTILS = True
except ImportError:
    pass

# ── 降级实现 ────────────────────────────────────────
if not _FULL_UTILS:

    _LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

    def setup_logger(name: str, level: str = _LOG_LEVEL) -> logging.Logger:
        """创建统一格式的 Logger (降级版)"""
        logger = logging.getLogger(name)
        if logger.handlers:
            return logger
        logger.setLevel(getattr(logging, level, logging.INFO))
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(name)s] %(levelname)s — %(message)s",
            datefmt="%H:%M:%S",
        ))
        logger.addHandler(handler)
        return logger

    # ── config.yaml 解析 ──
    _CONFIG_CACHE = None
    _CONFIG_YAML = os.path.join(os.path.dirname(__file__), "..", "config.yaml")

    def _cast_value(v: str):
        if v.lower() in ("true", "yes"):
            return True
        if v.lower() in ("false", "no"):
            return False
        try:
            return int(v)
        except ValueError:
            pass
        try:
            return float(v)
        except ValueError:
            pass
        return v.strip('"').strip("'")

    def load_config() -> dict:
        global _CONFIG_CACHE
        if _CONFIG_CACHE is not None:
            return _CONFIG_CACHE
        try:
            import yaml  # type: ignore
            with open(_CONFIG_YAML, encoding="utf-8") as f:
                _CONFIG_CACHE = yaml.safe_load(f) or {}
        except (ImportError, FileNotFoundError):
            _CONFIG_CACHE = {}
            if os.path.isfile(_CONFIG_YAML):
                section = None
                with open(_CONFIG_YAML, encoding="utf-8") as f:
                    for line in f:
                        s = line.strip()
                        if not s or s.startswith("#"):
                            continue
                        if not line.startswith(" ") and ":" in s:
                            key, _, val = s.partition(":")
                            val = val.strip()
                            if val:
                                _CONFIG_CACHE[key.strip()] = _cast_value(val)
                                section = None
                            else:
                                section = key.strip()
                                _CONFIG_CACHE[section] = {}
                        elif section and ":" in s:
                            key, _, val = s.partition(":")
                            _CONFIG_CACHE[section][key.strip()] = _cast_value(val.strip())
        except Exception:
            _CONFIG_CACHE = {}
        return _CONFIG_CACHE

    def cfg(key: str, default=None):
        """便捷读取配置项，支持点号路径"""
        conf = load_config()
        parts = key.split(".")
        cur = conf
        for p in parts:
            if isinstance(cur, dict) and p in cur:
                cur = cur[p]
            else:
                return default
        return cur

    def load_json(path, default=None):
        if not os.path.isfile(str(path)):
            return default
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

    def save_json(path, data, ensure_dir: bool = True):
        if ensure_dir:
            os.makedirs(os.path.dirname(str(path)) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def word_count(text: str) -> int:
        """中英文混合字数统计"""
        cn = len(re.findall(r"[\u4e00-\u9fff]", text))
        en = len(re.findall(r"[a-zA-Z]+", text))
        return cn + en

    def parse_outline(proj_dir: str = None) -> list:
        proj_dir = proj_dir or cfg("project_dir", ".")
        outline = os.path.join(proj_dir, "OUTLINE.md")
        items = []
        if os.path.isfile(outline):
            with open(outline, encoding="utf-8") as f:
                for line in f:
                    m = re.match(r"^(\d+)\.\s*(.+)", line.strip())
                    if m:
                        items.append({"number": int(m.group(1)), "title": m.group(2).strip()})
        return items

    def find_completed_chapters(proj_dir: str = None) -> list:
        proj_dir = proj_dir or cfg("project_dir", ".")
        chapters = []
        if not os.path.isdir(proj_dir):
            return chapters
        for f in sorted(os.listdir(proj_dir)):
            fp = os.path.join(proj_dir, f)
            if os.path.isfile(fp) and f.endswith(".md"):
                m = re.match(r"^(\d+)", f)
                if m:
                    chapters.append({"number": int(m.group(1)), "file": f})
        return chapters

    def read_chapter(chapter_num: int, proj_dir: str = None):
        proj_dir = proj_dir or cfg("project_dir", ".")
        prefix = f"{chapter_num:02d}"
        if not os.path.isdir(proj_dir):
            return None
        for f in sorted(os.listdir(proj_dir)):
            if f.endswith(".md") and f.startswith(prefix):
                fp = os.path.join(proj_dir, f)
                with open(fp, encoding="utf-8") as fh:
                    text = fh.read()
                return {"path": fp, "file": f, "content": text, "word_count": word_count(text)}
        return None

    def run_git(args, cwd=None):
        import subprocess
        cwd = cwd or cfg("project_dir", ".")
        try:
            result = subprocess.run(["git"] + list(args), cwd=cwd,
                                    capture_output=True, text=True, timeout=30)
            return {"ok": result.returncode == 0, "stdout": result.stdout.rstrip(),
                    "stderr": result.stderr.strip(), "code": result.returncode}
        except Exception as e:
            return {"ok": False, "stdout": "", "stderr": str(e), "code": -1}

    def get_project_dir() -> str:
        return os.environ.get("PROJECT_DIR", cfg("project_dir", "."))

    def get_output_dir() -> str:
        return os.environ.get("OUTPUT_DIR", cfg("output_dir", "/tmp/openclaw-tutorial-auto-reports"))

    def progress_bar(pct: float, width: int = 20) -> str:
        pct = max(0, min(100, pct))
        filled = int(width * pct / 100)
        return f"[{'█' * filled}{'░' * (width - filled)}] {pct:.1f}%"


# ── 公开 API ────────────────────────────────────────
__all__ = [
    "setup_logger", "cfg", "load_config",
    "load_json", "save_json", "word_count",
    "parse_outline", "find_completed_chapters", "read_chapter",
    "run_git", "get_project_dir", "get_output_dir",
    "progress_bar",
]
