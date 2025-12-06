#!/bin/bash

# FastAPI nohup 運行腳本
# 用於在背景執行 FastAPI 應用程式

# 設定變數
APP_NAME="meeting-helper-backend"
PID_FILE="$APP_NAME.pid"
LOG_DIR="logs"
LOG_FILE="$LOG_DIR/$APP_NAME.log"
ERROR_LOG="$LOG_DIR/$APP_NAME.error.log"

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 函數：顯示使用說明
show_usage() {
    echo "使用方法: $0 {start|stop|restart|status|logs}"
    echo ""
    echo "命令說明:"
    echo "  start    - 啟動 FastAPI 應用程式"
    echo "  stop     - 停止 FastAPI 應用程式"
    echo "  restart  - 重新啟動 FastAPI 應用程式"
    echo "  status   - 檢查應用程式狀態"
    echo "  logs     - 查看應用程式日誌"
    echo ""
    echo "選項:"
    echo "  --prod   - 使用生產模式 (預設為開發模式)"
    echo "  --https  - 使用 HTTPS (需要證書)"
    echo "  --workers N - 設定 worker 數量 (僅生產模式)"
}

# 函數：檢查 PID 檔案
check_pid() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            return 0  # 程序正在運行
        else
            rm -f "$PID_FILE"
            return 1  # PID 檔案存在但程序未運行
        fi
    else
        return 1  # PID 檔案不存在
    fi
}

# 函數：啟動應用程式
start_app() {
    if check_pid; then
        echo -e "${YELLOW}⚠️  應用程式已經在運行中 (PID: $PID)${NC}"
        return 1
    fi

    # 建立日誌目錄
    mkdir -p "$LOG_DIR"

    # 解析參數
    MODE="dev"
    USE_HTTPS=false
    WORKERS=4
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --prod)
                MODE="prod"
                shift
                ;;
            --https)
                USE_HTTPS=true
                shift
                ;;
            --workers)
                WORKERS="$2"
                shift 2
                ;;
            *)
                shift
                ;;
        esac
    done

    # 防止 Python 緩衝輸出
    export PYTHONUNBUFFERED=1

    # 構建命令
    if [ "$MODE" = "dev" ]; then
        if [ "$USE_HTTPS" = true ]; then
            CMD="uv run uvicorn src.main:app --host 0.0.0.0 --port 8701 --ssl-keyfile=./certs/key.pem --ssl-certfile=./certs/cert.pem --log-level info"
        else
            CMD="uv run uvicorn src.main:app --host 0.0.0.0 --port 8701 --log-level info"
        fi
    else
        if [ "$USE_HTTPS" = true ]; then
            CMD="uv run uvicorn src.main:app --host 0.0.0.0 --port 8701 --ssl-keyfile=./certs/key.pem --ssl-certfile=./certs/cert.pem --workers $WORKERS --log-level info"
        else
            CMD="uv run uvicorn src.main:app --host 0.0.0.0 --port 8701 --workers $WORKERS --log-level info"
        fi
    fi

    echo -e "${GREEN}🚀 啟動 FastAPI 應用程式...${NC}"
    echo "模式: $MODE"
    echo "HTTPS: $USE_HTTPS"
    [ "$MODE" = "prod" ] && echo "Workers: $WORKERS"
    echo "命令: $CMD"
    echo ""

    # 使用 nohup 在背景執行
    nohup $CMD > "$LOG_FILE" 2> "$ERROR_LOG" &
    
    # 獲取 PID
    PID=$!
    echo $PID > "$PID_FILE"
    
    # 等待幾秒確認啟動
    sleep 3
    
    if check_pid; then
        echo -e "${GREEN}✅ 應用程式啟動成功！${NC}"
        echo "PID: $PID"
        echo "日誌檔案: $LOG_FILE"
        echo "錯誤日誌: $ERROR_LOG"
        echo ""
        echo "訪問地址:"
        if [ "$USE_HTTPS" = true ]; then
            echo "  https://localhost:8701"
        else
            echo "  http://localhost:8701"
        fi
    else
        echo -e "${RED}❌ 應用程式啟動失敗！${NC}"
        echo "請檢查錯誤日誌: $ERROR_LOG"
        return 1
    fi
}

# 函數：停止應用程式
stop_app() {
    if ! check_pid; then
        echo -e "${YELLOW}⚠️  應用程式未在運行${NC}"
        return 1
    fi

    echo -e "${YELLOW}🛑 停止應用程式 (PID: $PID)...${NC}"
    kill "$PID"
    
    # 等待程序結束
    for i in {1..10}; do
        if ! ps -p "$PID" > /dev/null 2>&1; then
            break
        fi
        sleep 1
    done
    
    # 如果還在運行，強制終止
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "強制終止程序..."
        kill -9 "$PID"
    fi
    
    rm -f "$PID_FILE"
    echo -e "${GREEN}✅ 應用程式已停止${NC}"
}

# 函數：重新啟動應用程式
restart_app() {
    echo "重新啟動應用程式..."
    stop_app
    sleep 2
    start_app "$@"
}

# 函數：檢查狀態
check_status() {
    if check_pid; then
        echo -e "${GREEN}✅ 應用程式正在運行${NC}"
        echo "PID: $PID"
        echo ""
        echo "程序資訊:"
        ps -p "$PID" -o pid,ppid,cmd,%cpu,%mem,etime
    else
        echo -e "${RED}❌ 應用程式未在運行${NC}"
    fi
}

# 函數：查看日誌
view_logs() {
    if [ ! -f "$LOG_FILE" ]; then
        echo -e "${YELLOW}⚠️  日誌檔案不存在${NC}"
        return 1
    fi

    echo "顯示最近 50 行日誌 (按 Ctrl+C 退出):"
    echo "=================================="
    tail -f -n 50 "$LOG_FILE"
}

# 主程式
case "$1" in
    start)
        shift
        start_app "$@"
        ;;
    stop)
        stop_app
        ;;
    restart)
        shift
        restart_app "$@"
        ;;
    status)
        check_status
        ;;
    logs)
        view_logs
        ;;
    *)
        show_usage
        exit 1
        ;;
esac

exit 0