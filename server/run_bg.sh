#!/data/data/com.termux/files/usr/bin/bash
# FaceMagic 服务端 — 后台常驻启动脚本（极致轻量）
# 用法: bash run_bg.sh {start|stop|restart|status} [wake]

cd "$(dirname "$0")"

PID_FILE="server.pid"
LOG_FILE="server.log"

stop_server() {
    if [ -f "$PID_FILE" ]; then
        kill "$(cat "$PID_FILE")" 2>/dev/null
        rm -f "$PID_FILE"
        echo "服务已停止"
    fi
    termux-wake-unlock 2>/dev/null || true
}

start_server() {
    # 第二个参数为 wake 时才启用唤醒锁（默认不用，省电）
    if [ "${2:-}" = "wake" ]; then
        termux-wake-lock 2>/dev/null || true
        echo "[已启用唤醒锁，防止手机休眠]"
    else
        echo "[未启用唤醒锁，手机可正常休眠]"
        echo "[如需唤醒锁，请运行: bash run_bg.sh start wake]"
    fi

    # 后台启动（零依赖，无需 pip install）
    nohup python server.py > "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"

    sleep 2
    if kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo "FaceMagic 服务端已启动 (PID: $(cat $PID_FILE))"
        echo "日志: $LOG_FILE"
        echo "管理面板: http://127.0.0.1:5000/admin/"
        echo ""
        echo "暴露到外网（另开窗口）: ngrok http 5000"
    else
        echo "启动失败，查看日志: cat $LOG_FILE"
        termux-wake-unlock 2>/dev/null || true
    fi
}

case "${1:-start}" in
    start) start_server "$@" ;;
    stop)  stop_server ;;
    restart) stop_server; sleep 1; start_server "$@" ;;
    status)
        if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
            echo "运行中 (PID: $(cat $PID_FILE))"
        else
            echo "未运行"
        fi ;;
    *) echo "用法: bash run_bg.sh {start|stop|restart|status} [wake]" ;;
esac
