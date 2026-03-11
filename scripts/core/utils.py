#!/usr/bin/env python3
"""
Complex Task Automator - 共享工具函数
"""

import os
import re
import json
import shutil
from pathlib import Path
from typing import Any, Dict, Optional


def substitute_variables_base(value: str, context: Any) -> str:
    """替换 ${var} 格式的变量（共享工具函数）

    对 value 中的 ${varName} 占位符进行替换：
    1. 优先从 context.variables 中查找
    2. 其次从环境变量查找
    3. 未找到则保留原文
    """
    if not isinstance(value, str):
        return value

    def replace_var(match):
        var_name = match.group(1)
        if hasattr(context, 'variables') and var_name in context.variables:
            return str(context.variables[var_name])
        return os.environ.get(var_name, match.group(0))

    return re.sub(r'\$\{([^}]+)\}', replace_var, value)


# -------------------------------------------------------------------
# 安全文件 I/O
# -------------------------------------------------------------------


def safe_read_file(path: str, encoding: str = "utf-8") -> Optional[str]:
    """安全读取文件，文件不存在或读取失败时返回 None"""
    try:
        return Path(path).read_text(encoding=encoding)
    except Exception:
        return None


def safe_write_file(
    path: str,
    content: str,
    encoding: str = "utf-8",
    mkdir: bool = True,
) -> bool:
    """安全写入文件，自动创建父目录。返回 True/False 表示成功与否"""
    try:
        p = Path(path)
        if mkdir:
            p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding=encoding)
        return True
    except Exception:
        return False


def safe_read_json(path: str) -> Optional[Dict[str, Any]]:
    """安全读取 JSON 文件"""
    text = safe_read_file(path)
    if text is None:
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def safe_write_json(
    path: str,
    data: Any,
    indent: int = 2,
    ensure_ascii: bool = False,
) -> bool:
    """安全写入 JSON 文件"""
    try:
        content = json.dumps(data, indent=indent, ensure_ascii=ensure_ascii)
        return safe_write_file(path, content)
    except Exception:
        return False


# -------------------------------------------------------------------
# 路径工具
# -------------------------------------------------------------------


def resolve_path(base: str, relative: str) -> str:
    """将相对路径解析为绝对路径（基于 base 目录）"""
    p = Path(relative)
    if p.is_absolute():
        return str(p)
    return str(Path(base) / p)


def ensure_dir(path: str) -> Path:
    """确保目录存在并返回 Path 对象"""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


# -------------------------------------------------------------------
# YAML 工具
# -------------------------------------------------------------------


def load_yaml(path: str) -> Optional[Dict[str, Any]]:
    """安全加载 YAML 文件"""
    try:
        import yaml
        text = safe_read_file(path)
        if text is None:
            return None
        return yaml.safe_load(text)
    except Exception:
        return None


# -------------------------------------------------------------------
# 命令检测
# -------------------------------------------------------------------


def which(cmd: str) -> Optional[str]:
    """跨平台查找可执行文件路径（替代 subprocess + which）"""
    return shutil.which(cmd)
