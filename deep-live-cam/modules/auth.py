"""FaceMagic 卡密验证模块 — 客户端"""
import json
import os
import sys
import platform
import uuid
import requests
from datetime import datetime
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton,
    QHBoxLayout, QMessageBox, QApplication
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap, QIcon

# ─── 配置 ────────────────────────────────────────────────────────────────────

# 本地 token 存储路径
TOKEN_FILE = os.path.join(os.path.dirname(__file__), "..", ".auth_token")

# XOR 混淆密钥 (只是为了防明文读取)
XOR_KEY = b"FaceMagic_XOR_2025_Secret!!"

def _xor_obfuscate(data: bytes) -> bytes:
    return bytes(b ^ XOR_KEY[i % len(XOR_KEY)] for i, b in enumerate(data))

def get_device_id():
    """生成稳定的设备 ID"""
    system = platform.system()
    node = platform.node()
    machine = platform.machine()
    raw = f"{system}-{node}-{machine}"
    return uuid.uuid5(uuid.NAMESPACE_DNS, raw).hex[:16]

def load_local_token() -> dict | None:
    """读取本地缓存的 token"""
    try:
        path = TOKEN_FILE
        if not os.path.exists(path):
            return None
        with open(path, "rb") as f:
            encrypted = f.read()
        decrypted = _xor_obfuscate(encrypted)
        data = json.loads(decrypted.decode())
        return data
    except Exception:
        return None

def save_local_token(data: dict):
    """保存 token 到本地"""
    try:
        raw = json.dumps(data, ensure_ascii=False).encode()
        encrypted = _xor_obfuscate(raw)
        with open(TOKEN_FILE, "wb") as f:
            f.write(encrypted)
    except Exception:
        pass

def clear_local_token():
    """清除本地 token"""
    try:
        if os.path.exists(TOKEN_FILE):
            os.remove(TOKEN_FILE)
    except Exception:
        pass

def verify_with_server(card_key: str, device_id: str, server_url: str = "http://127.0.0.1:5000") -> dict:
    """向服务器验证卡密"""
    try:
        resp = requests.post(
            f"{server_url.rstrip('/')}/verify",
            json={"card_key": card_key, "device_id": device_id},
            timeout=10
        )
        return resp.json()
    except requests.exceptions.Timeout:
        return {"success": False, "msg": "连接服务器超时，请检查网络"}
    except requests.exceptions.ConnectionError:
        return {"success": False, "msg": "无法连接验证服务器，请检查网络"}
    except Exception as e:
        return {"success": False, "msg": f"验证异常: {str(e)}"}

def check_auth() -> bool:
    """检查本地 token 是否有效（离线检查）"""
    token = load_local_token()
    if token is None:
        return False
    expires_at = token.get("expires_at")
    if not expires_at:
        return False
    try:
        expire_dt = datetime.fromisoformat(expires_at)
        if datetime.now() < expire_dt:
            return True
    except Exception:
        pass
    clear_local_token()
    return False


class AuthDialog(QDialog):
    """卡密登录对话框"""

    def __init__(self, icon_path: str = "", server_url: str = "http://127.0.0.1:5000"):
        super().__init__()
        self.setWindowTitle("渣辉启动器 - 卡密验证")
        self.setFixedSize(420, 300)
        self._server_url = server_url
        self.setStyleSheet("""
            QDialog { background-color: #1a1a2e; }
            QLabel { color: #e0e0e0; font-size: 12pt; }
            QLineEdit {
                background-color: #16213e;
                color: #e0e0e0;
                border: 1px solid #0f3460;
                border-radius: 6px;
                padding: 10px;
                font-size: 14pt;
                font-family: monospace;
            }
            QPushButton {
                background-color: #e94560;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px 20px;
                font-size: 12pt;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #ff6b81; }
            QPushButton:pressed { background-color: #c23152; }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(30, 25, 30, 25)

        # 标题
        title = QLabel("渣辉启动器 v1.0")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 18pt; font-weight: bold; color: #e94560;")
        layout.addWidget(title)

        subtitle = QLabel("请输入卡密激活软件")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("font-size: 10pt; color: #888;")
        layout.addWidget(subtitle)

        layout.addSpacing(10)

        # 卡密输入框
        self.card_input = QLineEdit()
        self.card_input.setPlaceholderText("AI-XXXX-XXXX-XXXX")
        self.card_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.card_input.returnPressed.connect(self.on_verify)
        layout.addWidget(self.card_input)

        # 状态提示
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("font-size: 10pt;")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        layout.addSpacing(5)

        # 按钮
        btn_layout = QHBoxLayout()
        self.verify_btn = QPushButton("激 活")
        self.verify_btn.clicked.connect(self.on_verify)
        btn_layout.addWidget(self.verify_btn)

        self.exit_btn = QPushButton("退出")
        self.exit_btn.setStyleSheet("background-color: #555;")
        self.exit_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.exit_btn)
        layout.addLayout(btn_layout)

        layout.addStretch()

        self.result = None
        self._loading = False

    def set_loading(self, loading: bool):
        self._loading = loading
        self.verify_btn.setEnabled(not loading)
        self.card_input.setEnabled(not loading)
        if loading:
            self.verify_btn.setText("验证中...")
        else:
            self.verify_btn.setText("激 活")

    def on_verify(self):
        if self._loading:
            return
        card_key = self.card_input.text().strip().upper()
        if not card_key:
            self.status_label.setText("请输入卡密")
            self.status_label.setStyleSheet("font-size: 10pt; color: #ff6b6b;")
            return

        self.set_loading(True)
        self.status_label.setText("正在验证...")
        self.status_label.setStyleSheet("font-size: 10pt; color: #ffd93d;")
        QApplication.processEvents()

        device_id = get_device_id()
        result = verify_with_server(card_key, device_id, self._server_url)

        self.set_loading(False)
        if result.get("success"):
            save_local_token({
                "card_key": card_key,
                "expires_at": result.get("expires_at", ""),
                "device_id": device_id,
            })
            self.status_label.setText("✅ " + result.get("msg", "验证成功"))
            self.status_label.setStyleSheet("font-size: 10pt; color: #6bcb77;")
            QApplication.processEvents()
            QTimer.singleShot(800, self.accept)
        else:
            self.status_label.setText("❌ " + result.get("msg", "验证失败"))
            self.status_label.setStyleSheet("font-size: 10pt; color: #ff6b6b;")

    def get_card_key(self) -> str:
        return self.card_input.text().strip().upper() if self.result else ""


def run_auth(icon_path: str = "", server_url: str = "http://127.0.0.1:5000") -> bool:
    """
    运行卡密验证流程。
    返回 True 表示验证通过，False 表示退出。
    """
    # 先检查本地 token
    if check_auth():
        return True

    # 没有本地 token 或已过期，显示登录对话框
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    dialog = AuthDialog(icon_path, server_url)
    result = dialog.exec()

    if result == QDialog.DialogCode.Accepted:
        return True
    return False
