@echo off
REM 司法证据链 Agent — 一键启动

echo 清理缓存...
for /d /r . %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d" 2>nul
for /r . %%f in (*.pyc) do @del /q "%%f" 2>nul

echo 启动后端 (端口 9009)...
start "Backend" cmd /c "cd /d %~dp0 && python server.py"

timeout /t 4 /nobreak >nul

echo 启动前端...
cd /d %~dp0ui
start "Frontend" cmd /c "npm run dev"

echo.
echo ========================================
echo 浏览器打开 http://localhost:5173
echo ========================================
pause
