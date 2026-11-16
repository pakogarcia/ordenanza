@echo off
chcp 65001 >nul
cd /d "%~dp0"
git pull origin main
set GITHUB_EVENT_NAME=schedule
.\.venv\Scripts\python.exe 2_generar_test.py
git add temario.db
git diff --staged --quiet || (git commit -m "chore: actualizar contador veces_usado en temario.db" && git push origin main)
