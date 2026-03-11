#!/usr/bin/env python3
"""
research.py — DEPRECATED: 此脚本已合并到 web_researcher.py
保留为兼容层，调用 web_researcher 的统一接口。

旧行为: 独立的 Tavily/DDG 搜索 (通过 openclaw CLI)
新行为: 委托给 web_researcher.py (通过 node 脚本直接调用)
"""
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)


def run():
    """兼容入口：委托给 web_researcher"""
    import web_researcher
    return web_researcher.run()


if __name__ == "__main__":
    run()
