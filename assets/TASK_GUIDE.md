# Complex Task Automator - 使用指南

## 快速开始

### 1. 安装依赖

```bash
# 安装 Python 依赖
pip install pyyaml httpx

# 可选：安装调度依赖
pip install croniter watchdog
```

### 2. 运行示例

```bash
# 进入 Skill 目录
cd ~/.openclaw/workspace/skills/complex-task-automator

# 运行简单示例
python scripts/task-run.py examples/simple-workflow.yaml

# 干运行（仅验证配置）
python scripts/task-run.py examples/simple-workflow.yaml --dry-run

# 运行并行处理示例
python scripts/task-run.py examples/parallel-processing.yaml

# 运行重试机制示例
python scripts/task-run.py examples/retry-demo.yaml
```

---

## 创建自己的工作流

### 步骤 1：复制模板

```bash
cp templates/basic.yaml my-workflow.yaml
```

### 步骤 2：编辑配置

```yaml
name: my-workflow
version: "1.0"
description: "我的工作流"

tasks:
  - id: step-1
    name: "第一步"
    type: shell
    config:
      command: "echo 'Hello'"
      
  - id: step-2
    name: "第二步"
    type: shell
    config:
      command: "echo 'World'"
    depends_on:
      - step-1
```

### 步骤 3：运行

```bash
python scripts/task-run.py my-workflow.yaml
```

---

## 任务类型详解

### Shell 任务

执行 Shell 命令：

```yaml
- id: shell-task
  type: shell
  config:
    command: |
      echo "Multi-line command"
      ls -la
      pwd
    env:
      MY_VAR: "value"
```

### Python 任务

执行 Python 脚本：

```yaml
- id: python-task
  type: python
  config:
    script: "scripts/my_script.py"
    args:
      - "--input"
      - "/data/input.json"
      - "--output"
      - "/data/output.json"
```

### HTTP 任务

发送 HTTP 请求：

```yaml
- id: http-task
  type: http
  config:
    method: POST
    url: "https://api.example.com/data"
    headers:
      Authorization: "Bearer ${API_TOKEN}"
      Content-Type: "application/json"
    body:
      key: "value"
    output: "/tmp/response.json"  # 可选：保存响应
```

### Webhook 任务

发送 Webhook 通知：

```yaml
- id: webhook-task
  type: webhook
  config:
    url: "https://hooks.slack.com/services/xxx"
    body:
      text: "Task completed!"
```

---

## 依赖关系

### 顺序执行

```yaml
tasks:
  - id: A
  - id: B
    depends_on: [A]
  - id: C
    depends_on: [B]
```

执行顺序：A → B → C

### 并行执行

```yaml
tasks:
  - id: init
  - id: task-a
    depends_on: [init]
  - id: task-b
    depends_on: [init]
  - id: task-c
    depends_on: [init]
  - id: merge
    depends_on: [task-a, task-b, task-c]
```

执行流程：
- init 先执行
- task-a, task-b, task-c 并行执行
- merge 等待所有并行任务完成后执行

---

## 失败处理

### 重试配置

```yaml
- id: unstable-task
  retry:
    max_attempts: 5        # 最多重试5次
    backoff: exponential   # 指数退避
    initial_delay: 5       # 初始延迟5秒
    max_delay: 300         # 最大延迟300秒
```

退避策略：
- `fixed`：固定延迟
- `linear`：线性增长（delay × attempt）
- `exponential`：指数增长（delay × 2^(attempt-1)）
- `random`：随机延迟

### 失败处理策略

```yaml
- id: task-1
  on_failure: abort        # 终止整个工作流

- id: task-2
  on_failure: continue     # 继续执行后续任务

- id: task-3
  on_failure: skip_downstream  # 跳过依赖此任务的下游任务
```

---

## 变量使用

### 定义变量

```yaml
variables:
  data_dir: "/data/input"
  api_url: "https://api.example.com"
  batch_size: 100
```

### 使用变量

```yaml
tasks:
  - id: fetch
    type: http
    config:
      url: "${api_url}/data?size=${batch_size}"
```

### 命令行覆盖

