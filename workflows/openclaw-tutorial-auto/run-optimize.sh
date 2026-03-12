#!/bin/bash
# =========================================================
#  run-optimize.sh — 教程自动优化 Cron 入口脚本
# =========================================================
#  供 openclaw cron 定时调用的统一入口
#  调用 auto_optimizer.py v5.2 统一流水线 (14 阶段)
#
#  用法:
#    ./run-optimize.sh                        # 默认: 教程模式
#    ./run-optimize.sh --mode tutorial        # 教程优化
#    ./run-optimize.sh --mode code /path      # 代码优化
#    ./run-optimize.sh --mode both            # 双模式
#    ./run-optimize.sh --dry-run              # 干跑模式
#    ./run-optimize.sh --no-web-search        # 禁用 Web 搜索
#    ./run-optimize.sh --max-chapters 5       # 限制章节数
#    ./run-optimize.sh --incremental           # 增量模式 (mtime+size 缓存)
# =========================================================

set -euo pipefail

# ── 路径和变量 ──
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="/tmp/openclaw-tutorial-auto-reports/logs"
LOCK_FILE="/tmp/openclaw-tutorial-auto.lock"
LOG_FILE="${LOG_DIR}/optimize-$(date '+%Y-%m-%d_%H%M%S').log"

# 默认参数
MODE="tutorial"
MAX_CHAPTERS=""
DRY_RUN=""
EXTRA_ARGS=""

# ── 参数解析 ──
while [[ $# -gt 0 ]]; do
    case $1 in
        --mode)           MODE="$2"; shift 2 ;;
        --max-chapters)   MAX_CHAPTERS="$2"; shift 2 ;;
        --dry-run)        DRY_RUN="--dry-run"; shift ;;
        --no-web-search)  EXTRA_ARGS="${EXTRA_ARGS} --no-web-search"; shift ;;
        --incremental)    EXTRA_ARGS="${EXTRA_ARGS} --incremental"; shift ;;
        --stage)          EXTRA_ARGS="${EXTRA_ARGS} --stage $2"; shift 2 ;;
        --help|-h)
            echo "用法: $0 [--mode tutorial|code|both|auto] [--max-chapters N] [--dry-run] [--no-web-search] [--stage NAME]"
            exit 0
            ;;
        *)                EXTRA_ARGS="${EXTRA_ARGS} $1"; shift ;;
    esac
done

# ── 准备日志目录 ──
mkdir -p "${LOG_DIR}"

# ── 防重入锁 ──
if [[ -f "${LOCK_FILE}" ]]; then
    LOCK_PID=$(cat "${LOCK_FILE}" 2>/dev/null || echo "")
    if [[ -n "${LOCK_PID}" ]] && kill -0 "${LOCK_PID}" 2>/dev/null; then
        echo "⚠️  另一个优化进程正在运行 (PID: ${LOCK_PID})，跳过本次执行"
        exit 0
    else
        echo "🔓 发现过期锁文件，清理"
        rm -f "${LOCK_FILE}"
    fi
fi
echo $$ > "${LOCK_FILE}"
trap 'rm -f "${LOCK_FILE}"' EXIT

# ── 环境变量 ──
export PROJECT_DIR="${PROJECT_DIR:-/root/.openclaw/workspace/zxk-private/openclaw-tutorial-auto}"
export OUTPUT_DIR="${OUTPUT_DIR:-/tmp/openclaw-tutorial-auto-reports}"
export LOG_LEVEL="${LOG_LEVEL:-INFO}"

# ── 构建命令参数 ──
CMD_ARGS="--mode ${MODE}"
if [[ -n "${MAX_CHAPTERS}" ]]; then
    CMD_ARGS="${CMD_ARGS} --max-chapters ${MAX_CHAPTERS}"
fi
CMD_ARGS="${CMD_ARGS} --output-dir ${OUTPUT_DIR}"
CMD_ARGS="${CMD_ARGS} ${DRY_RUN} ${EXTRA_ARGS}"

# ── 执行 ──
echo "╔════════════════════════════════════════════════════╗"
echo "║  🚀 OpenClaw 教程自动优化 v5.2 (14 阶段)          ║"
echo "╚════════════════════════════════════════════════════╝"
echo ""
echo "⏰ 时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "📋 模式: ${MODE}"
echo "📁 项目: ${PROJECT_DIR}"
echo "📝 日志: ${LOG_FILE}"
echo ""

cd "${SCRIPT_DIR}"

# 调用 auto_optimizer.py (v5.2 统一入口)
python3 auto_optimizer.py ${CMD_ARGS} 2>&1 | tee "${LOG_FILE}"

EXIT_CODE=${PIPESTATUS[0]}

# ── 飞书通知（仅正式运行 + 有实际更新时） ──
if [[ -z "${DRY_RUN}" ]]; then
    if [[ -f "${OUTPUT_DIR}/pipeline-result.json" ]]; then
        STAGES_OK=$(python3 -c "
import json
try:
    data = json.load(open('${OUTPUT_DIR}/pipeline-result.json'))
    print(data.get('stages_ok', 0))
except: print(0)
" 2>/dev/null || echo "0")
        if [[ "${STAGES_OK}" -gt 0 ]]; then
            echo ""
            echo "📨 触发飞书通知..."
            python3 -m modules.notifier \
                --title "教程优化完成" \
                --body "模式: ${MODE}, 成功阶段: ${STAGES_OK}" \
                --level success 2>&1 || echo "⚠️ 飞书通知发送失败（不影响主流程）"
        fi
    fi
fi

# ── 日志清理（保留最近 50 个） ──
ls -t "${LOG_DIR}"/optimize-*.log 2>/dev/null | tail -n +51 | xargs rm -f 2>/dev/null || true

echo ""
echo "✅ 执行完成 (exit: ${EXIT_CODE})"
exit ${EXIT_CODE}
