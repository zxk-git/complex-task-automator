#!/usr/bin/env python3
"""
Git 工作流自动化 — 自动初始化仓库、提交变更、生成 commit message
安全策略：不覆盖未确认改动，支持回滚

依赖：utils.py 共享工具库
"""
import re
from pathlib import Path
from datetime import datetime

from utils import (
    get_project_dir,
    get_output_dir,
    get_git_remote,
    get_git_remote_name,
    run_git,
    save_json,
    setup_logger,
    get_encoding,
    cfg,
)

log = setup_logger("git_workflow")

# ── 配置 ────────────────────────────────────────────
GIT_AUTO_COMMIT = cfg("git.auto_commit", True)
GIT_BRANCH = cfg("git.branch", "main")


def _decode_octal_escapes(s: str) -> str:
    """
    解码 git 对中文文件名的八进制转义。
    例如 '"\\346\\234\\237\\345\\210\\212"' → '期刊'
    git core.quotepath=true 时，非 ASCII 字节被转义为 \\NNN 八进制序列。
    """
    s = s.strip('"').strip("'")
    # 匹配连续的 \\NNN 组序列
    octal_re = re.compile(r'((?:\\[0-3][0-7]{2})+)')

    def _replace(m: re.Match) -> str:
        seq = m.group(1)
        octals = re.findall(r'\\([0-3][0-7]{2})', seq)
        try:
            return bytes(int(o, 8) for o in octals).decode("utf-8")
        except Exception:
            return m.group(0)

    return octal_re.sub(_replace, s)


def init_repo(proj_dir: str) -> dict:
    """初始化 Git 仓库（如果不存在）"""
    git_dir = Path(proj_dir) / ".git"
    if git_dir.is_dir():
        run_git(["config", "core.quotepath", "false"], proj_dir)
        log.debug("仓库已存在，跳过初始化")
        return {"action": "already_initialized", "ok": True}

    result = run_git(["init"], proj_dir)
    if result["ok"]:
        # 创建 .gitignore
        gitignore = Path(proj_dir) / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text(
                "# OpenClaw Tutorial Auto\n"
                ".automation-report.md\n"
                ".task-logs/\n"
                "__pycache__/\n"
                "*.pyc\n"
                ".DS_Store\n",
                encoding=get_encoding(),
            )

        run_git(["checkout", "-b", GIT_BRANCH], proj_dir)
        run_git(["config", "core.quotepath", "false"], proj_dir)

        # 配置用户（如果未配置）
        user_check = run_git(["config", "user.email"], proj_dir)
        if not user_check["ok"] or not user_check["stdout"]:
            run_git(["config", "user.email", "openclaw-automator@local"], proj_dir)
            run_git(["config", "user.name", "OpenClaw Automator"], proj_dir)

        log.info("仓库初始化完成")
        return {"action": "initialized", "ok": True}

    log.error("仓库初始化失败: %s", result["stderr"])
    return {"action": "init_failed", "ok": False, "error": result["stderr"]}


def check_status(proj_dir: str) -> dict:
    """检查仓库状态"""
    status = run_git(["status", "--porcelain"], proj_dir)
    if not status["ok"]:
        return {"ok": False, "error": status["stderr"]}

    changes = []
    for line in status["stdout"].splitlines():
        if line.strip():
            code = line[:2].strip()
            filepath = line[3:].strip()
            change_type = {
                "M": "modified",
                "A": "added",
                "D": "deleted",
                "??": "untracked",
                "R": "renamed",
            }.get(code, "unknown")
            changes.append({"type": change_type, "file": filepath})

    return {
        "ok": True,
        "has_changes": len(changes) > 0,
        "changes": changes,
        "change_count": len(changes),
    }


def generate_commit_message(changes: list) -> str:
    """根据变更内容生成 commit message（正确处理中文文件名）"""
    new_chapters = []
    modified_files = []
    other_files = []

    for c in changes:
        # 解码 git 八进制转义（中文文件名）
        filepath = _decode_octal_escapes(c["file"])
        basename = Path(filepath).name

        if filepath.endswith(".md") and len(basename) > 2 and basename[0:1].isdigit():
            if c["type"] in ("added", "untracked"):
                base = basename.removesuffix(".md")
                name = base.split("-", 1)
                new_chapters.append(name[1] if len(name) > 1 else base)
            else:
                modified_files.append(filepath)
        else:
            other_files.append(filepath)

    parts = []
    if new_chapters:
        parts.append(f"add: 新增章节 {', '.join(new_chapters)}")
    if modified_files:
        parts.append(f"update: 更新 {', '.join(modified_files)}")
    if other_files and not new_chapters and not modified_files:
        parts.append("chore: 更新项目文件")

    if not parts:
        return "chore: 自动化更新"

    message = "; ".join(parts)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"{message} [{ts}]"


