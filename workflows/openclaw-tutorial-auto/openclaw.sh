#!/bin/bash
# =========================================================
#  openclaw.sh — OpenClaw v5.2 统一工作流入口脚本
# =========================================================
#  支持所有工作流模式，提供统一的命令行接口。
#
#  用法:
#    ./openclaw.sh <command> [options]
#
#  命令:
#    tutorial           教程优化流水线 (14 阶段)
#    code <dir>         代码优化流水线 (5 阶段)
#    both               教程+代码双流水线
#    auto               自动检测模式
#    status             查看项目状态
#    help               显示帮助
#
#  示例:
#    ./openclaw.sh tutorial --dry-run
#    ./openclaw.sh tutorial --no-web-search
#    ./openclaw.sh code /path/to/project
#    ./openclaw.sh code /path/to/project --ext .py .go --max-files 20
#    ./openclaw.sh both --dry-run
#    ./openclaw.sh auto
#    ./openclaw.sh status
# =========================================================

set -euo pipefail

# ── 路径 ──
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="/tmp/openclaw-reports/logs"
LOCK_FILE="/tmp/openclaw.lock"

# ── 颜色 ──
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# ── 环境变量 ──
export PROJECT_DIR="${PROJECT_DIR:-/root/.openclaw/workspace/zxk-private/openclaw-tutorial-auto}"
export LOG_LEVEL="${LOG_LEVEL:-INFO}"

# ── 帮助 ──
show_help() {
    echo -e "${CYAN}╔════════════════════════════════════════════════════════╗"
    echo -e "║  🚀 OpenClaw v5.2 — 统一自动优化工作流                ║"
    echo -e "╚════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${GREEN}命令:${NC}"
    echo "  tutorial                  教程优化流水线 (discover→scan→...→fix_issues→...→report, 14阶段)"
    echo "  code <dir>                代码优化流水线 (scan→analyze→enrich→refine→report, 5阶段)"
    echo "  both                      依次运行教程+代码双流水线"
    echo "  auto                      自动检测项目类型并选择流水线"
    echo "  status                    查看进度与状态"
    echo ""
    echo -e "${GREEN}通用选项:${NC}"
    echo "  --dry-run                 干跑模式，不做实际修改"
    echo "  --stage <name>            仅运行到指定阶段"
    echo "  --output-dir <dir>        自定义输出目录"
    echo "  --no-web-search           禁用 Web 搜索增强"
    echo ""
    echo -e "${GREEN}教程选项 (tutorial/both):${NC}"
    echo "  --max-chapters <N>        最大优化章节数 (默认: 全部)"
    echo "  --check-external          检查外部链接"
    echo ""
    echo -e "${GREEN}代码选项 (code/both):${NC}"
    echo "  --max-files <N>           最大优化文件数 (默认: 50)"
    echo "  --ext .py .js .go ...     仅扫描指定扩展名"
    echo ""
    echo -e "${GREEN}示例:${NC}"
    echo "  ./openclaw.sh tutorial --dry-run                    # 教程流水线干跑"
    echo "  ./openclaw.sh tutorial --no-web-search              # 禁用 Web 搜索"
    echo "  ./openclaw.sh code /opt/myproject                   # 代码分析"
    echo "  ./openclaw.sh code /opt/myproject --ext .py .go     # 仅 Python+Go"
    echo "  ./openclaw.sh both --dry-run                        # 双流水线干跑"
    echo "  ./openclaw.sh auto                                  # 自动检测"
    echo ""
    echo -e "${YELLOW}支持的语言族 (代码模式):${NC}"
    echo "  Python (.py) | JavaScript (.js) | TypeScript (.ts)"
    echo "  Go (.go) | Shell (.sh) | Rust (.rs)"
    echo "  C (.c, .h) | C++ (.cpp, .hpp) | Java (.java)"
    echo ""
    echo -e "${YELLOW}工作流 YAML 配置:${NC}"
    echo "  workflow-pipeline.yaml     统一流水线 v5.2 ⭐ (推荐, 教程14+代码5阶段)"
}

# ── 防重入锁 ──
acquire_lock() {
    if [[ -f "${LOCK_FILE}" ]]; then
        local lock_pid
        lock_pid=$(cat "${LOCK_FILE}" 2>/dev/null || echo "")
        if [[ -n "${lock_pid}" ]] && kill -0 "${lock_pid}" 2>/dev/null; then
            echo -e "${YELLOW}⚠️  另一个进程正在运行 (PID: ${lock_pid})，跳过${NC}"
            exit 0
        else
            echo -e "${YELLOW}🔓 清理过期锁文件${NC}"
            rm -f "${LOCK_FILE}"
        fi
    fi
    echo $$ > "${LOCK_FILE}"
    trap 'rm -f "${LOCK_FILE}"' EXIT
}

