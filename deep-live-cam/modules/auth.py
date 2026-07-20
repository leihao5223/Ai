"""FaceMagic 账号登录模块 — 客户端"""
import json
import os
import sys
import platform
import uuid
import requests
from datetime import datetime
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton,
    QHBoxLayout, QApplication
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon

# ─── 配置 ────────────────────────────────────────────────────────────────────

TOKEN_FILE = os.path.join(os.path.dirname(__file__), "..", ".auth_token")

XOR_KEY = b"FaceMagic_XOR_2025_Secret!!"

def _xor_obfuscate(data: bytes) -> bytes:
    return bytes(b ^ XOR_KEY[i % len(XOR_KEY)] for i, b in enumerate(data))

def get_device_id():
    system = platform.system()
    node = platform.node()
    machine = platform.machine()
    raw = f"{system}-{node}-{machine}"
    return uuid.uuid5(uuid.NAMESPACE_DNS, raw).hex[:16]

def load_local_token() -> dict | None:
    try:
        if not os.path.exists(TOKEN_FILE):
            return None
        with open(TOKEN_FILE, "rb") as f:
            encrypted = f.read()
        decrypted = _xor_obfuscate(encrypted)
        return json.loads(decrypted.decode())
    except Exception:
        return None

def save_local_token(data: dict):
    try:
        raw = json.dumps(data, ensure_ascii=False).encode()
        encrypted = _xor_obfuscate(raw)
        with open(TOKEN_FILE, "wb") as f:
            f.write(encrypted)
    except Exception:
        pass

def clear_local_token():
    try:
        if os.path.exists(TOKEN_FILE):
            os.remove(TOKEN_FILE)
    except Exception:
        pass

def login_with_server(username: str, password: str, server_url: str = "http://127.0.0.1:5000") -> dict:
    """向服务器发起账号密码登录"""
    try:
        resp = requests.post(
            f"{server_url.rstrip('/')}/api/login",
            json={"username": username, "password": password},
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
    """检查本地 token 是否有效"""
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


class LoginDialog(QDialog):
    """账号登录对话框"""

    def __init__(self, icon_path: str = "", server_url: str = "http://127.0.0.1:5000"):
        super().__init__()
        self.setWindowTitle("FaceMagic - 登录")
        self.setFixedSize(400, 320)
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
                font-size: 13pt;
            }
            QLineEdit:focus { border-color: #e94560; }
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
        layout.setSpacing(12)
        layout.setContentsMargins(30, 25, 30, 25)

        # 标题
        title = QLabel("FaceMagic")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 22pt; font-weight: bold; color: #e94560;")
        layout.addWidget(title)

        subtitle = QLabel("请输入账号密码登录")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("font-size: 10pt; color: #888;")
        layout.addWidget(subtitle)

        layout.addSpacing(15)

        # 用户名输入
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("用户名")
        self.username_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.username_input)

        # 密码输入
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("密码")
        self.password_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.password_input.returnPressed.connect(self.on_login)
        layout.addWidget(self.password_input)

        # 状态提示
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("font-size: 10pt;")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        layout.addSpacing(5)

        # 按钮
        btn_layout = QHBoxLayout()
        self.login_btn = QPushButton("登 录")
        self.login_btn.clicked.connect(self.on_login)
        btn_layout.addWidget(self.login_btn)

        self.exit_btn = QPushButton("退出")
        self.exit_btn.setStyleSheet("background-color: #555;")
        self.exit_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.exit_btn)
        layout.addLayout(btn_layout)

        layout.addStretch()

        self._loading = False

    def set_loading(self, loading: bool):
        self._loading = loading
        self.login_btn.setEnabled(not loading)
        self.username_input.setEnabled(not loading)
        self.password_input.setEnabled(not loading)
        self.login_btn.setText("登录中..." if loading else "登 录")

    def on_login(self):
        if self._loading:
            return
        username = self.username_input.text().strip()
        password = self.password_input.text()

        if not username:
            self.status_label.setText("请输入用户名")
            self.status_label.setStyleSheet("font-size: 10pt; color: #ff6b6b;")
            return
        if not password:
            self.status_label.setText("请输入密码")
            self.status_label.setStyleSheet("font-size: 10pt; color: #ff6b6b;")
            return

        self.set_loading(True)
        self.status_label.setText("正在验证...")
        self.status_label.setStyleSheet("font-size: 10pt; color: #ffd93d;")
        QApplication.processEvents()

        result = login_with_server(username, password, self._server_url)

        self.set_loading(False)
        if result.get("success"):
            save_local_token({
                "username": username,
                "token": result.get("token", ""),
                "expires_at": result.get("expires_at", ""),
                "account_expires_at": result.get("account_expires_at", ""),
            })
            msg = result.get("msg", "登录成功")
            self.status_label.setText(msg)
            self.status_label.setStyleSheet("font-size: 10pt; color: #6bcb77;")
            QApplication.processEvents()
            QTimer.singleShot(500, self.accept)
        else:
            self.status_label.setText(result.get("msg", "登录失败"))
            self.status_label.setStyleSheet("font-size: 10pt; color: #ff6b6b;")


def run_auth(icon_path: str = "", server_url: str = "http://127.0.0.1:5000") -> bool:
    """
    运行登录验证流程。
    返回 True 表示验证通过，False 表示退出。
    """
    # 先检查本地 token
    if check_auth():
        return True

    # 没有有效 token，显示登录对话框
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    if icon_path and os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    dialog = LoginDialog(icon_path, server_url)
    result = dialog.exec()

    if result == QDialog.DialogCode.Accepted:
        return True
    return False
