#!/usr/bin/env python3
"""
Complex Task Automator - 调度器
支持 Cron、间隔、事件触发等调度方式
"""

import asyncio
import json
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field
import time

try:
    from croniter import croniter
    HAS_CRONITER = True
except ImportError:
    HAS_CRONITER = False

from .models import ScheduleConfig, Workflow
from .engine import ExecutionEngine, run_workflow_from_file
from .logger import get_logger


@dataclass
class ScheduledJob:
    """调度任务"""
    job_id: str
    workflow_path: str
    schedule: ScheduleConfig
    enabled: bool = True
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    run_count: int = 0
    variables: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "workflow_path": self.workflow_path,
            "schedule": {
                "type": self.schedule.type,
                "cron": self.schedule.cron,
                "interval": self.schedule.interval,
                "timezone": self.schedule.timezone
            },
            "enabled": self.enabled,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "run_count": self.run_count,
            "variables": self.variables
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ScheduledJob':
        schedule = ScheduleConfig(**data.get('schedule', {}))
        return cls(
            job_id=data['job_id'],
            workflow_path=data['workflow_path'],
            schedule=schedule,
            enabled=data.get('enabled', True),
            last_run=datetime.fromisoformat(data['last_run']) if data.get('last_run') else None,
            next_run=datetime.fromisoformat(data['next_run']) if data.get('next_run') else None,
            run_count=data.get('run_count', 0),
            variables=data.get('variables', {})
        )


