@echo off
chcp 65001 >nul
echo ========================================================
echo   ACTUALIZANDO TEMARIO Y SINCRONIZANDO CON GITHUB
echo ========================================================
echo.
echo [1/4] Descargando el progreso actual de temario.db desde GitHub...
git pull origin main

echo.
echo [2/4] Procesando todos los archivos PDF de la carpeta...
.\.venv\Scripts\python.exe 1_procesar_pdf.py

echo.
echo [3/4] Ejecutando auditoria de seguridad de BD y usuarios...
.\.venv\Scripts\python.exe 5_auditoria_seguridad.py
if errorlevel 1 (
    echo.
    echo [ERROR] La auditoria de seguridad detecto un problema. Abortando subida.
    pause
    exit /b 1
)

echo.
echo [4/4] Subiendo la base de datos actualizada a GitHub...
git add temario.db 1_procesar_pdf.py 2_generar_test.py inventario_temario.txt
git commit -m "chore: actualizar temario.db con nuevos temas"
git push origin main

echo.
echo ========================================================
echo   PROCESO COMPLETADO CON EXITO
echo ========================================================
pause
