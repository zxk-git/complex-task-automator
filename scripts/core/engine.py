#!/usr/bin/env python3
"""
Complex Task Automator - 执行引擎
核心任务执行与调度逻辑
"""

import asyncio
import subprocess
import json
import os
import sys
import time
import signal
import httpx
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple
import re

from .models import (
    Task, TaskStatus, TaskType, TaskResult, TaskConfig,
    Workflow, WorkflowRun, ExecutionContext, RetryConfig,
    FailureAction, BackoffStrategy,
    ExecutionConfig, ScheduleConfig, NotificationConfig, WorkflowConfig, Hook
)
from .logger import TaskLogger, get_logger
from .skill_executor import SkillTaskExecutor, SkillManager
from .utils import substitute_variables_base


class TaskExecutor:
    """任务执行器基类"""
    
    def __init__(self, task: Task, context: ExecutionContext, logger: TaskLogger):
        self.task = task
        self.context = context
        self.logger = logger
    
    async def execute(self) -> TaskResult:
        """执行任务，需要子类实现"""
        raise NotImplementedError
    
    def substitute_variables(self, value: str) -> str:
        """替换变量"""
        if not isinstance(value, str):
            return value
        
        # 替换 ${var} 格式的变量（使用共享工具函数）
        result = substitute_variables_base(value, self.context)
        
        # 替换 {{ result.task_id.field }} 格式的引用
        def replace_result(match):
            expr = match.group(1).strip()
            if expr.startswith('result.'):
                parts = expr.split('.')
                if len(parts) >= 2:
                    task_id = parts[1]
                    task_result = self.context.get_result(task_id)
                    if task_result:
                        value = task_result.output
                        for part in parts[2:]:
                            if isinstance(value, dict):
                                value = value.get(part)
                        return str(value) if value is not None else ""
            return match.group(0)
        
        result = re.sub(r'\{\{(.+?)\}\}', replace_result, result)
        
        return result


class ShellTaskExecutor(TaskExecutor):
    """Shell 任务执行器"""
    
    async def execute(self) -> TaskResult:
        config = self.task.config
        command = self.substitute_variables(config.command)
        
        try:
            # 准备环境变量
            env = os.environ.copy()
            for key, value in config.env.items():
                env[key] = self.substitute_variables(value)
            
            # 执行命令
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )
            
            # 等待完成，处理超时
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
                    error=f"Task timed out after {timeout}s",
                    retryable=True
                )
            
            if process.returncode == 0:
                return TaskResult(
                    status=TaskStatus.COMPLETED,
                    output=stdout.decode('utf-8'),
                    metrics={"exit_code": 0}
                )
            else:
                return TaskResult(
                    status=TaskStatus.FAILED,
                    output=stdout.decode('utf-8'),
                    error=stderr.decode('utf-8'),
                    metrics={"exit_code": process.returncode},
                    retryable=True
                )
                
        except Exception as e:
            return TaskResult(
                status=TaskStatus.FAILED,
                error=str(e),
                retryable=True
            )


class PythonTaskExecutor(TaskExecutor):
    """Python 脚本任务执行器"""
    
    async def execute(self) -> TaskResult:
        config = self.task.config
        script = self.substitute_variables(config.script)
        args = [self.substitute_variables(arg) for arg in config.args]
        
        try:
            # 准备环境变量
            env = os.environ.copy()
            for key, value in config.env.items():
                env[key] = self.substitute_variables(value)
            
            # 构建命令
            cmd = [sys.executable, script] + args
            
            # 执行
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
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
                    error=f"Task timed out after {timeout}s",
                    retryable=True
                )
            
            if process.returncode == 0:
                # 尝试解析JSON输出
                output = stdout.decode('utf-8')
                try:
                    output = json.loads(output)
                except (json.JSONDecodeError, ValueError):
                    pass
                
                return TaskResult(
                    status=TaskStatus.COMPLETED,
                    output=output,
                    metrics={"exit_code": 0}
                )
            else:
                return TaskResult(
                    status=TaskStatus.FAILED,
                    output=stdout.decode('utf-8'),
                    error=stderr.decode('utf-8'),
                    metrics={"exit_code": process.returncode},
                    retryable=True
                )
                
        except Exception as e:
            return TaskResult(
                status=TaskStatus.FAILED,
                error=str(e),
                retryable=True
            )


