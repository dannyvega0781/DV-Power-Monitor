@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONUNBUFFERED=1"

if exist ".venv_windows\Scripts\python.exe" goto dependencias

echo Creando el entorno de respaldo para Windows...
py -3.13 -m venv .venv_windows
if errorlevel 1 goto error

:dependencias
".venv_windows\Scripts\python.exe" -c "import flask, serial, matplotlib, reportlab" >nul 2>&1
if not errorlevel 1 goto ejecutar

echo Instalando las librerias. Esta primera instalacion requiere Internet...
".venv_windows\Scripts\python.exe" -m pip install flask pyserial matplotlib reportlab
if errorlevel 1 goto error

:ejecutar
".venv_windows\Scripts\python.exe" lanzar_windows.py %*
if errorlevel 1 goto error
echo.
echo DV Power Monitor se ha detenido.
pause
exit /b 0

:error
echo.
echo No se pudo completar el inicio. Revisa el mensaje anterior.
echo Comprueba que Python 3.13 este instalado y el Arduino conectado.
pause
exit /b 1
