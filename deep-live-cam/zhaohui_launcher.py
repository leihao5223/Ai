#!/usr/bin/env python3
"""
FaceMagic Launcher — account login verification, then start main program
"""
import os, sys, json
from pathlib import Path

project_root = os.path.dirname(os.path.abspath(__file__))
os.environ["PATH"] = project_root + os.pathsep + os.environ.get("PATH", "")
sys.path.insert(0, project_root)

from modules.auth import run_auth, load_local_token
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

AUTH_CONFIG_FILE = os.path.join(project_root, "auth_config.json")

def load_config():
    default = {"server_url": "http://127.0.0.1:5000", "last_username": ""}
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
            json.dump(config, f, indent=4)
    except Exception:
        pass

def main():
    print("=" * 50)
    print("  FaceMagic v1.0")
    print("=" * 50)

    config = load_config()

    app = QApplication(sys.argv)
    icon_path = os.path.join(project_root, "icon.jpg")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # Integrity check
    from modules.guard import verify
    ok, _ = verify()
    if not ok:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.critical(None, "安全验证失败",
            "文件校验未通过或检测到调试器\n\n请联系 @zz522377")
        sys.exit(1)

    auth_ok = run_auth(icon_path, config.get("server_url", "http://127.0.0.1:5000"))
    if not auth_ok:
        print("用户退出登录")
        sys.exit(0)

    print("登录验证通过，启动主程序...")

    token = load_local_token()
    if token:
        config["last_username"] = token.get("username", "")
        save_config(config)

    from modules import core
    core.run()

if __name__ == "__main__":
    main()
