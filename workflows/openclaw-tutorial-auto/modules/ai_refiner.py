#!/usr/bin/env python3
"""
ai_refiner.py — OpenClaw AI 精炼模块
利用 OpenClaw agent CLI 对教程内容和代码进行 AI 驱动的高质量精炼。

功能:
  1. 教程章节 AI 精炼 — 优化行文、补充内容、提升教学质量
  2. 代码 AI 精炼 — 生成 docstrings、重构建议、最佳实践改进
  3. 建议 AI 增强 — 利用 LLM 为分析缺陷生成智能修复建议

使用:
  python -m modules.ai_refiner --mode tutorial --chapter 3
  python -m modules.ai_refiner --mode code --file path/to/file.py
  python -m modules.ai_refiner --mode suggest --report analysis.json
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPT_DIR)

from modules.compat import setup_logger, cfg, load_json, save_json

log = setup_logger("ai_refiner")

# ── 配置 ──────────────────────────────────────────────
OPENCLAW_BIN = os.getenv("OPENCLAW_BIN", "openclaw")
DEFAULT_AGENT = cfg("ai_refiner.agent", "coding")
DEFAULT_THINKING = cfg("ai_refiner.thinking", "medium")
DEFAULT_TIMEOUT = int(cfg("ai_refiner.timeout", "120"))
MAX_CONTENT_LENGTH = int(cfg("ai_refiner.max_content_length", "12000"))
DRY_RUN = os.getenv("DRY_RUN", "").lower() in ("1", "true", "yes")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# OpenClaw Agent 调用层
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def call_openclaw(prompt: str, agent: str = None, thinking: str = None,
                  timeout: int = None) -> dict:
    """
    调用 OpenClaw agent CLI 进行 AI 推理。

    Args:
        prompt: 发送给 agent 的消息
        agent: agent ID (默认 coding)
        thinking: 思考级别 off/minimal/low/medium/high
        timeout: 超时秒数

    Returns:
        {"ok": bool, "content": str, "raw": dict}
    """
    agent = agent or DEFAULT_AGENT
    thinking = thinking or DEFAULT_THINKING
    timeout = timeout or DEFAULT_TIMEOUT

    cmd = [
        OPENCLAW_BIN, "agent",
        "--agent", agent,
        "--message", prompt,
        "--thinking", thinking,
        "--timeout", str(timeout),
        "--json",
    ]

    if DRY_RUN:
        log.info("[DRY_RUN] 跳过 OpenClaw 调用: %s...", prompt[:80])
        return {
            "ok": True,
            "content": f"[DRY_RUN] AI 精炼结果占位 — prompt: {prompt[:100]}...",
            "raw": {},
        }

    log.info("调用 OpenClaw agent=%s thinking=%s...", agent, thinking)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout + 30,  # 额外 30s buffer
            cwd=SCRIPT_DIR,
        )

        if result.returncode != 0:
            log.error("OpenClaw 退出码 %d: %s", result.returncode, result.stderr[:300])
            return {"ok": False, "content": "", "raw": {"stderr": result.stderr[:500]}}

        # 解析 JSON 输出
        try:
            data = json.loads(result.stdout)
            content = data.get("reply", "") or data.get("content", "") or data.get("message", "")
            return {"ok": True, "content": content, "raw": data}
        except json.JSONDecodeError:
            # 非 JSON 输出，直接用 stdout
            return {"ok": True, "content": result.stdout.strip(), "raw": {}}

    except subprocess.TimeoutExpired:
        log.error("OpenClaw 调用超时 (%ds)", timeout)
        return {"ok": False, "content": "", "raw": {"error": "timeout"}}
    except FileNotFoundError:
        log.error("OpenClaw CLI 未找到: %s", OPENCLAW_BIN)
        return {"ok": False, "content": "", "raw": {"error": "openclaw_not_found"}}
    except Exception as e:
        log.error("OpenClaw 调用异常: %s", e)
        return {"ok": False, "content": "", "raw": {"error": str(e)}}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 教程 AI 精炼
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TUTORIAL_REFINE_PROMPT = """你是一位高级技术写作专家。请精炼以下教程章节内容。

## 要求
1. 保持原有结构和章节编号
2. 改善行文流畅度和逻辑连贯性
3. 补充缺失的解释和过渡段落
4. 优化代码示例的注释和说明
5. 确保中英文排版规范（中英之间加空格）
6. 修复任何技术不准确之处
7. 不要删除原有内容，只做优化和补充

## 分析发现的问题
{defects}

## 原始内容
```markdown
{content}
```

