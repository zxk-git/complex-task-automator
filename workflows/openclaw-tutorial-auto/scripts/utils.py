#!/usr/bin/env python3
"""
utils.py — 工作流共享工具库
所有脚本通用的函数、常量和日志配置。
消除重复代码，统一接口，提供结构化日志输出。
"""
from datetime import datetime
from pathlib import Path
from typing import Optional
import json
import logging
import os
import re
import shutil

# ═══════════════════════════════════════════════════════
# 日志配置
# ═══════════════════════════════════════════════════════

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()


def setup_logger(name: str, level: str = LOG_LEVEL) -> logging.Logger:
    """创建统一格式的 Logger"""
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


# ═══════════════════════════════════════════════════════
# 配置助手 — 从 config.yaml 读取统一参数
# ═══════════════════════════════════════════════════════

_CONFIG_CACHE: Optional[dict] = None
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_YAML = os.path.join(os.path.dirname(_SCRIPT_DIR), "config.yaml")


def load_config() -> dict:
    """加载 config.yaml，缓存结果；失败返回空字典"""
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE
    try:
        import yaml  # type: ignore
        text = Path(_CONFIG_YAML).read_text(encoding="utf-8")
        _CONFIG_CACHE = yaml.safe_load(text) or {}
    except ImportError:
        # 没有 PyYAML 时手工解析简单 key-value
        _CONFIG_CACHE = _parse_simple_yaml(_CONFIG_YAML)
    except Exception:
        _CONFIG_CACHE = {}
    return _CONFIG_CACHE


def _parse_simple_yaml(filepath: str) -> dict:
    """极简 YAML 解析器（仅支持顶级和一级嵌套的 key: value）"""
    result: dict = {}
    if not Path(filepath).is_file():
        return result
    current_section: Optional[str] = None
    for line in Path(filepath).read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # 顶级 key（无缩进）
        if not line.startswith(" ") and ":" in stripped:
            key, _, val = stripped.partition(":")
            val = val.strip()
            if val:
                # 布尔 / 数字 转换
                result[key.strip()] = _cast_value(val)
                current_section = None
            else:
                current_section = key.strip()
                result[current_section] = {}
        # 缩进 sub-key
        elif current_section and ":" in stripped:
            key, _, val = stripped.partition(":")
            val = val.strip()
            result[current_section][key.strip()] = _cast_value(val)
    return result


def _cast_value(v: str):
    """转换简单 YAML 值类型"""
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
    return v


def cfg(key: str, default=None):
    """便捷读取配置项，支持点号路径 (e.g. 'quality.min_words_per_chapter')"""
    conf = load_config()
    parts = key.split(".")
    cur = conf
    for p in parts:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return default
    return cur


# ═══════════════════════════════════════════════════════
# 路径常量 — 优先环境变量 → config.yaml → 硬编码默认值
# ═══════════════════════════════════════════════════════

def get_project_dir() -> str:
    """get_project_dir 的功能描述。

        Returns:
            str: ...
        """
    return os.environ.get(
        "PROJECT_DIR",
        cfg("project_dir", "/root/.openclaw/workspace/zxk-private/openclaw-tutorial-auto"),
    )


def get_output_dir() -> str:
    """get_output_dir 的功能描述。

        Returns:
            str: ...
        """
    return os.environ.get(
        "OUTPUT_DIR",
        cfg("output_dir", "/tmp/openclaw-tutorial-auto-reports"),
    )


def get_scripts_dir() -> str:
    """get_scripts_dir 的功能描述。

        Returns:
            str: ...
        """
    return os.environ.get("SCRIPTS_DIR", _SCRIPT_DIR)


def get_expected_chapters() -> int:
    """get_expected_chapters 的功能描述。

        Returns:
            int: ...
        """
    return int(os.environ.get(
        "EXPECTED_CHAPTERS",
        cfg("expected_chapters", 13),
    ))


def get_encoding() -> str:
    """get_encoding 的功能描述。

        Returns:
            str: ...
        """
    return cfg("encoding", "utf-8")


def get_git_remote() -> str:
    """Git remote URL：环境变量 > config.yaml > 默认"""
    return os.environ.get(
        "GIT_REMOTE",
        cfg("git.remote_url", ""),
    )


def get_git_remote_name() -> str:
    """Git remote 名称"""
    return os.environ.get(
        "GIT_REMOTE_NAME",
        cfg("git.remote_name", "origin"),
    )


# ═══════════════════════════════════════════════════════
# 大纲解析 — 唯一实现，全局复用
# ═══════════════════════════════════════════════════════

def parse_outline(proj_dir: str = None) -> list[dict]:
    """
    解析 OUTLINE.md，返回 [{"number": int, "title": str}, ...]
    """
    proj_dir = proj_dir or get_project_dir()
    outline = Path(proj_dir) / "OUTLINE.md"
    items: list[dict] = []
    if outline.is_file():
        for line in outline.read_text(encoding=get_encoding()).splitlines():
            m = re.match(r"^(\d+)\.\s*(.+)", line.strip())
            if m:
                items.append({
                    "number": int(m.group(1)),
                    "title": m.group(2).strip(),
                })
    return items


# ═══════════════════════════════════════════════════════
# 章节扫描 — 唯一实现，全局复用
# ═══════════════════════════════════════════════════════

