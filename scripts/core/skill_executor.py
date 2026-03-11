#!/usr/bin/env python3
"""
Complex Task Automator - Skill 调用模块
支持调用本地 OpenClaw Skills 完成任务
"""

import os
import json
import re
import asyncio
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from .models import Task, TaskResult, TaskStatus, TaskConfig
from .logger import TaskLogger
from .utils import substitute_variables_base


def _which(cmd: str) -> bool:
    """跨平台检查命令是否存在"""
    import shutil
    return shutil.which(cmd) is not None


@dataclass
class SkillInfo:
    """Skill 信息"""
    name: str
    description: str
    path: Path
    commands: List[str] = field(default_factory=list)
    requires_bins: List[str] = field(default_factory=list)
    requires_env: List[str] = field(default_factory=list)
    scripts: Dict[str, str] = field(default_factory=dict)


class SkillManager:
    """Skill 管理器"""
    
    def __init__(self, skills_dir: str = None):
        if skills_dir:
            self.skills_dir = Path(skills_dir)
        else:
            # 默认 OpenClaw skills 目录
            self.skills_dir = Path.home() / ".openclaw" / "workspace" / "skills"
        
        self._skills_cache: Dict[str, SkillInfo] = {}
    
    def list_skills(self) -> List[str]:
        """列出所有可用的 skills"""
        if not self.skills_dir.exists():
            return []
        
        skills = []
        for item in self.skills_dir.iterdir():
            if item.is_dir():
                skill_md = item / "SKILL.md"
                if skill_md.exists():
                    skills.append(item.name)
        
        return sorted(skills)
    
    def get_skill(self, name: str) -> Optional[SkillInfo]:
        """获取 skill 信息"""
        if name in self._skills_cache:
            return self._skills_cache[name]
        
        skill_path = self.skills_dir / name
        skill_md = skill_path / "SKILL.md"
        
        if not skill_md.exists():
            return None
        
        try:
            content = skill_md.read_text(encoding='utf-8')
            info = self._parse_skill_md(name, skill_path, content)
            self._skills_cache[name] = info
            return info
        except Exception as e:
            print(f"Failed to parse skill {name}: {e}")
            return None
    
    def _parse_skill_md(self, name: str, path: Path, content: str) -> SkillInfo:
        """解析 SKILL.md"""
        info = SkillInfo(name=name, description="", path=path)
        
        # 解析 frontmatter
        frontmatter_match = re.search(r'^```+skill\s*\n---\s*\n(.*?)\n---', content, re.DOTALL)
        if frontmatter_match:
            fm_content = frontmatter_match.group(1)
            
            # 解析 description
            desc_match = re.search(r'description:\s*["\']?([^"\'\n]+)', fm_content)
            if desc_match:
                info.description = desc_match.group(1).strip()
            
            # 解析 metadata
            metadata_match = re.search(r'metadata:\s*(\{.*\})', fm_content)
            if metadata_match:
                try:
                    metadata = json.loads(metadata_match.group(1))
                    clawdbot = metadata.get('clawdbot', {})
                    requires = clawdbot.get('requires', {})
                    info.requires_bins = requires.get('bins', [])
                    info.requires_env = requires.get('env', [])
                except (json.JSONDecodeError, ValueError):
                    pass
        
        # 提取代码块中的命令
        code_blocks = re.findall(r'```(?:bash|shell)?\s*\n(.*?)```', content, re.DOTALL)
        for block in code_blocks:
            commands = [line.strip() for line in block.split('\n') 
                       if line.strip() and not line.strip().startswith('#')]
            info.commands.extend(commands)
        
        # 查找 scripts 目录
        scripts_dir = path / "scripts"
        if scripts_dir.exists():
            for script in scripts_dir.iterdir():
                if script.is_file() and script.suffix in ['.py', '.js', '.mjs', '.sh']:
                    info.scripts[script.name] = str(script)
        
        return info
    
    def check_requirements(self, skill: SkillInfo) -> Tuple[bool, List[str]]:
        """检查 skill 依赖"""
        missing = []
        
        # 检查二进制依赖（跨平台）
        for bin_name in skill.requires_bins:
            if not _which(bin_name):
                missing.append(f"binary: {bin_name}")
        
        # 检查环境变量
        for env_name in skill.requires_env:
            if not os.environ.get(env_name):
                missing.append(f"env: {env_name}")
        
        return len(missing) == 0, missing


