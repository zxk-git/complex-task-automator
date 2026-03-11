#!/usr/bin/env python3
"""
markdown_utils.py — Markdown 解析工具
========================================
共享的 Markdown 处理函数。
"""

from typing import List, Dict, Optional
import re


def extract_headings(text: str) -> List[Dict]:
    """提取所有标题及其层级。"""
    headings = []
    for i, line in enumerate(text.split("\n"), 1):
        m = re.match(r"^(#{1,6})\s+(.+)", line)
        if m:
            headings.append({
                "level": len(m.group(1)),
                "text": m.group(2).strip(),
                "line": i,
            })
    return headings


def extract_h2_sections(text: str) -> List[Dict]:
    """提取所有 H2 段落及其内容。"""
    sections = []
    lines = text.split("\n")
    current = None

    for i, line in enumerate(lines, 1):
        if re.match(r"^##\s+(?!#)", line):
            if current:
                current["content"] = "\n".join(current["_lines"])
                del current["_lines"]
                sections.append(current)
            current = {
                "title": line.lstrip("#").strip(),
                "start_line": i,
                "_lines": [],
            }
        elif current:
            current["_lines"].append(line)

    if current:
        current["content"] = "\n".join(current["_lines"])
        del current["_lines"]
        sections.append(current)

    return sections


def word_count(text: str) -> int:
    """统计字数 (CJK + 英文单词)。"""
    cjk = len(re.findall(r'[\u4e00-\u9fff]', text))
    eng = len(re.findall(r'[a-zA-Z]+', text))
    return cjk + eng


def count_code_blocks(text: str) -> Dict:
    """统计代码块及其语言。"""
    blocks = re.findall(r"```(\w*)", text)
    return {
        "total": len(blocks),
        "labeled": len([b for b in blocks if b]),
        "unlabeled": len([b for b in blocks if not b]),
        "languages": list(set(b for b in blocks if b)),
    }


def heading_to_anchor(text: str) -> str:
    """将标题文本转为 GitHub 风格锚点。"""
    anchor = text.strip().lower()
    anchor = re.sub(r"[^\w\u4e00-\u9fff\s-]", "", anchor)
    anchor = re.sub(r"\s+", "-", anchor)
    return anchor


def extract_links(text: str) -> Dict:
    """提取所有链接，分类为内部/外部。"""
    internal = re.findall(r"\[.*?\]\((?!https?://|#)(.*?)\)", text)
    external = re.findall(r"\[.*?\]\((https?://.*?)\)", text)
    anchors = re.findall(r"\[.*?\]\((#.*?)\)", text)
    return {
        "internal": internal,
        "external": external,
        "anchors": anchors,
    }


def has_section(text: str, section_name: str) -> bool:
    """检查是否存在指定名称的 H2 段落。"""
    patterns = {
        "faq": r"##\s*常见问题|##\s*FAQ",
        "summary": r"##\s*本章小结|##\s*小结|##\s*Summary",
        "references": r"##\s*参考来源|##\s*参考|##\s*References",
        "troubleshooting": r"##\s*故障排查|##\s*Troubleshoot",
        "toc": r"##\s*📑?\s*本章目录|##\s*目录",
    }
    pattern = patterns.get(section_name.lower(), rf"##\s*{section_name}")
    return bool(re.search(pattern, text, re.IGNORECASE))


if __name__ == "__main__":
    pass
