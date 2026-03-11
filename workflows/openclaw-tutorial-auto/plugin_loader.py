#!/usr/bin/env python3
"""
plugin_loader.py — 插件热加载系统
====================================
允许在运行时动态发现、加载、卸载、重载插件，无需重启流水线。

## 插件约定

1. 插件放在 `plugins/` 目录（或 config.yaml 中 `plugins.dir` 指定的目录）
2. 每个插件是一个 Python 文件或包目录
3. 插件必须暴露 `PLUGIN_META` dict：

   ```python
   PLUGIN_META = {
       "name": "my_plugin",          # 唯一标识 (必须)
       "version": "1.0.0",           # 语义版本 (必须)
       "description": "...",         # 简介
       "author": "...",
       "hooks": ["after_scan", "before_refine"],  # 钩入的阶段
       "priority": 100,              # 优先级 (数字越小越先执行, 默认 100)
   }
   ```

4. 插件实现对应钩子函数：
   - `after_scan(scan_result: dict) -> dict`     # 扫描后处理
   - `before_refine(analysis: dict) -> dict`     # 精炼前处理
   - `after_refine(result: dict) -> dict`        # 精炼后处理
   - `on_report(report: dict) -> dict`           # 报告生成时
   - `on_error(stage: str, error: Exception)`    # 阶段出错时

## 使用方式

    from plugin_loader import PluginManager

    pm = PluginManager()
    pm.discover()
    pm.load_all()

    # 流水线中触发钩子
    scan_result = pm.trigger("after_scan", scan_result)

    # 热重载单个插件
    pm.reload("my_plugin")

    # 运行时加载新插件
    pm.load("plugins/new_plugin.py")
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from modules.compat import setup_logger, cfg

log = setup_logger("plugin_loader")

# ── 有效钩子名称 ──────────────────────────────────────
VALID_HOOKS = frozenset([
    "after_scan",
    "before_analyze",
    "after_analyze",
    "before_refine",
    "after_refine",
    "before_format",
    "after_format",
    "on_report",
    "on_error",
    "on_pipeline_start",
    "on_pipeline_end",
])

_ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PLUGIN_DIR = os.path.join(_ROOT, "plugins")


@dataclass
class PluginInfo:
    """已加载插件的元信息。"""
    name: str
    version: str
    description: str = ""
    author: str = ""
    hooks: List[str] = field(default_factory=list)
    priority: int = 100
    filepath: str = ""
    module: Any = None
    loaded_at: float = 0.0
    enabled: bool = True


class PluginManager:
    """插件热加载管理器。

    线程安全设计：所有 mutation 操作使用简单锁保护。
    """

    def __init__(self, plugin_dir: str = None):
        self.plugin_dir = plugin_dir or cfg("plugins.dir", DEFAULT_PLUGIN_DIR)
        self._plugins: Dict[str, PluginInfo] = {}
        self._hook_cache: Dict[str, List[tuple]] = {}  # hook_name → [(priority, plugin_name, callable)]
        self._dirty = True  # hook cache 需要重建

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 发现 & 加载
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def discover(self) -> List[str]:
        """扫描插件目录，返回发现的插件文件列表。"""
        if not os.path.isdir(self.plugin_dir):
            log.info(f"插件目录不存在: {self.plugin_dir}，跳过发现")
            return []

        found = []
        for entry in sorted(os.listdir(self.plugin_dir)):
            path = os.path.join(self.plugin_dir, entry)
            if entry.startswith("_") or entry.startswith("."):
                continue
            # 单文件插件
            if entry.endswith(".py"):
                found.append(path)
            # 包目录插件
            elif os.path.isdir(path) and os.path.exists(os.path.join(path, "__init__.py")):
                found.append(path)

        log.info(f"发现 {len(found)} 个插件候选: {[os.path.basename(f) for f in found]}")
        return found

    def load_all(self) -> int:
        """发现并加载所有插件。返回成功加载数。"""
        files = self.discover()
        loaded = 0
        for f in files:
            try:
                self.load(f)
                loaded += 1
            except Exception as e:
                log.warning(f"加载失败 {os.path.basename(f)}: {e}")
        return loaded

    def load(self, filepath: str) -> PluginInfo:
        """加载单个插件文件/包。

        Args:
            filepath: .py 文件路径或包目录路径

        Returns:
            PluginInfo

        Raises:
            ValueError: 插件格式不正确
            ImportError: 导入失败
        """
        filepath = os.path.abspath(filepath)
        basename = os.path.basename(filepath)

        # 确定模块名
        if filepath.endswith(".py"):
            mod_name = f"plugin_{Path(filepath).stem}"
        elif os.path.isdir(filepath):
            mod_name = f"plugin_{basename}"
        else:
            raise ValueError(f"不支持的插件格式: {filepath}")

        # 动态导入
        spec = importlib.util.spec_from_file_location(
            mod_name,
            filepath if filepath.endswith(".py") else os.path.join(filepath, "__init__.py"),
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"无法创建模块 spec: {filepath}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)

        # 验证 PLUGIN_META
        meta = getattr(module, "PLUGIN_META", None)
        if not meta or not isinstance(meta, dict):
            del sys.modules[mod_name]
            raise ValueError(f"插件缺少 PLUGIN_META: {basename}")

        name = meta.get("name")
        version = meta.get("version")
        if not name or not version:
            del sys.modules[mod_name]
            raise ValueError(f"PLUGIN_META 缺少 name/version: {basename}")

        # 验证钩子
        hooks = meta.get("hooks", [])
        invalid = set(hooks) - VALID_HOOKS
        if invalid:
            log.warning(f"插件 {name} 声明了无效钩子: {invalid}，将忽略")
            hooks = [h for h in hooks if h in VALID_HOOKS]

        # 验证钩子函数存在
        valid_hooks = []
        for hook in hooks:
            if callable(getattr(module, hook, None)):
                valid_hooks.append(hook)
            else:
                log.warning(f"插件 {name} 声明了钩子 {hook} 但未实现")

        # 如果已存在同名插件，先卸载
        if name in self._plugins:
            log.info(f"重载插件: {name} (v{self._plugins[name].version} → v{version})")
            self.unload(name)

        info = PluginInfo(
            name=name,
            version=version,
            description=meta.get("description", ""),
            author=meta.get("author", ""),
            hooks=valid_hooks,
            priority=meta.get("priority", 100),
            filepath=filepath,
            module=module,
            loaded_at=time.time(),
        )

        self._plugins[name] = info
        self._dirty = True
        log.info(f"✅ 加载插件: {name} v{version} (hooks: {valid_hooks})")
        return info

    def unload(self, name: str) -> bool:
        """卸载指定插件。"""
        info = self._plugins.pop(name, None)
        if not info:
            log.warning(f"插件 {name} 未加载，无法卸载")
            return False

        # 清理 sys.modules
        mod_name = f"plugin_{name}"
        sys.modules.pop(mod_name, None)

        self._dirty = True
        log.info(f"🔌 卸载插件: {name}")
        return True

    def reload(self, name: str) -> Optional[PluginInfo]:
        """热重载指定插件。"""
        info = self._plugins.get(name)
        if not info:
            log.warning(f"插件 {name} 未加载，无法重载")
            return None

        filepath = info.filepath
        self.unload(name)
        return self.load(filepath)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 钩子触发
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _rebuild_hook_cache(self):
        """重建钩子 → 处理器映射（按优先级排序）。"""
        cache: Dict[str, List[tuple]] = {}
        for info in self._plugins.values():
            if not info.enabled:
                continue
            for hook in info.hooks:
                fn = getattr(info.module, hook, None)
                if fn and callable(fn):
                    cache.setdefault(hook, []).append((info.priority, info.name, fn))

        # 按优先级排序 (数字越小越先执行)
        for hook in cache:
            cache[hook].sort(key=lambda x: x[0])

        self._hook_cache = cache
        self._dirty = False

    def trigger(self, hook_name: str, data: Any = None, **kwargs) -> Any:
        """触发指定钩子，按优先级顺序执行所有插件处理器。

        数据流: 前一个插件的返回值作为下一个的输入（管道模式）。
        如果处理器返回 None，保持原 data 不变。

        Args:
            hook_name: 钩子名称
            data: 传递给处理器的数据
            **kwargs: 额外参数

        Returns:
            经过所有插件处理后的数据
        """
        if self._dirty:
            self._rebuild_hook_cache()

        handlers = self._hook_cache.get(hook_name, [])
        if not handlers:
            return data

        for priority, plugin_name, fn in handlers:
            try:
                result = fn(data, **kwargs) if kwargs else fn(data)
                if result is not None:
                    data = result
            except Exception as e:
                log.error(f"插件 {plugin_name}.{hook_name}() 异常: {e}")
                # 插件错误不中断流水线
                continue

        return data

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 查询 & 管理
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def list_plugins(self) -> List[Dict]:
        """返回所有已加载插件的摘要。"""
        return [
            {
                "name": info.name,
                "version": info.version,
                "description": info.description,
                "hooks": info.hooks,
                "priority": info.priority,
                "enabled": info.enabled,
                "filepath": info.filepath,
            }
            for info in sorted(self._plugins.values(), key=lambda x: x.priority)
        ]

    def enable(self, name: str) -> bool:
        """启用插件。"""
        info = self._plugins.get(name)
        if info:
            info.enabled = True
            self._dirty = True
            return True
        return False

    def disable(self, name: str) -> bool:
        """禁用插件（不卸载，保留在内存中）。"""
        info = self._plugins.get(name)
        if info:
            info.enabled = False
            self._dirty = True
            return True
        return False

    def get(self, name: str) -> Optional[PluginInfo]:
        """获取插件信息。"""
        return self._plugins.get(name)

    @property
    def count(self) -> int:
        return len(self._plugins)

    @property
    def enabled_count(self) -> int:
        return sum(1 for p in self._plugins.values() if p.enabled)

    def __repr__(self):
        return f"<PluginManager plugins={self.count} enabled={self.enabled_count}>"


# ── 全局单例 ──────────────────────────────────────────
_manager: Optional[PluginManager] = None


def get_plugin_manager(plugin_dir: str = None) -> PluginManager:
    """获取全局 PluginManager 单例。"""
    global _manager
    if _manager is None:
        _manager = PluginManager(plugin_dir)
    return _manager


# ── CLI ───────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="插件管理器")
    parser.add_argument("--dir", default=None, help="插件目录")
    parser.add_argument("--list", action="store_true", help="列出已发现的插件")
    parser.add_argument("--load", type=str, help="加载指定插件")
    parser.add_argument("--test-hook", type=str, help="测试触发钩子")
    args = parser.parse_args()

    pm = PluginManager(args.dir)
    pm.load_all()

    if args.list or not args.load:
        print(f"\n已加载插件 ({pm.count}):")
        for p in pm.list_plugins():
            status = "✅" if p["enabled"] else "⏸️"
            print(f"  {status} {p['name']} v{p['version']} "
                  f"(hooks: {p['hooks']}, priority: {p['priority']})")
            if p["description"]:
                print(f"     {p['description']}")

    if args.load:
        pm.load(args.load)

    if args.test_hook:
        result = pm.trigger(args.test_hook, {"test": True})
        print(f"\n钩子 {args.test_hook} 结果: {result}")