class Scheduler:
    """任务调度器"""
    
    def __init__(self, config_dir: str = ".task-config"):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        self.jobs: Dict[str, ScheduledJob] = {}
        self.running = False
        self._lock = asyncio.Lock()
        self._engine = ExecutionEngine()
        self.logger = get_logger()
        
        # 加载已保存的调度任务
        self._load_jobs()
    
    def _load_jobs(self):
        """从文件加载调度任务"""
        jobs_file = self.config_dir / "schedules.json"
        if jobs_file.exists():
            try:
                with open(jobs_file, 'r') as f:
                    data = json.load(f)
                
                for job_data in data.get('jobs', []):
                    job = ScheduledJob.from_dict(job_data)
                    self.jobs[job.job_id] = job
                    
            except Exception as e:
                print(f"Failed to load schedules: {e}")
    
    def _save_jobs(self):
        """保存调度任务到文件"""
        jobs_file = self.config_dir / "schedules.json"
        
        data = {
            "jobs": [job.to_dict() for job in self.jobs.values()],
            "updated_at": datetime.now().isoformat()
        }
        
        with open(jobs_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def _calculate_next_run(self, job: ScheduledJob) -> Optional[datetime]:
        """计算下次运行时间"""
        schedule = job.schedule
        now = datetime.now()
        
        if schedule.type == "once":
            return None  # 一次性任务，已执行则不再调度
        
        elif schedule.type == "cron":
            if not HAS_CRONITER:
                raise RuntimeError("croniter package required for cron schedules")
            
            if not schedule.cron:
                return None
            
            cron = croniter(schedule.cron, now)
            return cron.get_next(datetime)
        
        elif schedule.type == "interval":
            if not schedule.interval:
                return None
            
            if job.last_run:
                return job.last_run + timedelta(seconds=schedule.interval)
            else:
                return now + timedelta(seconds=schedule.interval)
        
        return None
    
    async def add_job(
        self,
        job_id: str,
        workflow_path: str,
        schedule: ScheduleConfig,
        variables: Dict[str, Any] = None
    ) -> ScheduledJob:
        """添加调度任务"""
        async with self._lock:
            job = ScheduledJob(
                job_id=job_id,
                workflow_path=workflow_path,
                schedule=schedule,
                variables=variables or {}
            )
            
            # 计算首次运行时间
            job.next_run = self._calculate_next_run(job)
            
            self.jobs[job_id] = job
            self._save_jobs()
            
            return job
    
    async def remove_job(self, job_id: str) -> bool:
        """移除调度任务"""
        async with self._lock:
            if job_id in self.jobs:
                del self.jobs[job_id]
                self._save_jobs()
                return True
            return False
    
    async def enable_job(self, job_id: str) -> bool:
        """启用调度任务"""
        async with self._lock:
            if job_id in self.jobs:
                self.jobs[job_id].enabled = True
                self.jobs[job_id].next_run = self._calculate_next_run(self.jobs[job_id])
                self._save_jobs()
                return True
            return False
    
    async def disable_job(self, job_id: str) -> bool:
        """禁用调度任务"""
        async with self._lock:
            if job_id in self.jobs:
                self.jobs[job_id].enabled = False
                self._save_jobs()
                return True
            return False
    
    def list_jobs(self) -> List[ScheduledJob]:
        """列出所有调度任务"""
        return list(self.jobs.values())
    
    def get_next_run(self, job_id: str) -> Optional[datetime]:
        """获取下次运行时间"""
        job = self.jobs.get(job_id)
        if job:
            return job.next_run
        return None
    
    async def run_job(self, job_id: str) -> bool:
        """立即运行指定任务"""
        job = self.jobs.get(job_id)
        if not job:
            return False
        
        try:
            result = await run_workflow_from_file(
                job.workflow_path,
                variables=job.variables
            )
            
            async with self._lock:
                job.last_run = datetime.now()
                job.run_count += 1
                job.next_run = self._calculate_next_run(job)
                self._save_jobs()
            
            return result.success if result else False
            
        except Exception as e:
            self.logger.error(
                "scheduler",
                "scheduler",
                None,
                f"Failed to run job {job_id}: {e}"
            )
            return False
    
    async def _scheduler_loop(self):
        """调度循环"""
        while self.running:
            now = datetime.now()
            
            # 检查需要执行的任务
            jobs_to_run = []
            async with self._lock:
                for job in self.jobs.values():
                    if (job.enabled and 
                        job.next_run and 
                        job.next_run <= now):
                        jobs_to_run.append(job.job_id)
            
            # 执行任务
            for job_id in jobs_to_run:
                # 在后台执行，不阻塞调度循环
                asyncio.create_task(self.run_job(job_id))
            
            # 等待一段时间再检查
            await asyncio.sleep(1)
    
    def start(self):
        """启动调度器"""
        if not self.running:
            self.running = True
            asyncio.create_task(self._scheduler_loop())
            print("Scheduler started")
    
    def stop(self):
        """停止调度器"""
        self.running = False
        print("Scheduler stopped")


class EventTrigger:
    """事件触发器"""
    
    def __init__(self, scheduler: Scheduler):
        self.scheduler = scheduler
        self._watchers: Dict[str, 'FileWatcher'] = {}
    
    def watch_file(
        self,
        job_id: str,
        path: str,
        patterns: List[str] = None,
        debounce: int = 60
    ):
        """监控文件变化触发任务"""
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent
        
        class Handler(FileSystemEventHandler):
            def __init__(self, trigger, job_id, patterns, debounce):
                self.trigger = trigger
                self.job_id = job_id
                self.patterns = patterns or ['*']
                self.debounce = debounce
                self.last_trigger = 0
            
            def on_created(self, event):
                if not event.is_directory:
                    self._maybe_trigger(event.src_path)
            
            def on_modified(self, event):
                if not event.is_directory:
                    self._maybe_trigger(event.src_path)
            
            def _maybe_trigger(self, path):
                import fnmatch
                
                # 检查模式匹配
                matched = any(fnmatch.fnmatch(path, p) for p in self.patterns)
                if not matched:
                    return
                
                # 防抖
                now = time.time()
                if now - self.last_trigger < self.debounce:
                    return
                
                self.last_trigger = now
                
                # 触发任务
                asyncio.create_task(self.trigger.scheduler.run_job(self.job_id))
        
        observer = Observer()
        handler = Handler(self, job_id, patterns, debounce)
        observer.schedule(handler, path, recursive=True)
        observer.start()
        
        self._watchers[job_id] = observer
    
    def unwatch(self, job_id: str):
        """停止监控"""
        if job_id in self._watchers:
            self._watchers[job_id].stop()
            del self._watchers[job_id]


# 全局调度器实例
_scheduler: Optional[Scheduler] = None


def get_scheduler() -> Scheduler:
    """获取调度器实例"""
    global _scheduler
    if _scheduler is None:
        _scheduler = Scheduler()
    return _scheduler


# 命令行工具
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Task Scheduler")
    subparsers = parser.add_subparsers(dest="command")
    
    # 列出任务
    list_parser = subparsers.add_parser("list", help="List scheduled jobs")
    
    # 添加任务
    add_parser = subparsers.add_parser("add", help="Add scheduled job")
    add_parser.add_argument("job_id", help="Job ID")
    add_parser.add_argument("workflow", help="Workflow config file")
    add_parser.add_argument("--cron", help="Cron expression")
    add_parser.add_argument("--interval", type=int, help="Interval in seconds")
    
    # 移除任务
    remove_parser = subparsers.add_parser("remove", help="Remove job")
    remove_parser.add_argument("job_id", help="Job ID")
    
    # 启用/禁用
    enable_parser = subparsers.add_parser("enable", help="Enable job")
    enable_parser.add_argument("job_id", help="Job ID")
    
    disable_parser = subparsers.add_parser("disable", help="Disable job")
    disable_parser.add_argument("job_id", help="Job ID")
    
    # 查看下次运行
    next_parser = subparsers.add_parser("next", help="Show next run time")
    next_parser.add_argument("job_id", help="Job ID")
    
    args = parser.parse_args()
    scheduler = get_scheduler()
    
    if args.command == "list":
        jobs = scheduler.list_jobs()
        if jobs:
            print(f"{'Job ID':<20} {'Enabled':<8} {'Next Run':<20} {'Runs':<6}")
            print("-" * 60)
            for job in jobs:
                next_run = job.next_run.strftime('%Y-%m-%d %H:%M:%S') if job.next_run else 'N/A'
                print(f"{job.job_id:<20} {str(job.enabled):<8} {next_run:<20} {job.run_count:<6}")
        else:
            print("No scheduled jobs")
    
    elif args.command == "add":
        schedule = ScheduleConfig()
        if args.cron:
            schedule.type = "cron"
            schedule.cron = args.cron
        elif args.interval:
            schedule.type = "interval"
            schedule.interval = args.interval
        else:
            schedule.type = "once"
        
        job = asyncio.run(scheduler.add_job(args.job_id, args.workflow, schedule))
        print(f"Job added: {job.job_id}")
        if job.next_run:
            print(f"Next run: {job.next_run}")
    
    elif args.command == "remove":
        if asyncio.run(scheduler.remove_job(args.job_id)):
            print(f"Job removed: {args.job_id}")
        else:
            print(f"Job not found: {args.job_id}")
    
    elif args.command == "enable":
        if asyncio.run(scheduler.enable_job(args.job_id)):
            print(f"Job enabled: {args.job_id}")
        else:
            print(f"Job not found: {args.job_id}")
    
    elif args.command == "disable":
        if asyncio.run(scheduler.disable_job(args.job_id)):
            print(f"Job disabled: {args.job_id}")
        else:
            print(f"Job not found: {args.job_id}")
    
    elif args.command == "next":
        next_run = scheduler.get_next_run(args.job_id)
        if next_run:
            print(f"Next run: {next_run}")
        else:
            print("No scheduled run")
