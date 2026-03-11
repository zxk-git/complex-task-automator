#!/usr/bin/env python3
"""
task_queue.py — Pipeline 异步任务队列
=======================================
支持:
  - 提交 pipeline 任务到队列
  - Worker 并发执行 (可配置)
  - 任务状态追踪: pending → running → done/failed
  - 任务优先级
  - 任务取消 / 超时
  - 持久化队列状态到 JSON

## 使用方式

    from task_queue import TaskQueue, Task

    tq = TaskQueue(workers=2)
    tq.start()

    # 提交教程优化任务
    task_id = tq.submit(Task(
        task_type="tutorial",
        params={"stages": ["scan", "analyze"], "dry_run": True},
        priority=1,
    ))

    # 提交代码优化任务
    tq.submit(Task(
        task_type="code",
        params={"project_dir": "/path/to/project", "dry_run": True},
    ))

    # 查询状态
    status = tq.get_status(task_id)

    # 等待完成
    tq.wait()
    tq.stop()
"""

from __future__ import annotations

import json
import os
import queue
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from modules.compat import setup_logger, save_json, load_json

log = setup_logger("task_queue")

_ROOT = os.path.dirname(os.path.abspath(__file__))


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


@dataclass
class Task:
    """一个 Pipeline 任务。"""
    task_type: str               # "tutorial" | "code" | custom
    params: Dict[str, Any] = field(default_factory=dict)
    priority: int = 5            # 1 (最高) ~ 10 (最低)
    timeout: float = 0           # 超时秒数 (0 = 无限)
    task_id: str = ""
    status: TaskStatus = TaskStatus.PENDING
    created_at: str = ""
    started_at: str = ""
    finished_at: str = ""
    result: Optional[Dict] = None
    error: str = ""
    worker: str = ""

    def __post_init__(self):
        if not self.task_id:
            self.task_id = str(uuid.uuid4())[:8]
        if not self.created_at:
            self.created_at = datetime.now(tz=timezone.utc).isoformat()

    def __lt__(self, other):
        """优先级比较 (用于 PriorityQueue)。"""
        return self.priority < other.priority

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d


