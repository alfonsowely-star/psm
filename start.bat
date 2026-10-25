@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   Agent 配平工具
echo ============================================
echo.

where node >nul 2>nul
if errorlevel 1 (
    echo [错误] 未检测到 Node.js。请先安装 Node.js 22 或更高版本：
    echo   https://nodejs.org/
    echo.
    pause
    exit /b 1
)

where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未检测到 Python 3。请先安装：
    echo   https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

python -c "import numpy,pandas,scipy,sklearn" >nul 2>nul
if errorlevel 1 (
    echo 正在安装 Python 依赖（numpy / pandas / scipy / scikit-learn）...
    echo 首次安装需要几分钟，请耐心等待。
    echo.
    pip install numpy pandas scipy scikit-learn
)

echo 服务启动中，浏览器会自动打开 http://localhost:5175
echo 关闭此窗口即停止服务。
echo.
start "" http://localhost:5175
node src/server.mjs
pause
