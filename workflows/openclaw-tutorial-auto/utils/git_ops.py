#!/usr/bin/env python3
"""
git_ops.py — 统一 Git 操作
==============================
所有 Git 操作统一通过此模块执行，消除多处重复。
"""

import os
import re
import subprocess
import sys

# ── 兼容 utils 导入 ────────────────────────────────
_SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

try:
    from utils import setup_logger, cfg
except ImportError:
    import logging
    def setup_logger(name):
        """setup_logger 的功能描述。

            Args:
                name: ...
            """
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
        return logging.getLogger(name)
    def cfg(key, default=None):
        """cfg 的功能描述。

            Args:
                key: ...
                default: ...
            """
        return os.environ.get(key.replace(".", "_").upper(), default)

log = setup_logger("git_ops")


def run_git(*args, cwd=None):
    """执行 git 命令，返回 (returncode, stdout, stderr)。"""
    cwd = cwd or cfg("project_dir",
                      "/root/.openclaw/workspace/zxk-private/openclaw-tutorial-auto")
    try:
        result = subprocess.run(
            ["git"] + list(args),
            capture_output=True, text=True, cwd=cwd, timeout=30,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except Exception as e:
        return -1, "", str(e)


def decode_octal_escapes(text: str) -> str:
    """解码 Git 对中文文件名的八进制转义。"""
    def _replace(m):
        octals = m.group(0)
        try:
            byte_values = [int(o, 8) for o in re.findall(r"\\(\d{3})", octals)]
            return bytes(byte_values).decode("utf-8")
        except Exception:
            return octals

    return re.sub(r'(?:\\[0-9]{3})+', _replace, text.strip('"'))


def get_status(cwd=None):
    """获取 Git 工作区状态。"""
    code, out, _ = run_git("status", "--porcelain", cwd=cwd)
    if code != 0:
        return []
    files = []
    for line in out.split("\n"):
        if not line.strip():
            continue
        status = line[:2].strip()
        filepath = line[3:].strip()
        filepath = decode_octal_escapes(filepath)
        files.append({"status": status, "file": filepath})
    return files


def safe_add(patterns=None, cwd=None):
    """安全添加文件 (仅匹配白名单模式)。"""
    safe_patterns = patterns or [r".*\.md$", r".*\.gitignore$", r".*\.json$"]
    status_files = get_status(cwd)
    added = []

    for item in status_files:
        f = item["file"]
        if any(re.match(pat, f) for pat in safe_patterns):
            code, _, err = run_git("add", f, cwd=cwd)
            if code == 0:
                added.append(f)
            else:
                log.warning(f"git add 失败: {f} — {err}")

    return added


def commit(message: str, cwd=None):
    """提交变更。"""
    code, out, err = run_git("commit", "-m", message, cwd=cwd)
    if code == 0:
        log.info(f"Git commit: {message}")
        return True
    elif "nothing to commit" in (out + err):
        log.info("无变更需要提交")
        return False
    else:
        log.error(f"Git commit 失败: {err}")
        return False


def push(remote_name=None, branch=None, cwd=None):
    """推送到远程。"""
    remote = remote_name or cfg("git.remote_name", "origin")
    branch = branch or cfg("git.branch", "main")

    code, out, err = run_git("push", remote, branch, cwd=cwd)
    if code == 0:
        log.info(f"Git push 成功: {remote}/{branch}")
        return True
    else:
        log.error(f"Git push 失败: {err}")
        return False


def auto_commit_and_push(message: str = None, cwd=None):
    """一键安全提交并推送。"""
    cwd = cwd or cfg("project_dir",
                      "/root/.openclaw/workspace/zxk-private/openclaw-tutorial-auto")

    # 安全添加
    added = safe_add(cwd=cwd)
    if not added:
        log.info("无文件变更，跳过提交")
        return {"committed": False, "pushed": False, "files": []}

    # 生成提交消息
    if not message:
        message = _generate_commit_message(added)

    # 提交
    committed = commit(message, cwd=cwd)
    if not committed:
        return {"committed": False, "pushed": False, "files": added}

    # 推送
    pushed = push(cwd=cwd)

    return {"committed": True, "pushed": pushed, "files": added, "message": message}


def _generate_commit_message(files: list) -> str:
    """基于变更文件生成 commit 消息。"""
    md_files = [f for f in files if f.endswith(".md")]
    if md_files:
        if len(md_files) == 1:
            return f"docs: 优化 {os.path.basename(md_files[0])}"
        else:
            return f"docs: 优化 {len(md_files)} 个章节"
    return f"chore: 更新 {len(files)} 个文件"


if __name__ == "__main__":
    pass
