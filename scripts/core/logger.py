#!/usr/bin/env python3
"""
Complex Task Automator - 日志系统
提供结构化日志记录和执行追踪
"""

import json
import os
import logging
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional
from dataclasses import asdict

from .models import LogEntry, Checkpoint, TaskStatus


class TaskLogger:
    """任务日志记录器
    
    支持上下文管理器:
        with TaskLogger() as logger:
            logger.start_run(...)
    """
    
    def __init__(self, log_dir: str = ".task-logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建子目录
        (self.log_dir / "workflows").mkdir(exist_ok=True)
        (self.log_dir / "tasks").mkdir(exist_ok=True)
        (self.log_dir / "summary").mkdir(exist_ok=True)
        
        # 配置Python日志（防止重复 handler）
        self.logger = logging.getLogger("task_automator")
        self.logger.setLevel(logging.DEBUG)
        
        if not self.logger.handlers:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(
                logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
            )
            self.logger.addHandler(console_handler)
        
        # 当前运行的日志文件句柄
        self._current_run_id: Optional[str] = None
        self._file_handler: Optional[logging.FileHandler] = None
        self._json_file: Optional[Any] = None

    # 上下文管理器支持
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
    
    def start_run(self, workflow_name: str, run_id: str):
        """开始新的运行，初始化日志文件"""
        self._current_run_id = run_id
        
        # 创建工作流日志目录
        workflow_dir = self.log_dir / "workflows" / workflow_name
        workflow_dir.mkdir(parents=True, exist_ok=True)
        
        # 添加文件处理器
        log_file = workflow_dir / f"{run_id}.log"
        self._file_handler = logging.FileHandler(log_file, encoding='utf-8')
        self._file_handler.setLevel(logging.DEBUG)
        self._file_handler.setFormatter(
            logging.Formatter('%(asctime)s [%(levelname)s] [%(task_id)s] %(message)s')
        )
        self.logger.addHandler(self._file_handler)
        
        # 创建JSON日志文件
        json_file = workflow_dir / f"{run_id}.json"
        self._json_file = open(json_file, 'w', encoding='utf-8')
        self._json_file.write('[\n')
        self._first_entry = True
        
        self.info(
            workflow_name,
            run_id,
            None,
            f"Workflow run started: {run_id}"
        )
    
    def end_run(self, workflow_name: str, run_id: str, status: TaskStatus):
        """结束运行，关闭日志文件"""
        try:
            self.info(
                workflow_name,
                run_id,
                None,
                f"Workflow run ended with status: {status.value}"
            )
        finally:
            self._close_handles()
        
        self._current_run_id = None
    
    def _close_handles(self):
        """关闭所有打开的文件句柄（内部方法）"""
        # 关闭文件处理器
        if self._file_handler:
            self.logger.removeHandler(self._file_handler)
            self._file_handler.close()
            self._file_handler = None
        
        # 关闭JSON文件
        if self._json_file:
            try:
                self._json_file.write('\n]')
            except Exception:
                pass
            try:
                self._json_file.close()
            except Exception:
                pass
            self._json_file = None
    
    def close(self):
        """显式关闭所有资源"""
        self._close_handles()
        self._current_run_id = None
    
    def __del__(self):
        """析构时确保文件句柄被关闭"""
        try:
            self._close_handles()
        except Exception:
            pass
    
    def _write_json_entry(self, entry: LogEntry):
        """写入JSON日志条目"""
        if self._json_file:
            if not self._first_entry:
                self._json_file.write(',\n')
            self._first_entry = False
            json.dump(entry.to_dict(), self._json_file, ensure_ascii=False, indent=2)
    
    def log(
        self,
        level: str,
        workflow_id: str,
        run_id: str,
        task_id: Optional[str],
        message: str,
        context: Dict[str, Any] = None,
        metrics: Dict[str, Any] = None
    ):
        """记录日志条目"""
        entry = LogEntry(
            timestamp=datetime.now(),
            workflow_id=workflow_id,
            run_id=run_id,
            task_id=task_id,
            level=level,
            message=message,
            context=context or {},
            metrics=metrics or {}
        )
        
        # 写入JSON
        self._write_json_entry(entry)
        
        # Python日志
        extra = {'task_id': task_id or 'WORKFLOW'}
        log_method = getattr(self.logger, level.lower(), self.logger.info)
        log_method(message, extra=extra)
    
    def debug(self, workflow_id: str, run_id: str, task_id: Optional[str], message: str, **kwargs):
        self.log("DEBUG", workflow_id, run_id, task_id, message, **kwargs)
    
    def info(self, workflow_id: str, run_id: str, task_id: Optional[str], message: str, **kwargs):
        self.log("INFO", workflow_id, run_id, task_id, message, **kwargs)
    
    def warn(self, workflow_id: str, run_id: str, task_id: Optional[str], message: str, **kwargs):
        self.log("WARN", workflow_id, run_id, task_id, message, **kwargs)
    
    def error(self, workflow_id: str, run_id: str, task_id: Optional[str], message: str, **kwargs):
        self.log("ERROR", workflow_id, run_id, task_id, message, **kwargs)
    
    def fatal(self, workflow_id: str, run_id: str, task_id: Optional[str], message: str, **kwargs):
        self.log("FATAL", workflow_id, run_id, task_id, message, **kwargs)
    
    def task_start(
        self,
        workflow_id: str,
        run_id: str,
        task_id: str,
        attempt: int = 1,
        max_attempts: int = 3,
        timeout: Optional[int] = None
    ):
        """记录任务开始"""
        self.info(
            workflow_id,
            run_id,
            task_id,
            f"Task started (attempt {attempt}/{max_attempts})",
            context={
                "attempt": attempt,
                "max_attempts": max_attempts,
                "timeout": timeout
            },
            metrics={
                "start_time": datetime.now().isoformat()
            }
        )
    
    def task_complete(
        self,
        workflow_id: str,
        run_id: str,
        task_id: str,
        duration: float,
        output_size: int = 0
    ):
        """记录任务完成"""
        self.info(
            workflow_id,
            run_id,
            task_id,
            f"Task completed in {duration:.2f}s",
            metrics={
                "duration": duration,
                "output_size": output_size,
                "end_time": datetime.now().isoformat()
            }
        )
    
    def task_failed(
        self,
        workflow_id: str,
        run_id: str,
        task_id: str,
        error: str,
        attempt: int,
        will_retry: bool
    ):
        """记录任务失败"""
        message = f"Task failed: {error}"
        if will_retry:
            message += f" (will retry, attempt {attempt})"
        else:
            message += " (no more retries)"
        
        self.error(
            workflow_id,
            run_id,
            task_id,
            message,
            context={
                "error": error,
                "attempt": attempt,
                "will_retry": will_retry
            }
        )
    
    def save_checkpoint(
        self,
        workflow_name: str,
        run_id: str,
        task_id: str,
        status: TaskStatus,
        result: Any,
        context: Dict[str, Any] = None
    ):
        """保存检查点"""
        checkpoint = Checkpoint(
            run_id=run_id,
            task_id=task_id,
            status=status,
            result=result,
            timestamp=datetime.now(),
            context=context or {}
        )
        
        # 保存到文件
        checkpoint_dir = self.log_dir / "workflows" / workflow_name / "checkpoints"
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        
        checkpoint_file = checkpoint_dir / f"checkpoint-{task_id}.json"
        with open(checkpoint_file, 'w', encoding='utf-8') as f:
            json.dump(checkpoint.to_dict(), f, ensure_ascii=False, indent=2)
        
        self.debug(
            workflow_name,
            run_id,
            task_id,
            f"Checkpoint saved: {checkpoint_file}"
        )
    
    def load_checkpoint(
        self,
        workflow_name: str,
        run_id: str,
        task_id: str
    ) -> Optional[Checkpoint]:
        """加载检查点"""
        checkpoint_file = self.log_dir / "workflows" / workflow_name / "checkpoints" / f"checkpoint-{task_id}.json"
        
        if not checkpoint_file.exists():
            return None
        
        try:
            with open(checkpoint_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            return Checkpoint(
                run_id=data['run_id'],
                task_id=data['task_id'],
                status=TaskStatus(data['status']),
                result=data['result'],
                timestamp=datetime.fromisoformat(data['timestamp']),
                context=data.get('context', {})
            )
        except Exception as e:
            self.warn(
                workflow_name,
                run_id,
                task_id,
                f"Failed to load checkpoint: {e}"
            )
            return None
    
    def get_run_history(
        self,
        workflow_name: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """获取运行历史"""
        workflow_dir = self.log_dir / "workflows" / workflow_name
        
        if not workflow_dir.exists():
            return []
        
        # 查找所有JSON日志文件
        json_files = sorted(
            workflow_dir.glob("run-*.json"),
            key=lambda f: f.stat().st_mtime,
            reverse=True
        )[:limit]
        
        history = []
        for json_file in json_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # 处理未完成的JSON文件
                    if not content.endswith(']'):
                        content += ']'
                    entries = json.loads(content)
                
                if entries:
                    first = entries[0]
                    last = entries[-1]
                    
                    # 提取状态
                    status = "unknown"
                    for entry in reversed(entries):
                        if "ended with status" in entry.get("message", ""):
                            status = entry["message"].split(": ")[-1]
                            break
                    
                    history.append({
                        "run_id": first.get("run_id"),
                        "workflow_name": workflow_name,
                        "start_time": first.get("timestamp"),
                        "end_time": last.get("timestamp"),
                        "status": status,
                        "log_file": str(json_file)
                    })
            except Exception as e:
                continue
        
        return history
    
    def get_run_detail(
        self,
        workflow_name: str,
        run_id: str
    ) -> Dict[str, Any]:
        """获取运行详情"""
        json_file = self.log_dir / "workflows" / workflow_name / f"{run_id}.json"
        
        if not json_file.exists():
            return {"error": f"Run not found: {run_id}"}
        
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                content = f.read()
                if not content.endswith(']'):
                    content += ']'
                entries = json.loads(content)
            
            # 按任务分组
            tasks = {}
            for entry in entries:
                task_id = entry.get("task_id")
                if task_id and task_id != "WORKFLOW":
                    if task_id not in tasks:
                        tasks[task_id] = {
                            "task_id": task_id,
                            "status": "unknown",
                            "start_time": None,
                            "end_time": None,
                            "duration": None,
                            "attempts": 0,
                            "error": None
                        }
                    
                    task = tasks[task_id]
                    
                    if "started" in entry.get("message", "").lower():
                        task["start_time"] = entry.get("timestamp")
                        attempt = entry.get("context", {}).get("attempt", 1)
                        task["attempts"] = max(task["attempts"], attempt)
                    
                    if "completed" in entry.get("message", "").lower():
                        task["status"] = "completed"
                        task["end_time"] = entry.get("timestamp")
                        task["duration"] = entry.get("metrics", {}).get("duration")
                    
                    if "failed" in entry.get("message", "").lower():
                        if "no more retries" in entry.get("message", ""):
                            task["status"] = "failed"
                        task["error"] = entry.get("context", {}).get("error")
            
            return {
                "run_id": run_id,
                "workflow_name": workflow_name,
                "tasks": list(tasks.values()),
                "total_entries": len(entries)
            }
        except Exception as e:
            return {"error": str(e)}


# 全局日志实例
_logger: Optional[TaskLogger] = None


def get_logger(log_dir: str = ".task-logs") -> TaskLogger:
    """获取日志实例（单例）"""
    global _logger
    if _logger is None:
        _logger = TaskLogger(log_dir)
    return _logger


def reset_logger():
    """重置全局日志实例（用于测试或重新初始化）"""
    global _logger
    if _logger is not None:
        _logger.close()
        _logger = None