class HttpTaskExecutor(TaskExecutor):
    """HTTP 请求任务执行器"""
    
    async def execute(self) -> TaskResult:
        config = self.task.config
        url = self.substitute_variables(config.url)
        method = config.method.upper()
        headers = {k: self.substitute_variables(v) for k, v in config.headers.items()}
        
        # 处理请求体
        body = None
        if config.body:
            body = json.loads(
                self.substitute_variables(json.dumps(config.body))
            )
        
        try:
            timeout = self.task.timeout or 60
            
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=body
                )
                
                # 检查响应状态
                if response.is_success:
                    # 尝试解析JSON
                    try:
                        output = response.json()
                    except (json.JSONDecodeError, ValueError):
                        output = response.text
                    
                    # 如果配置了输出文件，保存响应
                    if config.output:
                        output_path = self.substitute_variables(config.output)
                        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                        with open(output_path, 'w') as f:
                            if isinstance(output, dict):
                                json.dump(output, f, indent=2)
                            else:
                                f.write(str(output))
                    
                    return TaskResult(
                        status=TaskStatus.COMPLETED,
                        output=output,
                        metrics={
                            "status_code": response.status_code,
                            "response_size": len(response.content)
                        }
                    )
                else:
                    # 判断是否可重试
                    retryable = response.status_code in [500, 502, 503, 504, 429]
                    
                    return TaskResult(
                        status=TaskStatus.FAILED,
                        error=f"HTTP {response.status_code}: {response.text[:200]}",
                        metrics={"status_code": response.status_code},
                        retryable=retryable
                    )
                    
        except httpx.TimeoutException:
            return TaskResult(
                status=TaskStatus.TIMEOUT,
                error="HTTP request timed out",
                retryable=True
            )
        except Exception as e:
            return TaskResult(
                status=TaskStatus.FAILED,
                error=str(e),
                retryable=True
            )


class WebhookTaskExecutor(HttpTaskExecutor):
    """Webhook 任务执行器（基于HTTP）"""
    
    async def execute(self) -> TaskResult:
        # 默认使用POST方法
        if not self.task.config.method:
            self.task.config.method = "POST"
        
        return await super().execute()


class NodeTaskExecutor(TaskExecutor):
    """Node.js 脚本任务执行器"""

    async def execute(self) -> TaskResult:
        config = self.task.config
        script = self.substitute_variables(config.script)
        args = [self.substitute_variables(arg) for arg in config.args]

        try:
            env = os.environ.copy()
            for key, value in config.env.items():
                env[key] = self.substitute_variables(value)

            cmd = ["node", script] + args

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            timeout = self.task.timeout
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                return TaskResult(
                    status=TaskStatus.TIMEOUT,
                    error=f"Task timed out after {timeout}s",
                    retryable=True,
                )

            if process.returncode == 0:
                output = stdout.decode("utf-8")
                try:
                    output = json.loads(output)
                except (json.JSONDecodeError, ValueError):
                    pass
                return TaskResult(
                    status=TaskStatus.COMPLETED,
                    output=output,
                    metrics={"exit_code": 0},
                )
            else:
                return TaskResult(
                    status=TaskStatus.FAILED,
                    output=stdout.decode("utf-8"),
                    error=stderr.decode("utf-8"),
                    metrics={"exit_code": process.returncode},
                    retryable=True,
                )
        except Exception as e:
            return TaskResult(
                status=TaskStatus.FAILED, error=str(e), retryable=True
            )


