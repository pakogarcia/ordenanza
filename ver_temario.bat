@echo off
chcp 65001 >nul
.\.venv\Scripts\python.exe -c "import importlib; m = importlib.import_module('1_procesar_pdf'); print(m.generar_informe_inventario())"
echo.
pause
