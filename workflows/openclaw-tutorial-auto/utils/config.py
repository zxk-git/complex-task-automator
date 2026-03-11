#!/usr/bin/env python3
"""
config.py — 统一配置管理
==========================
所有模块通过此文件读取配置，支持 config.yaml + 环境变量。
"""

import os
import re
import sys

# ── 兼容 scripts/utils.py 的 cfg() ────────────────
_SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

try:
    from utils import cfg as _utils_cfg, load_config
    def get(key, default=None):
        """读取配置项。优先级: 环境变量 > config.yaml > default"""
        return _utils_cfg(key, default)
except ImportError:
    _config_cache = {}

    def _load_yaml_simple(path):
        """简易 YAML 解析（无 PyYAML 时的回退）。"""
        data = {}
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    m = re.match(r"^(\w[\w.]*)\s*:\s*(.+)$", line)
                    if m:
                        key, val = m.group(1), m.group(2).strip()
                        val = val.strip('"').strip("'")
                        if val.lower() in ("true", "false"):
                            val = val.lower() == "true"
                        elif val.isdigit():
                            val = int(val)
                        data[key] = val
        except FileNotFoundError:
            pass
        return data

    def get(key, default=None):
        """读取配置项。优先级: 环境变量 > config.yaml > default"""
        env_key = key.replace(".", "_").upper()
        env_val = os.environ.get(env_key)
        if env_val is not None:
            return env_val

        if not _config_cache:
            config_path = os.path.join(
                os.path.dirname(__file__), "..", "config.yaml")
            _config_cache.update(_load_yaml_simple(config_path))

        # 支持 dotted key: git.branch → config[git][branch]
        parts = key.split(".")
        val = _config_cache
        for part in parts:
            if isinstance(val, dict):
                val = val.get(part)
            else:
                val = None
                break

        return val if val is not None else default


# 常用配置项的快捷方法
def project_dir():
    """project_dir 的功能描述。
        """
    return get("project_dir",
               "/root/.openclaw/workspace/zxk-private/openclaw-tutorial-auto")

def output_dir():
    """output_dir 的功能描述。
        """
    return get("output_dir", "/tmp/openclaw-tutorial-auto-reports")

def scripts_dir():
    """scripts_dir 的功能描述。
        """
    return os.path.join(os.path.dirname(__file__), "..", "scripts")

def modules_dir():
    """modules_dir 的功能描述。
        """
    return os.path.join(os.path.dirname(__file__), "..", "modules")

def prompts_dir():
    """prompts_dir 的功能描述。
        """
    return os.path.join(os.path.dirname(__file__), "..", "prompts")

def expected_chapters():
    """expected_chapters 的功能描述。
        """
    return int(get("expected_chapters", 21))

def is_dry_run():
    """is_dry_run 的功能描述。
        """
    return str(get("DRY_RUN", os.environ.get("DRY_RUN", "false"))).lower() == "true"


if __name__ == "__main__":
    pass