```bash
python scripts/task-run.py workflow.yaml --vars data_dir=/custom/path batch_size=500
```

### 引用任务结果

```yaml
- id: notify
  type: webhook
  config:
    body:
      stats: "{{ result.process-data.output }}"
```

---

## 查看执行日志

日志存储在 `.task-logs/` 目录：

```
.task-logs/
├── workflows/
│   └── my-workflow/
│       ├── run-20260306-100000.log    # 文本日志
│       ├── run-20260306-100000.json   # JSON日志
│       └── checkpoints/               # 检查点
├── tasks/
└── summary/
```

### 查看执行历史

```python
from scripts.core import get_logger

logger = get_logger()
history = logger.get_run_history("my-workflow", limit=10)
for run in history:
    print(f"{run['run_id']}: {run['status']}")
```

### 查看运行详情

```python
details = logger.get_run_detail("my-workflow", "run-20260306-100000")
for task in details['tasks']:
    print(f"{task['task_id']}: {task['status']} ({task['duration']}s)")
```

---

## 断点恢复

如果工作流执行失败，可以从失败点继续：

```bash
# 从特定任务开始恢复
python scripts/task-run.py workflow.yaml --resume-from task-id

# 查看上次执行的状态，确定从哪里恢复
python scripts/task-run.py workflow.yaml --dry-run
```

---

## 调度任务

### 添加定时任务

```python
from scripts.core import get_scheduler, ScheduleConfig

scheduler = get_scheduler()

# Cron 调度（每天凌晨2点）
scheduler.add_job(
    job_id="daily-job",
    workflow_path="workflows/daily.yaml",
    schedule=ScheduleConfig(type="cron", cron="0 2 * * *")
)

# 间隔调度（每小时）
scheduler.add_job(
    job_id="hourly-job",
    workflow_path="workflows/hourly.yaml",
    schedule=ScheduleConfig(type="interval", interval=3600)
)
```

### 管理调度任务

```python
# 列出所有任务
for job in scheduler.list_jobs():
    print(f"{job.job_id}: {job.enabled} - Next: {job.next_run}")

# 启用/禁用
scheduler.enable_job("daily-job")
scheduler.disable_job("hourly-job")

# 移除任务
scheduler.remove_job("daily-job")
```

---

## 最佳实践

### 1. 任务设计原则

- **原子性**：每个任务应该是独立的，可重试的
- **幂等性**：多次执行应产生相同结果
- **超时设置**：始终为任务设置合理的超时时间

### 2. 依赖管理

- 合理划分任务粒度
- 利用并行执行提高效率
- 避免创建不必要的依赖

### 3. 错误处理

- 为关键任务配置充足的重试次数
- 合理设置退避策略避免压垮下游服务
- 对非关键任务使用 `on_failure: continue`

### 4. 日志与监控

- 在任务中输出关键信息便于调试
- 利用 Webhook 发送执行状态通知
- 定期检查执行历史发现潜在问题

---

## 常见问题

### Q: 如何处理大量并行任务？

A: 使用 `max_parallel` 限制并发数：

```yaml
config:
  execution:
    max_parallel: 10  # 最多同时执行10个任务
```

### Q: 如何传递任务输出给下游任务？

A: 使用文件或变量引用：

```yaml
# 方式1：通过文件
- id: task-a
  config:
    command: "echo 'result' > /tmp/output.txt"
    
- id: task-b
  config:
    command: "cat /tmp/output.txt"
  depends_on: [task-a]

# 方式2：通过结果引用
- id: task-b
  config:
    body:
      data: "{{ result.task-a.output }}"
```

### Q: 如何调试失败的任务？

A: 查看详细日志：

```bash
# 查看日志文件
cat .task-logs/workflows/my-workflow/run-xxx.log

# 查看 JSON 日志获取结构化信息
cat .task-logs/workflows/my-workflow/run-xxx.json | jq '.[] | select(.level == "ERROR")'
```

---

## 更多资源

- [SKILL.md](../SKILL.md) - 完整功能文档
- [templates/](../templates/) - 配置模板
- [examples/](../examples/) - 更多示例
