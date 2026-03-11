# 🔌 插件开发指南

> 为 OpenClaw 自动优化系统编写自定义插件

---

## 概述

插件系统允许在流水线执行的关键节点注入自定义逻辑，无需修改核心代码。

**特性**:
- 文件级插件，放入 `plugins/` 目录自动发现
- 11 种 Hook 覆盖流水线全生命周期
- 优先级排序，pipe 模式传递数据
- 热加载：运行时加载/卸载/重载

---

## 快速开始

### 1. 创建插件文件

在 `plugins/` 目录下创建 Python 文件：

```python
# plugins/my_reporter.py

PLUGIN_META = {
    "name": "my_reporter",
    "version": "1.0.0",
    "description": "流水线完成后生成自定义报告",
    "hooks": ["on_pipeline_end"],
    "priority": 50,
}

def on_pipeline_end(data, **ctx):
    """流水线完成时生成报告。"""
    report = data or {}
    status = report.get("status", "unknown")
    print(f"[MyReporter] 流水线状态: {status}")
    
    # 可以写入文件、发送通知等
    with open("/tmp/my-report.txt", "w") as f:
        f.write(f"Status: {status}\n")
    
    return data  # 必须返回 data
```

### 2. 验证加载

```bash
python3 cli.py plugins
```

输出：
```
已加载插件 (1 个)

  ✅ my_reporter v1.0.0
     流水线完成后生成自定义报告
     hooks: on_pipeline_end
```

### 3. 运行

```bash
python3 cli.py run scan    # 插件会在 on_pipeline_end 时自动触发
```

---

## PLUGIN_META 规范

每个插件**必须**在模块顶层定义 `PLUGIN_META` 字典：

```python
PLUGIN_META = {
    "name": "plugin_name",       # 必填: 唯一标识符
    "version": "1.0.0",          # 必填: 版本号
    "description": "...",        # 可选: 描述
    "hooks": ["after_scan"],     # 必填: 要注册的 hook 列表
    "priority": 50,              # 可选: 优先级 (1-100, 默认 50, 越小越先)
}
```

---

## Hook 列表

| Hook | 触发时机 | data 参数 | 典型用途 |
|------|---------|----------|---------|
| `on_pipeline_start` | 流水线启动前 | `None` | 初始化资源 |
| `after_scan` | 扫描完成 | 扫描结果 dict | 过滤/增强扫描数据 |
| `before_analyze` | 分析前 | 上一阶段输出 | 预处理 |
| `after_analyze` | 分析后 | 分析结果 | 注入额外分析维度 |
| `before_refine` | 精炼前 | 分析数据 | 决定修复策略 |
| `after_refine` | 精炼后 | 精炼结果 | 验证修复效果 |
| `before_format` | 格式化前 | 待格式化数据 | 自定义格式规则 |
| `after_format` | 格式化后 | 格式化结果 | 后处理 |
| `on_report` | 生成报告时 | 报告 dict | 添加自定义报告字段 |
| `on_error` | 发生错误 | 错误信息 | 告警/日志 |
| `on_pipeline_end` | 流水线完成 | 最终报告 | 汇总/通知 |

---

## Hook 函数签名

```python
def hook_name(data, **ctx):
    """
    参数:
        data: 前一阶段的输出数据 (或前一个插件的输出)
        **ctx: 上下文信息 (hook_name, pipeline 实例等)
    
    返回:
        修改后的 data (pipe 模式: 输出会传给下一个插件)
        如果返回 None, 则保持 data 不变
    """
    # 处理数据
    modified = do_something(data)
    return modified
```

**重要**: 
- Hook 函数**必须**返回 data（或修改后的数据）
- 返回 `None` 等同于原样传递
- 异常会被捕获并记录，不会中断流水线

---

## 数据流 (Pipe 模式)

当多个插件注册同一个 Hook 时，按 priority 排序执行，数据 pipe 传递：

```
Plugin A (priority=10) → Plugin B (priority=50) → Plugin C (priority=90)
     data → modified_A → modified_B → modified_C → 返回给流水线
```

示例：

```python
# Plugin A: 标记低分 (priority=10)
def after_scan(data, **ctx):
    for ch in data.get("chapters", []):
        if ch.get("quality_score", 0) < 60:
            ch["_alert"] = True
    return data

# Plugin B: 过滤已标记的 (priority=50)
def after_scan(data, **ctx):
    alerts = [ch for ch in data.get("chapters", []) if ch.get("_alert")]
    data["_alert_count"] = len(alerts)
    return data
```