def safe_commit(proj_dir: str, changes: list) -> dict:
    """安全提交：只提交匹配 cfg('git.safe_patterns') 的文件"""
    default_patterns = [r'.*\.md"?$', r'.*\.gitignore"?$', r'.*\.json"?$']
    safe_patterns = cfg("git.safe_patterns", default_patterns)

    safe_files = []
    for c in changes:
        filepath = c["file"]
        clean_path = _decode_octal_escapes(filepath)
        is_safe = any(
            re.match(p, filepath) or re.match(p, clean_path)
            for p in safe_patterns
        )
        if is_safe:
            safe_files.append(filepath)

    if not safe_files:
        log.info("没有匹配安全模式的文件可提交")
        return {"action": "no_safe_files", "ok": True, "committed": []}

    # Stage 安全文件
    for f in safe_files:
        run_git(["add", f], proj_dir)

    message = generate_commit_message(changes)
    result = run_git(["commit", "-m", message], proj_dir)
    if result["ok"]:
        hash_result = run_git(["rev-parse", "--short", "HEAD"], proj_dir)
        commit_hash = hash_result["stdout"] if hash_result["ok"] else "unknown"
        log.info("已提交 %d 个文件 [%s] %s", len(safe_files), commit_hash, message)
        return {
            "action": "committed",
            "ok": True,
            "message": message,
            "hash": commit_hash,
            "files": safe_files,
        }

    log.error("提交失败: %s", result["stderr"])
    return {
        "action": "commit_failed",
        "ok": False,
        "error": result["stderr"],
        "files": safe_files,
    }


def push_remote(proj_dir: str) -> dict:
    """推送到远程（使用配置的 remote name，不再动态创建 remote）"""
    remote_url = get_git_remote()
    if not remote_url:
        log.info("未配置远程仓库，跳过推送")
        return {"action": "skip", "reason": "no_remote_configured"}

    remote_name = get_git_remote_name()

    # 确认 remote 存在
    check = run_git(["remote", "get-url", remote_name], proj_dir)
    if not check["ok"]:
        # remote 不存在，尝试添加
        add_result = run_git(["remote", "add", remote_name, remote_url], proj_dir)
        if not add_result["ok"]:
            log.error("添加远程 %s 失败: %s", remote_name, add_result["stderr"])
            return {"action": "add_remote_failed", "ok": False, "error": add_result["stderr"]}
        log.info("已添加远程 %s → %s", remote_name, remote_url)
    else:
        # remote 存在但 URL 可能不同，确保一致
        current_url = check["stdout"]
        if current_url != remote_url:
            run_git(["remote", "set-url", remote_name, remote_url], proj_dir)
            log.info("已更新远程 %s URL → %s", remote_name, remote_url)

    result = run_git(["push", "-u", remote_name, GIT_BRANCH], proj_dir)
    if result["ok"]:
        log.info("已推送到 %s/%s", remote_name, GIT_BRANCH)
    else:
        log.warning("推送失败: %s", result["stdout"] or result["stderr"])

    return {
        "action": "pushed" if result["ok"] else "push_failed",
        "ok": result["ok"],
        "remote_name": remote_name,
        "output": result["stdout"] or result["stderr"],
    }


def run():
    proj_dir = get_project_dir()
    out_dir = Path(get_output_dir())
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "git-result.json"

    log.info("Git 工作流启动 — 项目: %s", proj_dir)

    result = {
        "timestamp": datetime.now().isoformat(),
        "project_dir": proj_dir,
        "steps": [],
        "summary": {},
    }

    # Step 1: 初始化仓库
    init_result = init_repo(proj_dir)
    result["steps"].append({"step": "init", **init_result})

    if not init_result["ok"]:
        result["summary"] = {"ok": False, "error": "Git init failed"}
        save_json(out_file, result)
        return

    # Step 2: 检查状态
    status = check_status(proj_dir)
    result["steps"].append({"step": "status", **status})

    if not status["ok"]:
        result["summary"] = {"ok": False, "error": "Git status failed"}
        save_json(out_file, result)
        return

    if not status["has_changes"]:
        result["summary"] = {"ok": True, "message": "无需提交，工作区干净"}
        log.info("工作区干净，无变更")
        save_json(out_file, result)
        return

    # Step 3: 安全提交
    if GIT_AUTO_COMMIT:
        commit_result = safe_commit(proj_dir, status["changes"])
        result["steps"].append({"step": "commit", **commit_result})

        # Step 4: 推送（可选）
        if commit_result.get("ok") and commit_result.get("action") == "committed":
            push_result = push_remote(proj_dir)
            result["steps"].append({"step": "push", **push_result})
    else:
        log.info("自动提交已禁用 (git.auto_commit=false)")
        result["steps"].append({
            "step": "commit",
            "action": "skipped",
            "reason": "GIT_AUTO_COMMIT=false",
        })

    # 汇总
    committed = any(s.get("action") == "committed" for s in result["steps"])
    result["summary"] = {
        "ok": True,
        "changes": status["change_count"],
        "committed": committed,
        "message": "变更已提交" if committed else "变更未提交",
    }

    save_json(out_file, result)
    log.info("完成 — %s", result["summary"]["message"])


if __name__ == "__main__":
    run()
