@echo off
chcp 65001 >nul
git pull origin main >nul 2>&1
.\.venv\Scripts\python.exe 3_ver_suscriptores.py
git add temario.db >nul 2>&1
git diff --staged --quiet || (git commit -m "chore: sincronizar suscriptores en temario.db" >nul 2>&1 && git push origin main >nul 2>&1)
echo.
pause
