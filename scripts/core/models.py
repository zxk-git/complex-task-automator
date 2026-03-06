#!/usr/bin/env python3
"""
Complex Task Automator - 数据模型
定义任务、工作流和执行相关的数据结构
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime
import uuid


class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class TaskType(Enum):
    """任务类型枚举"""
    SHELL = "shell"
    PYTHON = "python"
    NODE = "node"
    HTTP = "http"
    WEBHOOK = "webhook"
    AGENT = "agent"
    COMPOSITE = "composite"
    CONDITIONAL = "conditional"
    SKILL = "skill"  # 调用本地 OpenClaw Skill


class FailureAction(Enum):
    """失败处理动作"""
    ABORT = "abort"
    CONTINUE = "continue"
    SKIP_DOWNSTREAM = "skip_downstream"
    FALLBACK = "fallback"


class BackoffStrategy(Enum):
    """退避策略"""
    FIXED = "fixed"
    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    RANDOM = "random"


@dataclass
class RetryConfig:
    """重试配置"""
    max_attempts: int = 3
    backoff: BackoffStrategy = BackoffStrategy.EXPONENTIAL
    initial_delay: float = 5.0
    max_delay: float = 300.0
    retry_on: List[str] = field(default_factory=lambda: ["timeout", "connection_error"])
    no_retry_on: List[str] = field(default_factory=list)
    
    def get_delay(self, attempt: int) -> float:
        """计算第N次重试的延迟时间"""
        if self.backoff == BackoffStrategy.FIXED:
            delay = self.initial_delay
        elif self.backoff == BackoffStrategy.LINEAR:
            delay = self.initial_delay * attempt
        elif self.backoff == BackoffStrategy.EXPONENTIAL:
            delay = self.initial_delay * (2 ** (attempt - 1))
        elif self.backoff == BackoffStrategy.RANDOM:
            import random
            delay = random.uniform(self.initial_delay, self.initial_delay * 2)
        else:
            delay = self.initial_delay
            
        return min(delay, self.max_delay)


@dataclass
class TaskConfig:
    """任务配置"""
    # 执行相关
    command: Optional[str] = None
    script: Optional[str] = None
    method: str = "GET"
    url: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    body: Optional[Dict[str, Any]] = None
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    
    # Skill 任务配置
    skill_name: Optional[str] = None  # 要调用的 skill 名称
    
    # 条件执行
    condition: Optional[str] = None
    on_true: List['Task'] = field(default_factory=list)
    on_false: List['Task'] = field(default_factory=list)
    
    # 输出配置
    output: Optional[str] = None
    output_parser: str = "json"  # json/text/xml


@dataclass
class Task:
    """任务定义"""
    id: str
    name: Optional[str] = None
    type: TaskType = TaskType.SHELL
    config: TaskConfig = field(default_factory=TaskConfig)
    
    # 依赖与执行控制
    depends_on: List[str] = field(default_factory=list)
    timeout: Optional[int] = None
    retry: Optional[RetryConfig] = None
    on_failure: FailureAction = FailureAction.ABORT
    fallback_task: Optional[str] = None
    
    # 执行状态（运行时填充）
    status: TaskStatus = TaskStatus.PENDING
    attempts: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    result: Any = None
    error: Optional[str] = None
    
    def __post_init__(self):
        if self.name is None:
            self.name = self.id
        if isinstance(self.type, str):
            self.type = TaskType(self.type)
        if isinstance(self.on_failure, str):
            self.on_failure = FailureAction(self.on_failure)


@dataclass
class TaskResult:
    """任务执行结果"""
    status: TaskStatus
    output: Any = None
    error: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    retryable: bool = False
    
    @property
    def success(self) -> bool:
        return self.status == TaskStatus.COMPLETED


@dataclass
class ExecutionConfig:
    """执行配置"""
    max_parallel: int = 5
    timeout: int = 3600
    retry_policy: RetryConfig = field(default_factory=RetryConfig)


@dataclass
class ScheduleConfig:
    """调度配置"""
    type: str = "once"  # once/cron/interval/event
    cron: Optional[str] = None
    interval: Optional[int] = None  # 秒
    timezone: str = "Asia/Shanghai"
    catch_up: bool = False
    max_concurrent: int = 1
    start_date: Optional[str] = None
    end_date: Optional[str] = None


@dataclass
class NotificationConfig:
    """通知配置"""
    on_start: bool = True
    on_complete: bool = True
    on_failure: bool = True
    channels: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class WorkflowConfig:
    """工作流配置"""
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    notifications: NotificationConfig = field(default_factory=NotificationConfig)


@dataclass
class Hook:
    """钩子定义"""
    type: str  # shell/webhook/python
    command: Optional[str] = None
    url: Optional[str] = None
    script: Optional[str] = None


@dataclass
class Workflow:
    """工作流定义"""
    name: str
    version: str = "1.0"
    description: str = ""
    config: WorkflowConfig = field(default_factory=WorkflowConfig)
    variables: Dict[str, Any] = field(default_factory=dict)
    tasks: List[Task] = field(default_factory=list)
    hooks: Dict[str, List[Hook]] = field(default_factory=dict)
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """根据ID获取任务"""
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None


@dataclass
class ExecutionContext:
    """执行上下文"""
    run_id: str = field(default_factory=lambda: f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}")
    workflow_name: str = ""
    variables: Dict[str, Any] = field(default_factory=dict)
    results: Dict[str, TaskResult] = field(default_factory=dict)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    def set_result(self, task_id: str, result: TaskResult):
        """设置任务结果"""
        self.results[task_id] = result
    
    def get_result(self, task_id: str) -> Optional[TaskResult]:
        """获取任务结果"""
        return self.results.get(task_id)
    
    def get_variable(self, key: str, default: Any = None) -> Any:
        """获取变量"""
        return self.variables.get(key, default)
    
    def set_variable(self, key: str, value: Any):
        """设置变量"""
        self.variables[key] = value


@dataclass
class WorkflowRun:
    """工作流运行记录"""
    run_id: str
    workflow_name: str
    status: TaskStatus
    start_time: datetime
    end_time: Optional[datetime] = None
    task_results: Dict[str, TaskResult] = field(default_factory=dict)
    error: Optional[str] = None
    
    @property
    def duration(self) -> Optional[float]:
        """执行时长（秒）"""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None
    
    @property
    def success(self) -> bool:
        return self.status == TaskStatus.COMPLETED


@dataclass
class LogEntry:
    """日志条目"""
    timestamp: datetime
    workflow_id: str
    run_id: str
    task_id: Optional[str]
    level: str  # DEBUG/INFO/WARN/ERROR/FATAL
    message: str
    context: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "workflow_id": self.workflow_id,
            "run_id": self.run_id,
            "task_id": self.task_id,
            "level": self.level,
            "message": self.message,
            "context": self.context,
            "metrics": self.metrics
        }


@dataclass
class Checkpoint:
    """检查点"""
    run_id: str
    task_id: str
    status: TaskStatus
    result: Any
    timestamp: datetime
    context: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "status": self.status.value,
            "result": self.result,
            "timestamp": self.timestamp.isoformat(),
            "context": self.context
        }
