#!/usr/bin/env python3
"""
渣辉启动器 — FaceMagic 唯一入口
带卡密验证，验证通过后启动主程序
"""
import os
import sys
import json
import platform
from pathlib import Path

# 添加项目根目录到 PATH
project_root = os.path.dirname(os.path.abspath(__file__))
os.environ["PATH"] = project_root + os.pathsep + os.environ.get("PATH", "")

# 导入验证模块
sys.path.insert(0, project_root)
from modules.auth import run_auth, get_device_id, verify_with_server, check_auth, load_local_token, clear_local_token, save_local_token
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QIcon

AUTH_CONFIG_FILE = os.path.join(project_root, "auth_config.json")

def load_config():
    default = {
        "server_url": "http://127.0.0.1:5000",
        "last_card_key": ""
    }
    try:
        if os.path.exists(AUTH_CONFIG_FILE):
            with open(AUTH_CONFIG_FILE, "r") as f:
                return {**default, **json.load(f)}
    except Exception:
        pass
    return default

def save_config(config):
    try:
        with open(AUTH_CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
    except Exception:
        pass

def main():
    print("=" * 50)
    print("  渣辉启动器 v1.0 — FaceMagic")
    print("=" * 50)

    # 加载配置
    config = load_config()

    # 创建 Qt 应用
    app = QApplication(sys.argv)
    icon_path = os.path.join(project_root, "icon.jpg")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # 运行卡密验证
    auth_ok = run_auth(icon_path, config.get("server_url", "http://127.0.0.1:5000"))

    if not auth_ok:
        print("用户退出验证")
        sys.exit(0)

    print("验证通过，启动主程序...")

    # 更新配置
    token = load_local_token()
    if token:
        config["last_card_key"] = token.get("card_key", "")
        save_config(config)

    # 导入并启动主程序
    from modules import core
    core.run()

if __name__ == "__main__":
    main()
