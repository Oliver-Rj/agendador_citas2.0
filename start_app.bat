@echo off
title Iniciando el bot de citas
cd /d %~dp0
call venv\Scripts\activate
python app.py
echo.
echo El bot se cerró. Presiona una tecla para salir.
pause >nul
