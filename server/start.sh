#!/data/data/com.termux/files/usr/bin/bash
# FaceMagic 一键启动（Termux）

echo "========================================"
echo "  FaceMagic 账号验证服务器"
echo "  零依赖 | 极致轻量"
echo "========================================"
echo ""

cd "$(dirname "$0")"

echo "📌 启动:"
echo "   bash run_bg.sh start       # 普通后台（手机可休眠）"
echo "   bash run_bg.sh start wake  # 后台+唤醒锁（不眠）"
echo ""
echo "📌 管理面板: http://127.0.0.1:5000/admin/"
echo "   默认密码: admin888"
echo ""
echo "📌 暴露到外网（另开窗口）:"
echo "   ngrok http 5000"
echo ""

bash run_bg.sh start
