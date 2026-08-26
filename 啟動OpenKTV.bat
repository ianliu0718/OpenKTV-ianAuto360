@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
	echo 找不到 .venv\Scripts\python.exe
	echo 請確認這是完整的 OpenKTV 專案資料夾。
	pause
	exit /b 1
)

if not exist "main.py" (
	echo 找不到 main.py
	pause
	exit /b 1
)

".venv\Scripts\python.exe" "main.py"
pause