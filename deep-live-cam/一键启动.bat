@echo off
chcp 65001 >nul
title FaceMagic 一键启动

setlocal enabledelayedexpansion

cd /d "%~dp0"

echo ════════════════════════════════════════
echo   FaceMagic — 一键启动
echo ════════════════════════════════════════
echo.

REM ── 检查 Python ──
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Python，请先安装 Python 3.10+
    echo 下载地址: https://www.python.org/downloads/
    echo 安装时记得勾选 "Add Python to PATH"
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set pyver=%%i
echo [✓] Python %pyver%

REM ── 检查 venv ──
if exist "venv\Scripts\python.exe" (
    echo [✓] 虚拟环境已存在，跳过配置
    echo.
    goto LAUNCH
)

echo.
echo [*] 首次使用，正在配置环境，请耐心等待...
echo [*] 下载量约 500MB，耗时取决于网络
echo.

REM ── 创建虚拟环境 ──
echo [1/6] 创建虚拟环境...
python -m venv venv
if %errorlevel% neq 0 (
    echo [错误] 创建虚拟环境失败
    pause
    exit /b 1
)

REM ── 升级 pip ──
echo [2/6] 升级 pip...
call venv\Scripts\python.exe -m pip install --upgrade pip -q

REM ── 安装基础依赖 ──
echo [3/6] 安装基础依赖...
call venv\Scripts\python.exe -m pip install numpy opencv-python pillow psutil tqdm -q
if %errorlevel% neq 0 (
    echo [错误] 基础依赖安装失败
    pause
    exit /b 1
)

REM ── 安装 onnxruntime ──
echo [4/6] 安装 AI 推理引擎...
echo    尝试 GPU 版本（需要 NVIDIA 显卡 + CUDA）...
call venv\Scripts\python.exe -m pip install onnxruntime-gpu==1.23.2 -q
if %errorlevel% neq 0 (
    echo    未检测到 CUDA，安装 CPU 版本...
    call venv\Scripts\python.exe -m pip install onnxruntime -q
)
echo    [✓] onnxruntime 安装完成

REM ── 安装其他依赖 ──
echo [5/6] 安装其他依赖...
call venv\Scripts\python.exe -m pip install insightface==0.7.3 -q
call venv\Scripts\python.exe -m pip install PySide6 -q
call venv\Scripts\python.exe -m pip install opennsfw2 protobuf requests -q
if %errorlevel% neq 0 (
    echo [警告] 部分依赖安装失败，但不影响核心功能
)

REM ── 下载模型 ──
echo [6/6] 检查模型文件...
if not exist "models\inswapper_128_fp16.onnx" (
    echo    下载人脸模型(约 90MB)...
    call venv\Scripts\python.exe -c "import urllib.request; urllib.request.urlretrieve('https://huggingface.co/hacksider/deep-live-cam/resolve/main/inswapper_128_fp16.onnx', 'models\inswapper_128_fp16.onnx')"
)
if not exist "models\GFPGANv1.4.pth" (
    echo    下载增强模型(约 340MB)... 比较慢，请耐心等待...
    call venv\Scripts\python.exe -c "import urllib.request; urllib.request.urlretrieve('https://github.com/TencentARC/GFPGAN/releases/download/v1.3.4/GFPGANv1.4.pth', 'models\GFPGANv1.4.pth')"
)

echo.
echo ════════════════════════════════════════
echo   环境配置完成！正在启动程序...
echo ════════════════════════════════════════
echo.

:LAUNCH
call venv\Scripts\python.exe 渣辉启动器.py
if %errorlevel% neq 0 (
    echo.
    echo [错误] 启动失败，尝试重新配置环境...
    echo 删除 venv 文件夹后重试
    pause
)
