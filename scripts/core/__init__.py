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
    HttpTaskExecutor,
    WebhookTaskExecutor,
    run_workflow_from_file
)

from .logger import (
    TaskLogger,
    get_logger
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
    'HttpTaskExecutor',
    'WebhookTaskExecutor',
    'run_workflow_from_file',
    
    # Logger
    'TaskLogger',
    'get_logger',
    
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
]

__version__ = "2.3.0"