---

## 完整示例

### 示例 1: 低分告警器

```python
# plugins/score_alert.py
"""为低分章节添加告警标记。"""

PLUGIN_META = {
    "name": "score_alert",
    "version": "1.0.0",
    "description": "低分章节告警",
    "hooks": ["after_scan"],
    "priority": 20,
}

THRESHOLD = 65

def after_scan(data, **ctx):
    chapters = data.get("chapters", [])
    alerts = []
    for ch in chapters:
        score = ch.get("quality_score", 0)
        if score < THRESHOLD:
            ch["_low_score_alert"] = True
            alerts.append(f"Ch{ch.get('number', '?')}: {score}")
    
    if alerts:
        print(f"[ScoreAlert] ⚠️ 低分章节: {', '.join(alerts)}")
    
    return data
```

### 示例 2: 飞书通知

```python
# plugins/feishu_notify.py
"""流水线完成后发送飞书通知。"""

PLUGIN_META = {
    "name": "feishu_notify",
    "version": "1.0.0",
    "description": "飞书通知",
    "hooks": ["on_pipeline_end", "on_error"],
    "priority": 90,
}

def on_pipeline_end(data, **ctx):
    from modules.notifier import send_notification
    report = data or {}
    send_notification(
        title="流水线完成",
        body=f"状态: {report.get('status', '?')}",
        level="success",
        channels=["feishu"],
    )
    return data

def on_error(data, **ctx):
    from modules.notifier import send_notification
    send_notification(
        title="流水线错误",
        body=str(data),
        level="error",
        channels=["feishu"],
    )
    return data
```

### 示例 3: 自定义评分维度

```python
# plugins/custom_scoring.py
"""添加自定义评分维度。"""

PLUGIN_META = {
    "name": "custom_scoring",
    "version": "1.0.0",
    "description": "添加 SEO 评分维度",
    "hooks": ["after_scan"],
    "priority": 30,
}

def after_scan(data, **ctx):
    for ch in data.get("chapters", []):
        content = ch.get("content", "")
        seo_score = _calculate_seo(content)
        ch.setdefault("_custom_scores", {})["seo"] = seo_score
    return data

def _calculate_seo(content: str) -> float:
    score = 100.0
    if len(content) < 300:
        score -= 20
    if "meta" not in content.lower():
        score -= 10
    return max(0, score)
```

---

## 编程方式管理插件

```python
from plugin_loader import get_plugin_manager

pm = get_plugin_manager()

# 加载
pm.load_all()                          # 加载 plugins/ 下所有插件
pm.load("/path/to/my_plugin.py")       # 加载单个文件

# 查询
plugins = pm.list_plugins()            # 列出所有插件
info = pm.get("my_plugin")            # 获取指定插件

# 禁用/启用
info.enabled = False                   # 禁用 (不会在 trigger 时执行)
info.enabled = True                    # 重新启用

# 热重载 (修改文件后)
pm.reload("my_plugin")                # 自动重新导入

# 卸载
pm.unload("my_plugin")                # 完全移除

# 手动触发 hook
result = pm.trigger("after_scan", scan_data, pipeline=self)
```

---

## 最佳实践

1. **命名**: 使用清晰的 `snake_case` 名称，避免与核心模块冲突
2. **优先级**: 数据增强类 < 50, 通知/日志类 > 50
3. **错误处理**: Hook 内部做好异常捕获，不要影响其他插件
4. **返回值**: 始终返回 data，即使未修改
5. **延迟导入**: 在 Hook 函数内导入重量级模块，减少启动开销
6. **无状态**: 尽量无状态设计，如需状态使用模块级变量
7. **测试**: 可单独导入模块测试 Hook 函数

```python
# 单独测试
from plugins.my_plugin import after_scan
test_data = {"chapters": [{"quality_score": 50}]}
result = after_scan(test_data)
assert result["chapters"][0].get("_low_score_alert") is True
```

---

## 目录结构

```
plugins/
├── __init__.py              # (可选) 空文件
├── score_highlighter.py     # 内置: 低分告警标记
├── my_reporter.py           # 自定义: 报告生成
├── feishu_notify.py         # 自定义: 飞书通知
└── ...
```

插件加载器会扫描 `plugins/` 目录下所有 `.py` 文件（排除 `__init__.py` 和 `_` 开头的文件）。
