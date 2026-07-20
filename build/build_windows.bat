@echo off
chcp 65001 >nul
title FaceMagic 打包工具

echo ============================================
echo   FaceMagic — zhaohui_launcher 打包脚本
echo ============================================
echo.

:: 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Python，请先安装 Python 3.10
    pause
    exit /b 1
)

:: 进入目录
cd /d "%~dp0..\deep-live-cam"

:: 创建虚拟环境
echo [1/5] 创建虚拟环境...
if not exist venv (
    python -m venv venv
)
call venv\Scripts\activate.bat

:: 安装依赖
echo [2/5] 安装 Python 依赖...
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements.txt
pip install pyinstaller

:: 下载模型
echo [3/5] 下载模型文件...
if not exist models (
    mkdir models
)
if not exist models\inswapper_128_fp16.onnx (
    curl -L -o models\inswapper_128_fp16.onnx "https://github.com/facefusion/facefusion-assets/releases/download/models-3.0.0/inswapper_128_fp16.onnx"
)
if not exist models\gfpganv1.4.pth (
    curl -L -o models\gfpganv1.4.pth "https://github.com/facefusion/facefusion-assets/releases/download/models-3.0.0/gfpgan_1.4.pth"
)

:: 打包
echo [4/5] 打包中（可能需要 10-20 分钟）...
if exist dist rmdir /s /q dist
pyinstaller ^
    --onedir ^
    --name "zhaohui_launcher" ^
    --add-data "icon.jpg;." ^
    --add-data "locales;locales" ^
    --add-data "modules;modules" ^
    --add-data "models;models" ^
    --hidden-import PySide6.QtCore ^
    --hidden-import PySide6.QtWidgets ^
    --hidden-import PySide6.QtGui ^
    --hidden-import PySide6.QtNetwork ^
    --hidden-import cv2 ^
    --hidden-import insightface ^
    --hidden-import onnxruntime ^
    --hidden-import PIL ^
    --hidden-import requests ^
    --hidden-import numpy ^
    --hidden-import modules.auth ^
    --collect-all PySide6 ^
    zhaohui_launcher.py

:: 复制配置文件
echo [5/5] 生成启动脚本...
copy auth_config.json dist\zhaohui_launcher\
echo @echo off > dist\zhaohui_launcher\一键启动.bat
echo zhaohui_launcher.exe >> dist\zhaohui_launcher\一键启动.bat

echo.
echo ============================================
echo   打包完成！
echo   输出目录: dist\zhaohui_launcher\
echo   请先编辑 auth_config.json 设置服务器地址
echo   然后运行 一键启动.bat
echo ============================================
pause
