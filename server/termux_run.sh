#!/data/data/com.termux/files/usr/bin/bash
# FaceMagic 验证服务器 — Termux 启动脚本
# 使用方法: bash termux_run.sh

echo "=== FaceMagic 验证服务器 ==="

# 安装依赖
pip install flask 2>/dev/null

# 启动服务器 (后台)
python server.py &
SERVER_PID=$!
echo "服务器 PID: $SERVER_PID"

# 安装并启动 ngrok
if ! command -v ngrok &> /dev/null; then
    echo "正在安装 ngrok..."
    pkg install ngrok -y 2>/dev/null || {
        echo "请手动安装 ngrok: https://ngrok.com/download"
        echo "或运行: pkg install ngrok"
    }
fi

sleep 2
echo ""
echo "启动 ngrok 隧道..."
echo "在另一个 Termux 窗口运行: ngrok http 5000"
echo ""
echo "在第一个窗口运行以下命令生成卡密:"
echo "python -c \"import requests; r=requests.post('http://127.0.0.1:5000/admin/generate', json={'token':'admin888','type':'day','count':5}); print(r.json())\""
echo ""

wait $SERVER_PID