请直接输出精炼后的完整 Markdown 内容（不要包含 ```markdown 标记）:"""


def refine_tutorial_chapter(chapter_path: str, defects: list = None,
                            max_length: int = None) -> dict:
    """
    使用 OpenClaw AI 精炼教程章节。

    Args:
        chapter_path: 章节文件路径
        defects: 质量分析发现的缺陷列表
        max_length: 最大内容长度（字符）

    Returns:
        {"ok": bool, "changes": str describing what changed,
         "original_length": int, "refined_length": int}
    """
    max_length = max_length or MAX_CONTENT_LENGTH

    if not os.path.exists(chapter_path):
        return {"ok": False, "error": f"文件不存在: {chapter_path}"}

    content = Path(chapter_path).read_text(encoding="utf-8")
    original_length = len(content)

    # 截断过长内容
    if len(content) > max_length:
        log.warning("内容过长 (%d > %d)，截断处理", len(content), max_length)
        content = content[:max_length] + "\n\n... (内容已截断)"

    # 格式化缺陷信息
    defect_text = "无特定缺陷" if not defects else "\n".join(
        f"- [{d.get('severity', 'info')}] {d.get('type', '?')}: {d.get('message', '')}"
        for d in defects
    )

    prompt = TUTORIAL_REFINE_PROMPT.format(
        content=content,
        defects=defect_text,
    )

    result = call_openclaw(prompt, thinking="high")
    if not result["ok"]:
        return {"ok": False, "error": "OpenClaw 调用失败", "raw": result["raw"]}

    refined = result["content"].strip()

    # 清理可能的 markdown fence
    if refined.startswith("```markdown"):
        refined = refined[len("```markdown"):].strip()
    if refined.startswith("```"):
        refined = refined[3:].strip()
    if refined.endswith("```"):
        refined = refined[:-3].strip()

    refined_length = len(refined)

    # 安全检查：精炼后内容不应过短
    if refined_length < original_length * 0.5:
        log.warning("AI 精炼结果过短 (%d < 50%% of %d)，跳过写入", refined_length, original_length)
        return {"ok": False, "error": "refined_too_short",
                "original_length": original_length, "refined_length": refined_length}

    if not DRY_RUN:
        # 备份
        bak_path = chapter_path + ".ai-bak"
        if not os.path.exists(bak_path):
            Path(bak_path).write_text(
                Path(chapter_path).read_text(encoding="utf-8"), encoding="utf-8"
            )
        # 写入精炼后内容
        Path(chapter_path).write_text(refined, encoding="utf-8")
        log.info("✅ AI 精炼完成: %s (%d → %d 字符)", chapter_path, original_length, refined_length)
    else:
        log.info("[DRY_RUN] AI 精炼: %s (%d → %d 字符)", chapter_path, original_length, refined_length)

    return {
        "ok": True,
        "original_length": original_length,
        "refined_length": refined_length,
        "delta": refined_length - original_length,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 代码 AI 精炼
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CODE_REFINE_PROMPT = """你是一位高级软件工程师。请精炼以下 {language} 代码文件。

## 要求
1. 为缺失 docstring/注释的函数/类添加完整文档
2. 改善代码可读性和结构
3. 修复潜在的 bug 或反模式
4. 优化 import 组织
5. 保持功能不变
6. 不要大规模重构

## 分析发现的问题
{defects}

## 代码
```{language}
{content}
```

请直接输出精炼后的完整代码（不要包含 ```{language} 标记）:"""


def refine_code_file(filepath: str, language: str = "python",
                     defects: list = None) -> dict:
    """使用 OpenClaw AI 精炼代码文件。"""
    if not os.path.exists(filepath):
        return {"ok": False, "error": f"文件不存在: {filepath}"}

    content = Path(filepath).read_text(encoding="utf-8")
    original_length = len(content)

    if len(content) > MAX_CONTENT_LENGTH:
        log.warning("代码文件过长 (%d > %d)，跳过 AI 精炼", len(content), MAX_CONTENT_LENGTH)
        return {"ok": False, "error": "file_too_long", "length": len(content)}

    defect_text = "无特定缺陷" if not defects else "\n".join(
        f"- [{d.get('severity', 'info')}] {d.get('type', '?')}: {d.get('message', '')}"
        for d in defects
    )

    prompt = CODE_REFINE_PROMPT.format(
        language=language,
        content=content,
        defects=defect_text,
    )

    result = call_openclaw(prompt, thinking="high")
    if not result["ok"]:
        return {"ok": False, "error": "OpenClaw 调用失败", "raw": result["raw"]}

    refined = result["content"].strip()
    # 清理 fence
    fence_pattern = re.compile(r'^```\w*\n?', re.MULTILINE)
    refined = fence_pattern.sub('', refined).rstrip('`').strip()

    refined_length = len(refined)

    if refined_length < original_length * 0.3:
        log.warning("AI 结果过短，跳过")
        return {"ok": False, "error": "refined_too_short"}

    if not DRY_RUN:
        bak_path = filepath + ".ai-bak"
        if not os.path.exists(bak_path):
            Path(bak_path).write_text(content, encoding="utf-8")
        Path(filepath).write_text(refined, encoding="utf-8")
        log.info("✅ AI 代码精炼: %s (%d → %d)", filepath, original_length, refined_length)
    else:
        log.info("[DRY_RUN] AI 代码精炼: %s", filepath)

    return {"ok": True, "original_length": original_length,
            "refined_length": refined_length}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 智能建议生成
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SUGGEST_PROMPT = """你是一位技术写作专家，请根据以下质量分析报告，为每个问题生成具体可执行的修复建议。

## 分析摘要
- 文件: {file}
- 质量分数: {score}/100
- 等级: {grade}

## 缺陷列表
{defects}

请为每个缺陷输出一个 JSON 数组，每项包含:
- "defect_type": 缺陷类型
- "suggestion": 具体修复建议 (中文)
- "priority": "high" / "medium" / "low"
- "auto_fixable": true/false

只输出 JSON 数组，不要其他文字:"""


def generate_ai_suggestions(file_path: str, score: float, grade: str,
                            defects: list) -> list:
    """使用 AI 为分析缺陷生成智能修复建议。"""
    if not defects:
        return []

    defect_text = "\n".join(
        f"- [{d.get('severity', '?')}] {d.get('type', '?')}: {d.get('message', '')}"
        for d in defects
    )

    prompt = SUGGEST_PROMPT.format(
        file=file_path, score=score, grade=grade, defects=defect_text
    )

    result = call_openclaw(prompt, thinking="low", timeout=60)
    if not result["ok"]:
        log.warning("AI 建议生成失败: %s", file_path)
        return []

    content = result["content"].strip()
    # 提取 JSON
    try:
        # 尝试直接解析
        suggestions = json.loads(content)
        if isinstance(suggestions, list):
            return suggestions
    except json.JSONDecodeError:
        pass

    # 尝试从 markdown code block 中提取
    match = re.search(r'```(?:json)?\s*\n(.*?)\n```', content, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    log.warning("无法解析 AI 建议输出: %s...", content[:200])
    return []


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Pipeline 集成入口
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def ai_refine_batch(chapters: list = None, code_files: list = None,
                    analysis_report: dict = None) -> dict:
    """
    批量 AI 精炼入口 — 供 pipeline 调用。

    Args:
        chapters: [{"path": ..., "defects": [...], "chapter": N}, ...]
        code_files: [{"path": ..., "language": ..., "defects": [...]}, ...]
        analysis_report: 完整分析报告 (自动提取 chapters/files)

    Returns:
        {"tutorial": [...results], "code": [...results], "suggestions": [...]}
    """
    results = {"tutorial": [], "code": [], "suggestions": []}

    # 从分析报告自动提取
    if analysis_report and not chapters and not code_files:
        chapters = []
        for ch in analysis_report.get("chapters", []):
            chapters.append({
                "path": ch.get("file", ""),
                "defects": ch.get("defects", []),
                "chapter": ch.get("chapter", 0),
                "score": ch.get("quality_score", 0),
                "grade": ch.get("grade", "?"),
            })
        code_files = []
        for f in analysis_report.get("files", []):
            code_files.append({
                "path": f.get("file", ""),
                "language": f.get("language", "python"),
                "defects": f.get("defects", []),
            })

    # 教程精炼
    for ch in (chapters or []):
        path = ch.get("path", "")
        if not path or not os.path.exists(path):
            continue
        r = refine_tutorial_chapter(path, ch.get("defects"))
        r["chapter"] = ch.get("chapter", 0)
        results["tutorial"].append(r)

        # 同时生成 AI 建议
        if ch.get("defects"):
            suggestions = generate_ai_suggestions(
                path, ch.get("score", 0), ch.get("grade", "?"), ch["defects"]
            )
            results["suggestions"].extend(suggestions)

    # 代码精炼
    for f in (code_files or []):
        path = f.get("path", "")
        if not path or not os.path.exists(path):
            continue
        r = refine_code_file(path, f.get("language", "python"), f.get("defects"))
        r["file"] = path
        results["code"].append(r)

    return results


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CLI
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="OpenClaw AI 精炼模块")
    parser.add_argument("--mode", choices=["tutorial", "code", "suggest"], required=True)
    parser.add_argument("--file", "-f", help="文件路径")
    parser.add_argument("--chapter", "-c", type=int, help="章节号")
    parser.add_argument("--report", help="分析报告 JSON 路径")
    parser.add_argument("--language", "-l", default="python", help="代码语言")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        os.environ["DRY_RUN"] = "1"
        DRY_RUN = True

    if args.mode == "tutorial":
        if not args.file:
            print("--file 必须指定教程章节路径")
            sys.exit(1)
        result = refine_tutorial_chapter(args.file)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.mode == "code":
        if not args.file:
            print("--file 必须指定代码文件路径")
            sys.exit(1)
        result = refine_code_file(args.file, args.language)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.mode == "suggest":
        if not args.report:
            print("--report 必须指定分析报告 JSON")
            sys.exit(1)
        report = load_json(args.report)
        result = ai_refine_batch(analysis_report=report)
        print(json.dumps(result, indent=2, ensure_ascii=False))
