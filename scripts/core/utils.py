#!/usr/bin/env python3
"""
Complex Task Automator - 共享工具函数
"""

import os
import re
from typing import Any


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
