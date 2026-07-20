@echo off
title FaceMagic Launcher
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ========================================
echo   FaceMagic Launcher
echo ========================================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Install Python 3.10+
    echo Download: https://www.python.org/downloads/
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set pyver=%%i
echo [OK] Python %pyver%

if exist "venv\Scripts\python.exe" (
    echo [OK] Virtual env found
    echo.
    goto LAUNCH
)

echo.
echo First time setup - installing dependencies (about 500MB)
echo.

echo [1/6] Creating virtual env...
python -m venv venv
if %errorlevel% neq 0 (
    echo [ERROR] Failed to create virtual env
    pause
    exit /b 1
)

echo [2/6] Upgrading pip...
call venv\Scripts\python.exe -m pip install --upgrade pip -q

echo [3/6] Installing base deps...
call venv\Scripts\python.exe -m pip install numpy opencv-python pillow psutil tqdm -q
if %errorlevel% neq 0 (
    echo [ERROR] Base deps install failed
    pause
    exit /b 1
)

echo [4/6] Installing AI engine...
echo     Trying GPU (needs NVIDIA + CUDA)...
call venv\Scripts\python.exe -m pip install onnxruntime-gpu==1.23.2 -q
if %errorlevel% neq 0 (
    echo     No CUDA, installing CPU version...
    call venv\Scripts\python.exe -m pip install onnxruntime -q
)
echo    [OK] onnxruntime installed

echo [5/6] Installing other deps...
echo     Installing insightface...
call venv\Scripts\python.exe -m pip install insightface==0.7.3 -q
if %errorlevel% neq 0 (
    echo     Build failed - installing C++ compiler...
    where winget >nul 2>&1
    if !errorlevel! equ 0 (
        winget install Microsoft.VisualStudio.2022.BuildTools --silent --accept-package-agreements 2>&1 | findstr /i "success"
    )
    call venv\Scripts\python.exe -m pip install insightface==0.7.3 -q
    if !errorlevel! neq 0 (
        echo     Still failed, trying latest version...
        call venv\Scripts\python.exe -m pip install insightface -q
    )
)
echo     Installing PySide6...
call venv\Scripts\python.exe -m pip install PySide6 -q
echo     Installing other packages...
call venv\Scripts\python.exe -m pip install opennsfw2 protobuf requests -q

echo [6/6] Checking models...
if not exist "models\inswapper_128_fp16.onnx" (
    echo     Downloading face model (90MB)...
    call venv\Scripts\python.exe -c "import urllib.request; urllib.request.urlretrieve('https://huggingface.co/hacksider/deep-live-cam/resolve/main/inswapper_128_fp16.onnx', 'models\inswapper_128_fp16.onnx')"
)
if not exist "models\GFPGANv1.4.pth" (
    echo     Downloading enhancer model (340MB)... please wait...
    call venv\Scripts\python.exe -c "import urllib.request; urllib.request.urlretrieve('https://github.com/TencentARC/GFPGAN/releases/download/v1.3.4/GFPGANv1.4.pth', 'models\GFPGANv1.4.pth')"
)

echo.
echo ========================================
echo   Setup complete! Starting program...
echo ========================================
echo.

:LAUNCH
call venv\Scripts\python.exe zhaohui_launcher.py
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Launch failed, try deleting venv folder and retry
    pause
)
