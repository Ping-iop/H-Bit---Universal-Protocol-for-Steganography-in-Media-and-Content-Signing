@echo off
cd /d "%~dp0"
echo Activando entorno GPU...
call gpu_env\Scripts\activate.bat
echo Iniciando H-Bit GUI...
python hbit_gui.py
pause