# ── 日志头 ──
print_header() {
    local mode="$1"
    echo -e "${CYAN}╔════════════════════════════════════════════════════════╗"
    echo -e "║  🚀 OpenClaw v5.2 — ${mode}"
    echo -e "╚════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "⏰ 时间: $(date '+%Y-%m-%d %H:%M:%S')"
    echo -e "📁 项目: ${PROJECT_DIR}"
    echo ""
}

# ── 日志清理 ──
cleanup_logs() {
    ls -t "${LOG_DIR}"/*.log 2>/dev/null | tail -n +51 | xargs rm -f 2>/dev/null || true
}

# ══════════════════════════════════════════
#  命令分发
# ══════════════════════════════════════════

cmd_tutorial() {
    acquire_lock
    mkdir -p "${LOG_DIR}"
    local log_file="${LOG_DIR}/tutorial-$(date '+%Y%m%d_%H%M%S').log"
    print_header "教程优化流水线 (14 阶段)"

    cd "${SCRIPT_DIR}"
    python3 auto_optimizer.py --mode tutorial "$@" 2>&1 | tee "${log_file}"
    local rc=${PIPESTATUS[0]}
    cleanup_logs
    exit ${rc}
}

cmd_code() {
    acquire_lock
    mkdir -p "${LOG_DIR}"
    local log_file="${LOG_DIR}/code-$(date '+%Y%m%d_%H%M%S').log"
    print_header "代码优化流水线 (5 阶段)"

    cd "${SCRIPT_DIR}"
    python3 auto_optimizer.py --mode code "$@" 2>&1 | tee "${log_file}"
    local rc=${PIPESTATUS[0]}
    cleanup_logs
    exit ${rc}
}

cmd_both() {
    acquire_lock
    mkdir -p "${LOG_DIR}"
    local log_file="${LOG_DIR}/both-$(date '+%Y%m%d_%H%M%S').log"
    print_header "教程+代码双流水线"

    cd "${SCRIPT_DIR}"
    python3 auto_optimizer.py --mode both "$@" 2>&1 | tee "${log_file}"
    local rc=${PIPESTATUS[0]}
    cleanup_logs
    exit ${rc}
}

cmd_auto() {
    acquire_lock
    mkdir -p "${LOG_DIR}"
    local log_file="${LOG_DIR}/auto-$(date '+%Y%m%d_%H%M%S').log"
    print_header "自动检测模式"

    cd "${SCRIPT_DIR}"
    python3 auto_optimizer.py --mode auto "$@" 2>&1 | tee "${log_file}"
    local rc=${PIPESTATUS[0]}
    cleanup_logs
    exit ${rc}
}

cmd_daemon() {
    local daemon_mode="${1:-continuous}"
    shift 2>/dev/null || true

    acquire_lock
    mkdir -p "${LOG_DIR}"
    local log_file="${LOG_DIR}/daemon-$(date '+%Y%m%d_%H%M%S').log"
    print_header "调度器 (${daemon_mode})"

    cd "${SCRIPT_DIR}"
    python3 auto_optimizer.py --mode "${daemon_mode}" "$@" 2>&1 | tee "${log_file}"
    local rc=${PIPESTATUS[0]}
    cleanup_logs
    exit ${rc}
}

cmd_status() {
    print_header "项目状态"

    cd "${SCRIPT_DIR}"
    python3 auto_optimizer.py --mode auto --dry-run --stage scan 2>&1
}

# ══════════════════════════════════════════
#  主入口
# ══════════════════════════════════════════

if [[ $# -eq 0 ]]; then
    show_help
    exit 0
fi

COMMAND="$1"
shift

case "${COMMAND}" in
    tutorial)   cmd_tutorial "$@" ;;
    code)       cmd_code "$@" ;;
    both)       cmd_both "$@" ;;
    auto)       cmd_auto "$@" ;;
    daemon)     cmd_daemon "$@" ;;
    status)     cmd_status ;;
    help|--help|-h) show_help ;;
    *)
        echo -e "${RED}❌ 未知命令: ${COMMAND}${NC}"
        echo "   运行 './openclaw.sh help' 查看帮助"
        exit 1
        ;;
esac