class SkillTaskExecutor:
    """Skill 任务执行器
    
    NOTE: 不继承 TaskExecutor 以避免循环导入 (engine ↔ skill_executor)。
    但提供相同的接口签名，且复用 substitute_variables_base。
    """
    
    def __init__(self, task: Task, context: Any, logger: TaskLogger):
        self.task = task
        self.context = context
        self.logger = logger
        self.manager = SkillManager()
    
    def substitute_variables(self, value: str) -> str:
        """替换变量（统一使用 substitute_variables_base + skill baseDir）"""
        if not isinstance(value, str):
            return value
        
        result = substitute_variables_base(value, self.context)
        
        # 替换 {{ result.task_id.field }} 格式的引用
        import re as _re

        def _replace_result(match):
            expr = match.group(1).strip()
            if expr.startswith('result.'):
                parts = expr.split('.')
                if len(parts) >= 2:
                    task_id = parts[1]
                    if hasattr(self.context, 'get_result'):
                        task_result = self.context.get_result(task_id)
                        if task_result:
                            val = task_result.output
                            for part in parts[2:]:
                                if isinstance(val, dict):
                                    val = val.get(part)
                            return str(val) if val is not None else ""
            return match.group(0)

        result = _re.sub(r'\{\{(.+?)\}\}', _replace_result, result)

        # 替换 {baseDir} 为 skill 目录
        skill_name = self.task.config.skill_name if hasattr(self.task.config, 'skill_name') else None
        if skill_name:
            skill = self.manager.get_skill(skill_name)
            if skill:
                result = result.replace('{baseDir}', str(skill.path))
        
        return result
    
    async def execute(self) -> TaskResult:
        """执行 skill 任务"""
        config = self.task.config
        
        # 获取 skill 配置
        skill_name = getattr(config, 'skill_name', None) or config.__dict__.get('skill_name')
        if not skill_name:
            return TaskResult(
                status=TaskStatus.FAILED,
                error="Skill name not specified"
            )
        
        # 获取 skill 信息
        skill = self.manager.get_skill(skill_name)
        if not skill:
            return TaskResult(
                status=TaskStatus.FAILED,
                error=f"Skill not found: {skill_name}"
            )
        
        # 检查依赖
        ok, missing = self.manager.check_requirements(skill)
        if not ok:
            return TaskResult(
                status=TaskStatus.FAILED,
                error=f"Missing requirements: {', '.join(missing)}"
            )
        
        # 获取要执行的命令或脚本
        command = getattr(config, 'command', None) or config.__dict__.get('command')
        script = getattr(config, 'script', None) or config.__dict__.get('script')
        args = getattr(config, 'args', []) or config.__dict__.get('args', [])
        
        try:
            if command:
                # 执行命令
                return await self._execute_command(skill, command, args)
            elif script:
                # 执行脚本
                return await self._execute_script(skill, script, args)
            elif skill.commands:
                # 使用 skill 的默认命令
                cmd = skill.commands[0]
                for arg in args:
                    cmd = cmd.replace('{arg}', self.substitute_variables(str(arg)), 1)
                return await self._execute_command(skill, cmd, [])
            else:
                return TaskResult(
                    status=TaskStatus.FAILED,
                    error=f"No command or script specified for skill: {skill_name}"
                )
                
        except Exception as e:
            return TaskResult(
                status=TaskStatus.FAILED,
                error=str(e),
                retryable=True
            )
    
    async def _execute_command(
        self, 
        skill: SkillInfo, 
        command: str, 
        args: List[str]
    ) -> TaskResult:
        """执行命令"""
        # 替换变量
        full_command = self.substitute_variables(command)
        
        # 替换 {baseDir}
        full_command = full_command.replace('{baseDir}', str(skill.path))
        
        # 添加参数
        if args:
            full_command += ' ' + ' '.join(
                f'"{self.substitute_variables(str(arg))}"' 
                for arg in args
            )
        
        # 执行
        process = await asyncio.create_subprocess_shell(
            full_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(skill.path)
        )
        
        timeout = self.task.timeout
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            return TaskResult(
                status=TaskStatus.TIMEOUT,
                error=f"Skill execution timed out after {timeout}s",
                retryable=True
            )
        
        if process.returncode == 0:
            output = stdout.decode('utf-8')
            
            # 尝试解析 JSON 输出
            try:
                output = json.loads(output)
            except (json.JSONDecodeError, ValueError):
                pass
            
            return TaskResult(
                status=TaskStatus.COMPLETED,
                output=output,
                metrics={
                    "skill": skill.name,
                    "exit_code": 0
                }
            )
        else:
            return TaskResult(
                status=TaskStatus.FAILED,
                output=stdout.decode('utf-8'),
                error=stderr.decode('utf-8'),
                metrics={
                    "skill": skill.name,
                    "exit_code": process.returncode
                },
                retryable=True
            )
    
    async def _execute_script(
        self, 
        skill: SkillInfo, 
        script_name: str, 
        args: List[str]
    ) -> TaskResult:
        """执行脚本"""
        # 查找脚本
        script_path = None
        
        if script_name in skill.scripts:
            script_path = skill.scripts[script_name]
        else:
            # 尝试在 scripts 目录查找
            possible_paths = [
                skill.path / "scripts" / script_name,
                skill.path / script_name
            ]
            for p in possible_paths:
                if p.exists():
                    script_path = str(p)
                    break
        
        if not script_path:
            return TaskResult(
                status=TaskStatus.FAILED,
                error=f"Script not found: {script_name}"
            )
        
        # 确定执行器
        ext = Path(script_path).suffix.lower()
        if ext in ['.py']:
            executor = ['python3']
        elif ext in ['.js', '.mjs']:
            executor = ['node']
        elif ext in ['.sh']:
            executor = ['bash']
        else:
            executor = []
        
        # 构建命令
        cmd_parts = executor + [script_path] + [
            self.substitute_variables(str(arg)) for arg in args
        ]
        
        # 执行
        process = await asyncio.create_subprocess_exec(
            *cmd_parts,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(skill.path)
        )
        
        timeout = self.task.timeout
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            return TaskResult(
                status=TaskStatus.TIMEOUT,
                error=f"Script execution timed out after {timeout}s",
                retryable=True
            )
        
        if process.returncode == 0:
            output = stdout.decode('utf-8')
            
            try:
                output = json.loads(output)
            except (json.JSONDecodeError, ValueError):
                pass
            
            return TaskResult(
                status=TaskStatus.COMPLETED,
                output=output,
                metrics={
                    "skill": skill.name,
                    "script": script_name,
                    "exit_code": 0
                }
            )
        else:
            return TaskResult(
                status=TaskStatus.FAILED,
                output=stdout.decode('utf-8'),
                error=stderr.decode('utf-8'),
                metrics={
                    "skill": skill.name,
                    "script": script_name,
                    "exit_code": process.returncode
                },
                retryable=True
            )


# 工具函数
def list_available_skills(skills_dir: str = None) -> List[Dict[str, Any]]:
    """列出所有可用的 skills"""
    manager = SkillManager(skills_dir)
    result = []
    
    for skill_name in manager.list_skills():
        skill = manager.get_skill(skill_name)
        if skill:
            ok, missing = manager.check_requirements(skill)
            result.append({
                "name": skill.name,
                "description": skill.description,
                "ready": ok,
                "missing": missing,
                "has_scripts": len(skill.scripts) > 0,
                "scripts": list(skill.scripts.keys())
            })
    
    return result