class TaskQueue:
    """异步任务队列管理器。"""

    def __init__(self, workers: int = 2, persist_file: str = None):
        self.num_workers = workers
        self.persist_file = persist_file or os.path.join(
            _ROOT, ".task-queue-state.json")

        self._queue: queue.PriorityQueue = queue.PriorityQueue()
        self._tasks: Dict[str, Task] = {}
        self._workers: List[threading.Thread] = []
        self._running = False
        self._lock = threading.Lock()
        self._done_event = threading.Event()

        # 任务类型 → 执行器映射
        self._executors: Dict[str, Callable] = {
            "tutorial": self._exec_tutorial,
            "code": self._exec_code,
        }

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 生命周期
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def start(self):
        """启动 Worker 线程。"""
        if self._running:
            return
        self._running = True
        self._done_event.clear()

        for i in range(self.num_workers):
            worker_name = f"worker-{i}"
            t = threading.Thread(
                target=self._worker_loop,
                args=(worker_name,),
                name=worker_name,
                daemon=True,
            )
            self._workers.append(t)
            t.start()

        log.info(f"任务队列启动: {self.num_workers} workers")

    def stop(self, wait: bool = True):
        """停止所有 Worker。"""
        self._running = False
        # 放入毒丸让 worker 退出
        for _ in self._workers:
            self._queue.put((0, None))
        if wait:
            for t in self._workers:
                t.join(timeout=5)
        self._workers.clear()
        self._persist()
        log.info("任务队列已停止")

    def wait(self, timeout: float = None) -> bool:
        """等待所有任务完成。"""
        start = time.time()
        while True:
            with self._lock:
                pending = sum(1 for t in self._tasks.values()
                              if t.status in (TaskStatus.PENDING, TaskStatus.RUNNING))
            if pending == 0:
                return True
            if timeout and (time.time() - start) > timeout:
                return False
            time.sleep(0.5)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 提交 & 管理
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def submit(self, task: Task) -> str:
        """提交任务到队列。返回 task_id。"""
        with self._lock:
            self._tasks[task.task_id] = task
        self._queue.put((task.priority, task))
        log.info(f"提交任务: {task.task_id} ({task.task_type}) priority={task.priority}")
        return task.task_id

    def cancel(self, task_id: str) -> bool:
        """取消待执行的任务。"""
        with self._lock:
            task = self._tasks.get(task_id)
            if task and task.status == TaskStatus.PENDING:
                task.status = TaskStatus.CANCELLED
                task.finished_at = datetime.now(tz=timezone.utc).isoformat()
                log.info(f"取消任务: {task_id}")
                return True
        return False

    def get_status(self, task_id: str) -> Optional[Dict]:
        """查询任务状态。"""
        with self._lock:
            task = self._tasks.get(task_id)
            return task.to_dict() if task else None

    def list_tasks(self, status: TaskStatus = None) -> List[Dict]:
        """列出所有任务。"""
        with self._lock:
            tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        return [t.to_dict() for t in sorted(tasks, key=lambda x: x.created_at)]

    def register_executor(self, task_type: str, fn: Callable):
        """注册自定义任务类型执行器。"""
        self._executors[task_type] = fn
        log.info(f"注册执行器: {task_type}")

    def clear_completed(self) -> int:
        """清理已完成/失败的任务。"""
        with self._lock:
            to_remove = [tid for tid, t in self._tasks.items()
                         if t.status in (TaskStatus.DONE, TaskStatus.FAILED,
                                         TaskStatus.CANCELLED, TaskStatus.TIMEOUT)]
            for tid in to_remove:
                del self._tasks[tid]
        return len(to_remove)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Worker 循环
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _worker_loop(self, worker_name: str):
        """Worker 线程主循环。"""
        log.debug(f"{worker_name} 启动")
        while self._running:
            try:
                priority, task = self._queue.get(timeout=1)
            except queue.Empty:
                continue

            # 毒丸退出
            if task is None:
                break

            # 已取消的任务跳过
            if task.status == TaskStatus.CANCELLED:
                continue

            self._execute_task(task, worker_name)
            self._persist()

        log.debug(f"{worker_name} 退出")

    def _execute_task(self, task: Task, worker_name: str):
        """执行单个任务。"""
        with self._lock:
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now(tz=timezone.utc).isoformat()
            task.worker = worker_name

        executor = self._executors.get(task.task_type)
        if not executor:
            with self._lock:
                task.status = TaskStatus.FAILED
                task.error = f"未知任务类型: {task.task_type}"
                task.finished_at = datetime.now(tz=timezone.utc).isoformat()
            log.error(f"任务 {task.task_id} 失败: 未知类型 {task.task_type}")
            return

        log.info(f"[{worker_name}] 执行任务: {task.task_id} ({task.task_type})")
        start = time.time()

        try:
            if task.timeout > 0:
                result = self._exec_with_timeout(executor, task.params, task.timeout)
            else:
                result = executor(task.params)

            elapsed = time.time() - start
            with self._lock:
                task.status = TaskStatus.DONE
                task.result = result if isinstance(result, dict) else {"output": str(result)}
                task.finished_at = datetime.now(tz=timezone.utc).isoformat()

            log.info(f"[{worker_name}] 任务完成: {task.task_id} ({elapsed:.1f}s)")

        except TimeoutError:
            with self._lock:
                task.status = TaskStatus.TIMEOUT
                task.error = f"超时 ({task.timeout}s)"
                task.finished_at = datetime.now(tz=timezone.utc).isoformat()
            log.error(f"[{worker_name}] 任务超时: {task.task_id}")

        except Exception as e:
            with self._lock:
                task.status = TaskStatus.FAILED
                task.error = str(e)
                task.finished_at = datetime.now(tz=timezone.utc).isoformat()
            log.error(f"[{worker_name}] 任务失败: {task.task_id}: {e}")
            traceback.print_exc()

    @staticmethod
    def _exec_with_timeout(fn, params, timeout):
        """带超时的执行。"""
        result_holder = [None]
        error_holder = [None]

        def target():
            try:
                result_holder[0] = fn(params)
            except Exception as e:
                error_holder[0] = e

        t = threading.Thread(target=target, daemon=True)
        t.start()
        t.join(timeout=timeout)

        if t.is_alive():
            raise TimeoutError(f"执行超时 ({timeout}s)")
        if error_holder[0]:
            raise error_holder[0]
        return result_holder[0]

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 内置执行器
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @staticmethod
    def _exec_tutorial(params: dict) -> dict:
        """执行教程优化 pipeline。"""
        import sys
        _root = os.path.dirname(os.path.abspath(__file__))
        if _root not in sys.path:
            sys.path.insert(0, _root)

        from pipeline import Pipeline
        p = Pipeline(
            max_chapters=params.get("max_chapters"),
            dry_run=params.get("dry_run", False),
            stages=params.get("stages"),
            web_search=params.get("web_search", False),
            check_external=params.get("check_external", False),
        )
        return p.run()

    @staticmethod
    def _exec_code(params: dict) -> dict:
        """执行代码优化 pipeline。"""
        import sys
        _root = os.path.dirname(os.path.abspath(__file__))
        if _root not in sys.path:
            sys.path.insert(0, _root)

        from code_pipeline import CodePipeline
        cp = CodePipeline(
            project_dir=params.get("project_dir", os.getcwd()),
            output_dir=params.get("output_dir"),
            max_files=params.get("max_files"),
            dry_run=params.get("dry_run", False),
            stages=params.get("stages"),
            extensions=params.get("extensions"),
        )
        return cp.run()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 持久化
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _persist(self):
        """保存队列状态到文件。"""
        try:
            with self._lock:
                data = {
                    "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                    "tasks": {tid: t.to_dict() for tid, t in self._tasks.items()},
                }
            save_json(self.persist_file, data)
        except Exception:
            pass  # 持久化失败不影响运行

    def restore(self) -> int:
        """从文件恢复未完成的任务。"""
        data = load_json(self.persist_file)
        if not data:
            return 0
        restored = 0
        for tid, tdata in data.get("tasks", {}).items():
            if tdata.get("status") in ("pending", "running"):
                task = Task(
                    task_type=tdata["task_type"],
                    params=tdata.get("params", {}),
                    priority=tdata.get("priority", 5),
                    timeout=tdata.get("timeout", 0),
                    task_id=tid,
                )
                self.submit(task)
                restored += 1
        log.info(f"恢复 {restored} 个未完成任务")
        return restored

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 统计
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def stats(self) -> Dict:
        """返回队列统计。"""
        with self._lock:
            tasks = list(self._tasks.values())
        by_status = {}
        for t in tasks:
            by_status[t.status.value] = by_status.get(t.status.value, 0) + 1
        return {
            "total": len(tasks),
            "by_status": by_status,
            "queue_size": self._queue.qsize(),
            "workers": self.num_workers,
            "running": self._running,
        }

    def __repr__(self):
        s = self.stats()
        return (f"<TaskQueue workers={s['workers']} "
                f"total={s['total']} queue={s['queue_size']}>")