def find_completed_chapters(proj_dir: str = None) -> list[dict]:
    """
    扫描已有章节 .md 文件，返回
    [{"number": int, "file": str, "size_bytes": int, "modified": str}, ...]
    """
    proj_dir = proj_dir or get_project_dir()
    chapters: list[dict] = []
    proj = Path(proj_dir)
    if not proj.is_dir():
        return chapters
    for f in sorted(proj.iterdir()):
        if f.is_file() and f.suffix == ".md":
            m = re.match(r"^(\d+)", f.name)
            if m:
                stat = f.stat()
                chapters.append({
                    "number": int(m.group(1)),
                    "file": f.name,
                    "size_bytes": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })
    return chapters


def find_completed_numbers(proj_dir: str = None) -> set[int]:
    """返回已完成章节编号集合 (便捷接口)"""
    return {ch["number"] for ch in find_completed_chapters(proj_dir)}


# ═══════════════════════════════════════════════════════
# 章节读取 — 唯一实现，全局复用
# ═══════════════════════════════════════════════════════

def read_chapter(chapter_num: int, proj_dir: str = None) -> Optional[dict]:
    """
    读取指定章节并返回结构化信息，未找到返回 None。
    返回: {"path", "file", "content", "word_count", "code_blocks", "headings", "char_count"}
    """
    proj_dir = proj_dir or get_project_dir()
    proj = Path(proj_dir)
    prefix = f"{chapter_num:02d}"
    for f in sorted(proj.iterdir()):
        if f.is_file() and f.suffix == ".md" and f.name.startswith(prefix):
            text = f.read_text(encoding=get_encoding())
            headings = re.findall(r"^(#{1,3})\s+(.+)", text, re.MULTILINE)
            code_blocks = len(re.findall(r"```", text)) // 2
            wc = word_count(text)
            return {
                "path": str(f),
                "file": f.name,
                "content": text,
                "word_count": wc,
                "code_blocks": code_blocks,
                "headings": [{"level": len(h[0]), "text": h[1]} for h in headings],
                "char_count": len(text),
            }
    return None


# ═══════════════════════════════════════════════════════
# 文本度量
# ═══════════════════════════════════════════════════════

def word_count(text: str) -> int:
    """中英文混合字数统计"""
    cn = len(re.findall(r"[\u4e00-\u9fff]", text))
    en = len(re.findall(r"[a-zA-Z]+", text))
    return cn + en


# ═══════════════════════════════════════════════════════
# JSON 安全加载/保存
# ═══════════════════════════════════════════════════════

def load_json(filepath: str | Path, default=None):
    """安全加载 JSON 文件，失败返回 default"""
    p = Path(filepath)
    if not p.is_file():
        return default
    try:
        return json.loads(p.read_text(encoding=get_encoding()))
    except Exception:
        return default


def save_json(filepath: str | Path, data, ensure_dir: bool = True):
    """安全保存 JSON 文件"""
    p = Path(filepath)
    if ensure_dir:
        p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding=get_encoding())


# ═══════════════════════════════════════════════════════
# 磁盘健康
# ═══════════════════════════════════════════════════════

def check_disk_health(path: str = None) -> dict:
    """检查磁盘空间，默认检查项目所在分区"""
    path = path or get_project_dir()
    total, used, free = shutil.disk_usage(path)
    return {
        "total_gb": round(total / (1024 ** 3), 1),
        "used_gb": round(used / (1024 ** 3), 1),
        "free_gb": round(free / (1024 ** 3), 1),
        "usage_percent": round(used / total * 100, 1),
        "healthy": free > 1024 ** 3,
    }


# ═══════════════════════════════════════════════════════
# Git 辅助
# ═══════════════════════════════════════════════════════

import subprocess


def run_git(args: list[str], cwd: str = None) -> dict:
    """执行 git 命令，返回 {"ok", "stdout", "stderr", "code"}"""
    cwd = cwd or get_project_dir()
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd, capture_output=True, text=True, timeout=30,
        )
        return {
            "ok": result.returncode == 0,
            "stdout": result.stdout.rstrip(),
            "stderr": result.stderr.strip(),
            "code": result.returncode,
        }
    except Exception as e:
        return {"ok": False, "stdout": "", "stderr": str(e), "code": -1}


# ═══════════════════════════════════════════════════════
# 缓存清理
# ═══════════════════════════════════════════════════════

def cleanup_old_caches(cache_dir: str = None, max_days: int = 7):
    """清理过期的搜索缓存和优化历史"""
    cache_dir = cache_dir or os.path.join(get_output_dir(), "research-cache")
    cache_path = Path(cache_dir)
    if not cache_path.is_dir():
        return 0
    cutoff = datetime.now().timestamp() - max_days * 86400
    removed = 0
    for f in cache_path.iterdir():
        if f.is_file() and f.stat().st_mtime < cutoff:
            f.unlink()
            removed += 1
    return removed


def trim_history(history: dict, max_entries: int = 200) -> dict:
    """裁剪优化历史，防止无限增长"""
    entries = history.get("history", [])
    if len(entries) > max_entries:
        history["history"] = entries[-max_entries:]
    return history


# ═══════════════════════════════════════════════════════
# 进度条 / 格式化
# ═══════════════════════════════════════════════════════

def progress_bar(pct: float, width: int = 20) -> str:
    """ASCII 进度条"""
    pct = max(0, min(100, pct))
    filled = int(width * pct / 100)
    return f"[{'█' * filled}{'░' * (width - filled)}] {pct:.1f}%"


def banner(title: str, icon: str = "🔧"):
    """统一打印带框的标题"""
    print(f"\n{'═' * 56}")
    print(f"  {icon} {title}")
    print(f"{'═' * 56}")


if __name__ == "__main__":
    pass
