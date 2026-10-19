@echo off
chcp 65001 >nul
cd /d "%~dp0"

python -c "import PySide6" >nul 2>nul
if errorlevel 1 (
    echo 首次运行，正在安装 PySide6，请稍候...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo PySide6 安装失败，请检查网络或 Python 环境。
        pause
        exit /b 1
    )
)

start "" pythonw "%~dp0app.py"
