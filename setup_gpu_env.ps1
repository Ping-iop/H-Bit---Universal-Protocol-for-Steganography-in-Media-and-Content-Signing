# Script de configuración para entorno H-Bit con GPU (CUDA 12.x)
Write-Host "Iniciando configuración de entorno GPU..." -ForegroundColor Cyan

# 1. Crear entorno virtual
if (!(Test-Path "gpu_env")) {
    Write-Host "Creando entorno virtual 'gpu_env'..."
    python -m venv gpu_env
} else {
    Write-Host "Entorno 'gpu_env' ya existe."
}

# 2. Activar y actualizar pip
Write-Host "Actualizando pip..."
& .\gpu_env\Scripts\python.exe -m pip install --upgrade pip

# 3. Instalar dependencias base
Write-Host "Instalando dependencias base..."
$deps = "numpy>=1.26.0", "scipy>=1.12.0", "Pillow>=10.2.0", "opencv-python-headless>=4.9.0", "reedsolo>=1.7.0", "click>=8.1.0", "cryptography>=42.0.0", "customtkinter", "packaging"
& .\gpu_env\Scripts\pip.exe install $deps

# 4. Instalar CuPy para CUDA 12.x
Write-Host "Instalando soporte GPU (cupy-cuda12x)..." -ForegroundColor Yellow
& .\gpu_env\Scripts\pip.exe install cupy-cuda12x

# 5. Crear script de lanzamiento
Write-Host "Creando launcher 'run_hbit_gpu.bat'..."
$launcherContent = "@echo off
cd /d ""%~dp0""
echo Activando entorno GPU...
call gpu_env\Scripts\activate.bat
echo Iniciando H-Bit GUI...
python hbit_gui.py
pause"

Set-Content -Path "run_hbit_gpu.bat" -Value $launcherContent

Write-Host "¡Configuración completada exitosamente!" -ForegroundColor Green
Write-Host "Ejecuta 'run_hbit_gpu.bat' para iniciar la aplicación."
