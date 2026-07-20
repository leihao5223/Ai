#!/data/data/com.termux/files/usr/bin/bash
# FaceMagic 一键启动（Termux）
# 开两个窗口：
#   窗口1: bash start.sh        # 启动服务器
#   窗口2: 运行管理命令

echo "========================================"
echo "  FaceMagic 卡密系统 — Termux 一键启动"
echo "========================================"
echo ""

# 检查 Python
if ! command -v python &> /dev/null; then
    echo "正在安装 Python..."
    pkg install python -y
fi

# 安装依赖
pip install flask requests 2>/dev/null

# 启动服务器
echo "🚀 启动验证服务器 (端口 5000)..."
cd "$(dirname "$0")"
python server.py &
SERVER_PID=$!
echo "   服务器 PID: $SERVER_PID"

sleep 2
echo ""
echo "✅ 服务器已启动！"
echo ""
echo "📌 在另一个 Termux 窗口运行 ngrok:"
echo "   ngrok http 5000"
echo ""
echo "📌 管理卡密:"
echo "   python manage.py gen day 10     # 生成10张天卡"
echo "   python manage.py gen month 5    # 生成5张月卡"
echo "   python manage.py gen year 2     # 生成2张年卡"
echo "   python manage.py list           # 查所有卡密"
echo "   python manage.py stats          # 统计"
echo ""
echo "📌 从 ngrok 拿到地址后，编辑:"
echo "   deep-live-cam/auth_config.json"
echo "   把 server_url 改成你的 ngrok 地址"
echo ""
echo "按 Ctrl+C 停止服务器"

# 等待服务器进程
wait $SERVER_PID
