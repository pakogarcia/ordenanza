@echo off
chcp 65001 >nul
git pull origin main >nul 2>&1
.\.venv\Scripts\python.exe 3_ver_suscriptores.py
echo.
pause
