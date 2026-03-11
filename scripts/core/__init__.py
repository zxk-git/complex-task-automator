#!/usr/bin/env python3
"""
Complex Task Automator - 核心模块
"""

from .models import (
    Task, TaskStatus, TaskType, TaskResult, TaskConfig,
    Workflow, WorkflowRun, ExecutionContext,
    RetryConfig, BackoffStrategy, FailureAction,
    ScheduleConfig, NotificationConfig, WorkflowConfig,
    LogEntry, Checkpoint
)

from .engine import (
    ExecutionEngine,
    TaskExecutor,
    ShellTaskExecutor,
    PythonTaskExecutor,
    NodeTaskExecutor,
    HttpTaskExecutor,
    WebhookTaskExecutor,
    run_workflow_from_file
)

from .logger import (
    TaskLogger,
    get_logger,
    reset_logger
)

from .scheduler import (
    Scheduler,
    ScheduledJob,
    EventTrigger,
    get_scheduler
)

from .skill_executor import (
    SkillTaskExecutor,
    SkillManager,
    SkillInfo,
    list_available_skills
)

from .utils import (
    substitute_variables_base,
    safe_read_file,
    safe_write_file,
    safe_read_json,
    safe_write_json,
    resolve_path,
    ensure_dir,
    load_yaml,
    which,
)

__all__ = [
    # Models
    'Task', 'TaskStatus', 'TaskType', 'TaskResult', 'TaskConfig',
    'Workflow', 'WorkflowRun', 'ExecutionContext',
    'RetryConfig', 'BackoffStrategy', 'FailureAction',
    'ScheduleConfig', 'NotificationConfig', 'WorkflowConfig',
    'LogEntry', 'Checkpoint',
    
    # Engine
    'ExecutionEngine',
    'TaskExecutor',
    'ShellTaskExecutor',
    'PythonTaskExecutor',
    'NodeTaskExecutor',
    'HttpTaskExecutor',
    'WebhookTaskExecutor',
    'run_workflow_from_file',
    
    # Logger
    'TaskLogger',
    'get_logger',
    'reset_logger',
    
    # Scheduler
    'Scheduler',
    'ScheduledJob',
    'EventTrigger',
    'get_scheduler',
    
    # Skill Executor
    'SkillTaskExecutor',
    'SkillManager',
    'SkillInfo',
    'list_available_skills',

    # Utils
    'substitute_variables_base',
    'safe_read_file',
    'safe_write_file',
    'safe_read_json',
    'safe_write_json',
    'resolve_path',
    'ensure_dir',
    'load_yaml',
    'which',
]

__version__ = "2.4.0"
