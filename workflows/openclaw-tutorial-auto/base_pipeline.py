#!/usr/bin/env python3
"""
base_pipeline.py — 流水线基类
================================
提取 Pipeline / CodePipeline 的共享逻辑:
  - run() 循环: banner → stages → error handling → final report
  - _generate_final_report(): JSON 结果生成
  - _print_banner(): 统一 banner 输出

子类只需:
  1. 定义 STAGES / CRITICAL_STAGES / PIPELINE_NAME / PIPELINE_VERSION
  2. 实现 _stage_xxx() 处理器
  3. 覆写 output_dir 属性（如需要）
"""

from datetime import datetime, timezone
import os
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from modules.compat import setup_logger, save_json
from plugin_loader import get_plugin_manager


class BasePipeline:
    """流水线基类 — 封装 run loop / banner / error handling / final report。"""

    # ── 子类必须覆写 ──
    STAGES: list = []
    CRITICAL_STAGES: tuple = ("scan",)
    PIPELINE_NAME: str = "流水线"
    PIPELINE_VERSION: str = "1.0"
    PIPELINE_ICON: str = "⚙️"
    PARALLEL_GROUPS: list = []  # 可并行阶段组: [("stage_a", "stage_b", ...), ...]

    def __init__(self, *, dry_run: bool = False, stages: list = None,
                 plugins: bool = True, **kwargs):
        self.dry_run = dry_run
        self.stages = stages or list(self.STAGES)
        self.results: dict = {}
        self.start_time: float | None = None
        self.plugins_enabled = plugins

        if dry_run:
            os.environ["DRY_RUN"] = "true"

        # 初始化插件系统
        self._pm = get_plugin_manager() if plugins else None
        if self._pm:
            self._pm.load_all()

    # ── 子类需覆写的属性 ──

    @property
    def output_dir(self) -> str:
        """报告输出目录，子类应覆写。"""
        raise NotImplementedError

    @property
    def project_dir(self) -> str:
        """项目目录，子类应覆写。"""
        raise NotImplementedError

    @property
    def report_filename(self) -> str:
        """最终 JSON 报告文件名。"""
        return "pipeline-result.json"

    # ── 核心运行循环 ──

    def run(self) -> dict:
        """执行流水线 — 统一调度所有阶段，支持并行阶段组。"""
        self.start_time = time.time()
        os.makedirs(self.output_dir, exist_ok=True)

        self._print_banner()
        self._trigger("on_pipeline_start", {"pipeline": self.PIPELINE_NAME, "stages": self.stages})

        # 预计算并行组映射: stage_name → group tuple
        _parallel_map: dict[str, tuple] = {}
        for group in getattr(self, "PARALLEL_GROUPS", []):
            for s in group:
                _parallel_map[s] = group

        executed: set = set()  # 已执行阶段（含并行组内的）
        abort = False

        for stage in self.stages:
            if stage in executed:
                continue
            if abort:
                break

            group = _parallel_map.get(stage)
            # 过滤: 只并行执行当前 stages 列表中实际存在的组成员
            group_stages = [s for s in group if s in self.stages] if group else None

            if group_stages and len(group_stages) > 1:
                # ── 并行执行一组阶段 ──
                abort = self._run_parallel_group(group_stages, executed)
            else:
                # ── 串行执行单个阶段 ──
                abort = self._run_single_stage(stage, executed)

            self._log.info("")

        report = self._generate_final_report()
        self._trigger("on_pipeline_end", report)
        return report

    def _run_single_stage(self, stage: str, executed: set) -> bool:
        """执行单个阶段，返回 True 表示需要中断流水线。"""
        handler = getattr(self, f"_stage_{stage}", None)
        if not handler:
            self._log.warning(f"未知阶段: {stage}，跳过")
            executed.add(stage)
            return False

        self._log.info(f"{'='*50}")
        self._log.info(f"  Stage: {stage.upper()}")
        self._log.info(f"{'='*50}")

        try:
            self._trigger(f"before_{stage}", {"stage": stage})
            result = handler()
            result = self._trigger(f"after_{stage}", result)
            self.results[stage] = {
                "status": "ok",
                "data": result,
                "duration": time.time() - self.start_time,
            }
            self._log.info(f"  ✅ {stage} 完成")
        except Exception as e:
            self._log.error(f"  ❌ {stage} 失败: {e}")
            traceback.print_exc()
            self._trigger("on_error", {"stage": stage, "error": str(e)})
            self.results[stage] = {
                "status": "error",
                "error": str(e),
                "duration": time.time() - self.start_time,
            }
            if stage in self.CRITICAL_STAGES:
                self._log.error("  关键阶段失败，中断流水线")
                executed.add(stage)
                return True

        executed.add(stage)
        return False

    def _run_parallel_group(self, stages: list, executed: set) -> bool:
        """并行执行一组阶段（ThreadPool），返回 True 表示需要中断。"""
        self._log.info(f"{'='*50}")
        self._log.info(f"  ⚡ 并行执行: {' | '.join(s.upper() for s in stages)}")
        self._log.info(f"{'='*50}")

        abort = False
        futures = {}

        def _run_stage(stage_name: str):
            handler = getattr(self, f"_stage_{stage_name}", None)
            if not handler:
                return stage_name, None, None
            self._trigger(f"before_{stage_name}", {"stage": stage_name})
            result = handler()
            result = self._trigger(f"after_{stage_name}", result)
            return stage_name, result, None

        with ThreadPoolExecutor(max_workers=len(stages)) as pool:
            for s in stages:
                futures[pool.submit(_run_stage, s)] = s

            for future in as_completed(futures):
                stage_name = futures[future]
                try:
                    name, result, _ = future.result()
                    self.results[name] = {
                        "status": "ok",
                        "data": result,
                        "duration": time.time() - self.start_time,
                    }
                    self._log.info(f"  ✅ {name} 完成")
                except Exception as e:
                    self._log.error(f"  ❌ {stage_name} 失败: {e}")
                    traceback.print_exc()
                    self._trigger("on_error", {"stage": stage_name, "error": str(e)})
                    self.results[stage_name] = {
                        "status": "error",
                        "error": str(e),
                        "duration": time.time() - self.start_time,
                    }
                    if stage_name in self.CRITICAL_STAGES:
                        self._log.error("  关键阶段失败，中断流水线")
                        abort = True
                executed.add(stage_name)

        return abort

        report = self._generate_final_report()
        self._trigger("on_pipeline_end", report)
        return report

    # ── Banner ──

    def _print_banner(self):
        """输出流水线启动信息。"""
        title = f"{self.PIPELINE_ICON}  {self.PIPELINE_NAME} v{self.PIPELINE_VERSION}"
        self._log.info("╔════════════════════════════════════════════════╗")
        self._log.info(f"║  {title:<45}║")
        self._log.info("╚════════════════════════════════════════════════╝")
        self._log.info(f"项目: {self.project_dir}")
        self._log.info(f"输出: {self.output_dir}")
        self._log.info(f"阶段: {' → '.join(self.stages)}")
        self._log.info(f"模式: {'DRY_RUN' if self.dry_run else 'LIVE'}")
        self._log.info("")

    # ── Final Report ──

    def _generate_final_report(self) -> dict:
        """生成最终的 JSON 结果。"""
        duration = time.time() - self.start_time if self.start_time else 0
        report = {
            "pipeline_version": self.PIPELINE_VERSION,
            "mode": self.PIPELINE_NAME,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "project_dir": self.project_dir,
            "duration_seconds": round(duration, 1),
            "dry_run": self.dry_run,
            "stages_executed": list(self.results.keys()),
            "stages_ok": sum(1 for r in self.results.values()
                             if r["status"] == "ok"),
            "stages_failed": sum(1 for r in self.results.values()
                                 if r["status"] == "error"),
            "results": {
                k: {"status": v["status"], "duration": v.get("duration", 0)}
                for k, v in self.results.items()
            },
        }

        save_json(os.path.join(self.output_dir, self.report_filename), report)
        self._log.info(
            f"流水线完成: {report['stages_ok']}/{len(self.results)} 阶段成功, "
            f"耗时 {duration:.1f}s"
        )
        return report

    # ── 便捷属性 ──

    def _trigger(self, hook_name: str, data: Any = None) -> Any:
        """触发插件钩子（安全包装）。"""
        if self._pm:
            return self._pm.trigger(hook_name, data)
        return data

    @property
    def _log(self):
        """子类 logger — 延迟获取，避免基类实例化时创建。"""
        if not hasattr(self, "_logger"):
            self._logger = setup_logger(self.__class__.__name__.lower())
        return self._logger