class ExecutionEngine:
    """任务执行引擎"""
    
    # 注册任务执行器
    EXECUTORS = {
        TaskType.SHELL: ShellTaskExecutor,
        TaskType.PYTHON: PythonTaskExecutor,
        TaskType.NODE: NodeTaskExecutor,
        TaskType.HTTP: HttpTaskExecutor,
        TaskType.WEBHOOK: WebhookTaskExecutor,
        TaskType.SKILL: SkillTaskExecutor,  # 调用本地 Skills
    }
    
    def __init__(self, log_dir: str = ".task-logs"):
        self.logger = get_logger(log_dir)
        self._cancelled = False
    
    def parse_workflow(self, config: Dict[str, Any]) -> Workflow:
        """解析工作流配置（完整解析 config/hooks/tasks）"""
        # ---- 解析 execution config ----
        exec_cfg = config.get('config', {}).get('execution', {})
        retry_raw = exec_cfg.get('retry_policy', {})
        execution = ExecutionConfig(
            max_parallel=exec_cfg.get('max_parallel', 5),
            timeout=exec_cfg.get('timeout', 3600),
            retry_policy=RetryConfig(
                max_attempts=retry_raw.get('max_attempts', 3),
                backoff=BackoffStrategy(retry_raw.get('backoff', 'exponential')),
                initial_delay=retry_raw.get('initial_delay', 5),
                max_delay=retry_raw.get('max_delay', 300),
            ) if retry_raw else RetryConfig(),
        )

        # ---- 解析 schedule config ----
        sched_raw = config.get('config', {}).get('schedule', {})
        schedule = ScheduleConfig(**{
            k: v for k, v in sched_raw.items()
            if k in ScheduleConfig.__dataclass_fields__
        }) if sched_raw else ScheduleConfig()

        # ---- 解析 notification config ----
        notif_raw = config.get('config', {}).get('notifications', {})
        notifications = NotificationConfig(
            on_start=notif_raw.get('on_start', True),
            on_complete=notif_raw.get('on_complete', True),
            on_failure=notif_raw.get('on_failure', True),
            channels=notif_raw.get('channels', []),
        ) if notif_raw else NotificationConfig()

        workflow_config = WorkflowConfig(
            execution=execution,
            schedule=schedule,
            notifications=notifications,
        )

        # ---- 解析 hooks ----
        hooks: Dict[str, List] = {}
        for hook_name, hook_list in config.get('hooks', {}).items():
            parsed = []
            for h in (hook_list or []):
                parsed.append(Hook(
                    type=h.get('type', 'shell'),
                    command=h.get('command'),
                    url=h.get('url'),
                    script=h.get('script'),
                ))
            hooks[hook_name] = parsed

        # ---- 解析 tasks ----
        tasks = []
        for task_config in config.get('tasks', []):
            task = Task(
                id=task_config['id'],
                name=task_config.get('name'),
                type=TaskType(task_config.get('type', 'shell')),
                config=TaskConfig(**{
                    k: v for k, v in task_config.get('config', {}).items()
                    if k in TaskConfig.__dataclass_fields__
                }),
                depends_on=task_config.get('depends_on', []),
                timeout=task_config.get('timeout'),
                on_failure=task_config.get('on_failure', 'abort')
            )
            
            # 解析重试配置
            if 'retry' in task_config:
                retry_config = task_config['retry']
                task.retry = RetryConfig(
                    max_attempts=retry_config.get('max_attempts', 3),
                    backoff=BackoffStrategy(retry_config.get('backoff', 'exponential')),
                    initial_delay=retry_config.get('initial_delay', 5),
                    max_delay=retry_config.get('max_delay', 300)
                )
            
            tasks.append(task)
        
        return Workflow(
            name=config.get('name', 'unnamed-workflow'),
            version=config.get('version', '1.0'),
            description=config.get('description', ''),
            config=workflow_config,
            variables=config.get('variables', {}),
            tasks=tasks,
            hooks=hooks,
        )
    
    def build_dependency_graph(self, tasks: List[Task]) -> Dict[str, Set[str]]:
        """构建任务依赖图"""
        graph = {}
        for task in tasks:
            graph[task.id] = set(task.depends_on)
        return graph
    
    def topological_sort(self, tasks: List[Task]) -> List[List[Task]]:
        """拓扑排序，返回可并行执行的任务层级"""
        graph = self.build_dependency_graph(tasks)
        task_map = {task.id: task for task in tasks}
        
        # BFS 进行分层（入度为0的节点组成当前层）
        remaining = set(graph.keys())
        levels = []
        
        while remaining:
            current_level = [
                tid for tid in remaining
                if not (graph[tid] & remaining)  # 所有依赖均已完成
            ]
            
            if not current_level:
                raise ValueError(f"Circular dependency detected among: {remaining}")
            
            levels.append([task_map[tid] for tid in current_level])
            remaining -= set(current_level)
        
        return levels

    # ------------------------------------------------------------------
    # Hook 执行
    # ------------------------------------------------------------------
    async def _run_hooks(
        self,
        hooks: List,
        context: ExecutionContext,
        workflow_name: str,
    ):
        """执行钩子列表（pre_run / post_run / on_failure）"""
        for hook in hooks:
            try:
                if hook.type == "shell" and hook.command:
                    proc = await asyncio.create_subprocess_shell(
                        hook.command,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    await asyncio.wait_for(proc.communicate(), timeout=60)
                elif hook.type == "webhook" and hook.url:
                    async with httpx.AsyncClient(timeout=30) as client:
                        await client.post(hook.url)
                elif hook.type == "python" and hook.script:
                    proc = await asyncio.create_subprocess_exec(
                        sys.executable, hook.script,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    await asyncio.wait_for(proc.communicate(), timeout=120)
            except Exception as exc:
                self.logger.warn(
                    workflow_name,
                    context.run_id,
                    None,
                    f"Hook ({hook.type}) failed: {exc}",
                )
    
    async def execute_task(
        self,
        task: Task,
        context: ExecutionContext,
        workflow_name: str
    ) -> TaskResult:
        """执行单个任务"""
        retry_config = task.retry or RetryConfig(max_attempts=1)
        
        for attempt in range(1, retry_config.max_attempts + 1):
            task.attempts = attempt
            task.start_time = datetime.now()
            task.status = TaskStatus.RUNNING
            
            # 记录任务开始
            self.logger.task_start(
                workflow_name,
                context.run_id,
                task.id,
                attempt,
                retry_config.max_attempts,
                task.timeout
            )
            
            # 获取执行器
            executor_class = self.EXECUTORS.get(task.type)
            if not executor_class:
                return TaskResult(
                    status=TaskStatus.FAILED,
                    error=f"Unknown task type: {task.type}"
                )
            
            executor = executor_class(task, context, self.logger)
            
            # 执行任务
            start_time = time.time()
            result = await executor.execute()
            duration = time.time() - start_time
            
            task.end_time = datetime.now()
            
            if result.success:
                task.status = TaskStatus.COMPLETED
                task.result = result.output
                
                self.logger.task_complete(
                    workflow_name,
                    context.run_id,
                    task.id,
                    duration,
                    len(str(result.output)) if result.output else 0
                )
                
                # 保存检查点
                self.logger.save_checkpoint(
                    workflow_name,
                    context.run_id,
                    task.id,
                    TaskStatus.COMPLETED,
                    result.output
                )
                
                return result
            
            # 任务失败
            will_retry = (
                result.retryable and 
                attempt < retry_config.max_attempts and
                not self._cancelled
            )
            
            self.logger.task_failed(
                workflow_name,
                context.run_id,
                task.id,
                result.error or "Unknown error",
                attempt,
                will_retry
            )
            
            if will_retry:
                delay = retry_config.get_delay(attempt)
                self.logger.info(
                    workflow_name,
                    context.run_id,
                    task.id,
                    f"Retrying in {delay:.1f}s..."
                )
                await asyncio.sleep(delay)
            else:
                task.status = TaskStatus.FAILED
                task.error = result.error
                
                # 保存失败检查点
                self.logger.save_checkpoint(
                    workflow_name,
                    context.run_id,
                    task.id,
                    TaskStatus.FAILED,
                    None,
                    {"error": result.error}
                )
                
                return result
        
        # 重试耗尽
        return TaskResult(
            status=TaskStatus.FAILED,
            error="Max retries exceeded"
        )
    
    async def run(
        self,
        workflow: Workflow,
        context: Optional[ExecutionContext] = None,
        resume_from: Optional[str] = None
    ) -> WorkflowRun:
        """执行工作流"""
        # 初始化上下文
        if context is None:
            context = ExecutionContext(
                workflow_name=workflow.name,
                variables=workflow.variables.copy()
            )
        
        context.start_time = datetime.now()
        
        # 初始化运行记录
        run = WorkflowRun(
            run_id=context.run_id,
            workflow_name=workflow.name,
            status=TaskStatus.RUNNING,
            start_time=context.start_time
        )
        
        # 开始日志记录
        self.logger.start_run(workflow.name, context.run_id)
        
        try:
            # 执行 pre_run 钩子
            if 'pre_run' in workflow.hooks:
                await self._run_hooks(workflow.hooks['pre_run'], context, workflow.name)

            # 拓扑排序
            levels = self.topological_sort(workflow.tasks)
            
            # 处理断点恢复
            skip_until = None
            if resume_from:
                skip_until = resume_from
            
            # 按层级执行
            for level in levels:
                if self._cancelled:
                    break
                
                # 准备可执行的任务
                tasks_to_run = []
                for task in level:
                    # 检查断点恢复
                    if skip_until:
                        if task.id == skip_until:
                            skip_until = None
                        else:
                            # 跳过已完成的任务
                            checkpoint = self.logger.load_checkpoint(
                                workflow.name,
                                context.run_id,
                                task.id
                            )
                            if checkpoint and checkpoint.status == TaskStatus.COMPLETED:
                                context.set_result(task.id, TaskResult(
                                    status=TaskStatus.COMPLETED,
                                    output=checkpoint.result
                                ))
                                continue
                    
                    # 检查依赖是否都成功
                    deps_ok = True
                    for dep_id in task.depends_on:
                        dep_result = context.get_result(dep_id)
                        if not dep_result or not dep_result.success:
                            deps_ok = False
                            break
                    
                    if deps_ok:
                        tasks_to_run.append(task)
                    else:
                        # 跳过此任务
                        task.status = TaskStatus.SKIPPED
                        context.set_result(task.id, TaskResult(
                            status=TaskStatus.SKIPPED,
                            error="Dependency failed"
                        ))
                        self.logger.info(
                            workflow.name,
                            context.run_id,
                            task.id,
                            "Task skipped due to failed dependency"
                        )
                
                # 并行执行当前层级的任务
                if tasks_to_run:
                    # 限制并行数
                    max_parallel = workflow.config.execution.max_parallel
                    semaphore = asyncio.Semaphore(max_parallel)
                    
                    async def run_with_semaphore(t):
                        async with semaphore:
                            return await self.execute_task(t, context, workflow.name)
                    
                    results = await asyncio.gather(*[
                        run_with_semaphore(task)
                        for task in tasks_to_run
                    ])
                    
                    # 处理结果
                    should_abort = False
                    for task, result in zip(tasks_to_run, results):
                        context.set_result(task.id, result)
                        run.task_results[task.id] = result
                        
                        if not result.success:
                            if task.on_failure == FailureAction.ABORT:
                                should_abort = True
                                run.error = f"Task {task.id} failed: {result.error}"
                    
                    if should_abort:
                        run.status = TaskStatus.FAILED
                        break
            
            # 检查最终状态
            if run.status == TaskStatus.RUNNING:
                all_success = all(
                    r.success or r.status == TaskStatus.SKIPPED
                    for r in context.results.values()
                )
                run.status = TaskStatus.COMPLETED if all_success else TaskStatus.FAILED
        
        except Exception as e:
            run.status = TaskStatus.FAILED
            run.error = str(e)
            self.logger.fatal(
                workflow.name,
                context.run_id,
                None,
                f"Workflow execution failed: {e}"
            )
            # 执行 on_failure 钩子
            if 'on_failure' in workflow.hooks:
                try:
                    await self._run_hooks(workflow.hooks['on_failure'], context, workflow.name)
                except Exception:
                    pass
        
        finally:
            # 执行 post_run 钩子
            if 'post_run' in workflow.hooks:
                try:
                    await self._run_hooks(workflow.hooks['post_run'], context, workflow.name)
                except Exception:
                    pass

            run.end_time = datetime.now()
            context.end_time = run.end_time
            self.logger.end_run(workflow.name, context.run_id, run.status)
        
        return run
    
    def cancel(self):
        """取消执行"""
        self._cancelled = True


async def run_workflow_from_file(
    config_path: str,
    variables: Dict[str, Any] = None,
    resume_from: str = None,
    dry_run: bool = False,
    max_parallel: int = None,
    timeout: int = None,
    log_dir: str = ".task-logs",
) -> WorkflowRun:
    """从配置文件执行工作流"""
    import yaml
    
    # 读取配置
    with open(config_path, 'r') as f:
        if config_path.endswith('.json'):
            config = json.load(f)
        else:
            config = yaml.safe_load(f)
    
    # 创建引擎
    engine = ExecutionEngine(log_dir=log_dir)
    
    # 解析工作流
    workflow = engine.parse_workflow(config)
    
    # 合并变量
    if variables:
        workflow.variables.update(variables)

    # CLI 覆盖参数
    if max_parallel is not None:
        workflow.config.execution.max_parallel = max_parallel
    if timeout is not None:
        workflow.config.execution.timeout = timeout
    
    # 干运行模式 — 增强校验
    if dry_run:
        print(f"Workflow: {workflow.name} (v{workflow.version})")
        print(f"Description: {workflow.description}")
        print(f"Tasks: {len(workflow.tasks)}")
        print(f"Max parallel: {workflow.config.execution.max_parallel}")
        print(f"Timeout: {workflow.config.execution.timeout}s")

        # 检查任务 ID 唯一性
        ids = [t.id for t in workflow.tasks]
        dupes = [tid for tid in ids if ids.count(tid) > 1]
        if dupes:
            print(f"[WARN] Duplicate task IDs: {set(dupes)}")

        # 检查依赖引用有效性
        id_set = set(ids)
        for t in workflow.tasks:
            for dep in t.depends_on:
                if dep not in id_set:
                    print(f"[WARN] Task '{t.id}' depends on unknown task '{dep}'")

        levels = engine.topological_sort(workflow.tasks)
        print(f"Execution levels: {len(levels)}")
        for i, level in enumerate(levels):
            print(f"  Level {i+1}: {[t.id for t in level]}")

        if workflow.hooks:
            print(f"Hooks: {', '.join(workflow.hooks.keys())}")

        print("Dry run OK — no execution performed")
        return None
    
    # 执行
    return await engine.run(workflow, resume_from=resume_from)


if __name__ == "__main__":
    # Use task-run.py as the CLI entry point
    print("Use 'python3 task-run.py' to run workflows")