# ── CLI ───────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Pipeline 任务队列")
    parser.add_argument("--workers", type=int, default=2, help="Worker 数量")
    sub = parser.add_subparsers(dest="cmd")

    sub_tutorial = sub.add_parser("tutorial", help="提交教程优化任务")
    sub_tutorial.add_argument("--dry-run", action="store_true")
    sub_tutorial.add_argument("--stages", nargs="+")
    sub_tutorial.add_argument("--max-chapters", type=int)

    sub_code = sub.add_parser("code", help="提交代码优化任务")
    sub_code.add_argument("project_dir", nargs="?", default=".")
    sub_code.add_argument("--dry-run", action="store_true")
    sub_code.add_argument("--stages", nargs="+")

    sub_status = sub.add_parser("status", help="查看队列状态")

    args = parser.parse_args()

    tq = TaskQueue(workers=args.workers)
    tq.start()

    if args.cmd == "tutorial":
        tid = tq.submit(Task(
            task_type="tutorial",
            params={
                "dry_run": args.dry_run,
                "stages": args.stages,
                "max_chapters": args.max_chapters,
            },
        ))
        print(f"任务已提交: {tid}")
        tq.wait()
        status = tq.get_status(tid)
        print(f"状态: {status['status']}")

    elif args.cmd == "code":
        tid = tq.submit(Task(
            task_type="code",
            params={
                "project_dir": args.project_dir,
                "dry_run": args.dry_run,
                "stages": args.stages,
            },
        ))
        print(f"任务已提交: {tid}")
        tq.wait()
        status = tq.get_status(tid)
        print(f"状态: {status['status']}")

    elif args.cmd == "status":
        print(tq.stats())

    else:
        parser.print_help()

    tq.stop()
