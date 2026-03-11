#!/bin/bash
# =========================================================
#  run-optimize.sh — 教程持续优化入口脚本
# =========================================================
#  供 openclaw cron 定时调用的统一入口
#
#  用法:
#    ./run-optimize.sh                # 默认 continuous 模式
#    ./run-optimize.sh --mode optimize # 仅搜索+优化
#    ./run-optimize.sh --dry-run      # 空运行
#    ./run-optimize.sh --status       # 查看状态
# =========================================================

set -euo pipefail

# ── 路径和变量 ──
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS_DIR="${SCRIPT_DIR}/scripts"
LOG_DIR="/tmp/openclaw-tutorial-auto-reports/logs"
LOCK_FILE="/tmp/openclaw-tutorial-auto.lock"
LOG_FILE="${LOG_DIR}/optimize-$(date '+%Y-%m-%d_%H%M%S').log"

# 默认参数
MODE="continuous"
MAX_CHAPTERS=3
DRY_RUN=""
EXTRA_ARGS=""

# ── 参数解析 ──
while [[ $# -gt 0 ]]; do
    case $1 in
        --mode)     MODE="$2"; shift 2 ;;
        --max-chapters) MAX_CHAPTERS="$2"; shift 2 ;;
        --dry-run)  DRY_RUN="--dry-run"; shift ;;
        --status)   MODE="status"; shift ;;
        --help|-h)
            echo "用法: $0 [--mode continuous|optimize|health|status] [--max-chapters N] [--dry-run]"
            exit 0
            ;;
        *)          EXTRA_ARGS="${EXTRA_ARGS} $1"; shift ;;
    esac
done

# ── 准备日志目录 ──
mkdir -p "${LOG_DIR}"

# ── 防重入锁 ──
if [[ "${MODE}" != "status" ]]; then
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
fi

# ── 环境变量 ──
export PROJECT_DIR="${PROJECT_DIR:-/root/.openclaw/workspace/zxk-private/openclaw-tutorial-auto}"
export OUTPUT_DIR="${OUTPUT_DIR:-/tmp/openclaw-tutorial-auto-reports}"
export SCRIPTS_DIR="${SCRIPTS_DIR}"
export LOG_LEVEL="${LOG_LEVEL:-INFO}"

# ── 执行 ──
echo "╔════════════════════════════════════════════════════╗"
echo "║  🚀 OpenClaw 教程持续优化                         ║"
echo "╚════════════════════════════════════════════════════╝"
echo ""
echo "⏰ 时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "📋 模式: ${MODE}"
echo "📁 项目: ${PROJECT_DIR}"
echo "📝 日志: ${LOG_FILE}"
echo ""

cd "${SCRIPTS_DIR}"

# 分两路输出: 终端 + 日志文件
python3 daemon.py \
    --mode "${MODE}" \
    --max-chapters "${MAX_CHAPTERS}" \
    ${DRY_RUN} \
    ${EXTRA_ARGS} \
    2>&1 | tee "${LOG_FILE}"

EXIT_CODE=${PIPESTATUS[0]}

# ── 飞书通知（仅 continuous/optimize 模式 + 有实际更新时） ──
if [[ "${MODE}" =~ ^(continuous|optimize)$ ]] && [[ -z "${DRY_RUN}" ]]; then
    if [[ -f "${OUTPUT_DIR}/optimize-result.json" ]]; then
        OPTIMIZED=$(python3 -c "
import json
try:
    data = json.load(open('${OUTPUT_DIR}/optimize-result.json'))
    print(data.get('optimized', 0))
except: print(0)
" 2>/dev/null || echo "0")
        if [[ "${OPTIMIZED}" -gt 0 ]]; then
            echo ""
            echo "📨 触发飞书通知..."
            python3 feishu_notify.py 2>&1 || echo "⚠️ 飞书通知发送失败（不影响主流程）"
        else
            echo ""
            echo "ℹ️  本轮无优化更新，跳过飞书通知"
        fi
    fi
fi

# ── 日志清理（保留最近 50 个） ──
ls -t "${LOG_DIR}"/optimize-*.log 2>/dev/null | tail -n +51 | xargs rm -f 2>/dev/null || true

echo ""
echo "✅ 执行完成 (exit: ${EXIT_CODE})"
exit ${EXIT_CODE}
