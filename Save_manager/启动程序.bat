@echo off
echo Requesting administrative privileges...

:: 检查是否已经以管理员权限运行
net session >nul 2>&1
if %errorLevel% == 0 (
    echo Administrative privileges confirmed.
    goto :run_script
) else (
    echo Administrative privileges not found. Requesting...
    :: 以管理员权限重新启动脚本
    powershell -Command "Start-Process cmd -Verb RunAs -ArgumentList '/c %~dpnx0'"
    exit /b
)

:run_script
echo Running main.py...
python main.py
pause 