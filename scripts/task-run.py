#!/usr/bin/env python3
"""
task-run - 执行工作流的命令行工具
"""

import argparse
import asyncio
import sys
import os

# 添加核心模块路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.engine import run_workflow_from_file


def main():
    parser = argparse.ArgumentParser(
        description="Execute a task workflow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  task-run workflow.yaml
  task-run workflow.yaml --dry-run
  task-run workflow.yaml --vars API_KEY=xxx ENV=prod
  task-run workflow.yaml --resume-from process-data
  task-run workflow.yaml --parallel 10 --timeout 7200
        """
    )
    
    parser.add_argument(
        "config",
        help="Workflow configuration file (YAML or JSON)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration without executing"
    )
    parser.add_argument(
        "--vars",
        nargs="*",
        metavar="KEY=VALUE",
        help="Override workflow variables"
    )
    parser.add_argument(
        "--resume-from",
        metavar="TASK_ID",
        help="Resume execution from a specific task"
    )
    parser.add_argument(
        "--parallel",
        type=int,
        metavar="N",
        help="Maximum parallel tasks"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        metavar="SECONDS",
        help="Global timeout in seconds"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )
    parser.add_argument(
        "--log-dir",
        metavar="DIR",
        default=".task-logs",
        help="Directory for log output (default: .task-logs)"
    )
    
    args = parser.parse_args()
    
    # 检查配置文件
    if not os.path.exists(args.config):
        print(f"Error: Configuration file not found: {args.config}")
        sys.exit(1)
    
    # 解析变量
    variables = {}
    if args.vars:
        for var in args.vars:
            if "=" in var:
                key, value = var.split("=", 1)
                variables[key] = value
            else:
                print(f"Warning: Invalid variable format: {var}")
    
    # 执行
    try:
        result = asyncio.run(run_workflow_from_file(
            args.config,
            variables=variables,
            resume_from=args.resume_from,
            dry_run=args.dry_run,
            max_parallel=args.parallel,
            timeout=args.timeout,
            log_dir=args.log_dir,
        ))
        
        if result:
            print(f"\n{'='*50}")
            print(f"Run ID: {result.run_id}")
            print(f"Status: {result.status.value}")
            if result.duration:
                print(f"Duration: {result.duration:.2f}s")
            if result.error:
                print(f"Error: {result.error}")
            print(f"{'='*50}")
            
            # 退出码
            sys.exit(0 if result.success else 1)
        
    except KeyboardInterrupt:
        print("\nExecution cancelled")
        sys.exit(130)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
