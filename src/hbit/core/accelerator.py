"""
Módulo de Aceleración de Hardware para H-Bit.

Este módulo gestiona la selección del backend numérico adecuado:
- CuPy (GPU NVIDIA): Si está disponible y se detecta hardware compatible.
- NumPy (CPU): Fallback por defecto o si no hay GPU.

Expone 'xp' como alias al backend seleccionado, permitiendo escribir
código agnóstico al dispositivo.
"""

import sys
import os
import numpy as np

# Intentar añadir rutas de CUDA al DLL search path (Windows)
# Esto ayuda si el usuario tiene el Toolkit instalado pero no en PATH
cuda_candidates = [
    r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v13.1\bin",
    r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v13.0\bin",
    r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.6\bin",
    r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.5\bin", 
    r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.4\bin",
    r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.3\bin",
    r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.2\bin",
    r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.1\bin",
    r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.0\bin",
]

if hasattr(os, "add_dll_directory"):
    # 1. Rutas del System Toolkit (si existen)
    for p in cuda_candidates:
        if os.path.exists(p):
            try:
                os.add_dll_directory(p)
            except Exception:
                pass

    # 2. Rutas de paquetes pip 'nvidia-*' (portable)
    # Busca en todos los site-packages activos
    import site
    try:
        # Combinar sitios globales y de usuario
        site_paths = site.getsitepackages() + [site.getusersitepackages()]
        # Añadir path del entorno actual si no está (e.g. venv)
        if sys.prefix:
            site_paths.append(os.path.join(sys.prefix, "Lib", "site-packages"))
            
        for sp in site_paths:
            nvidia_path = os.path.join(sp, "nvidia")
            if os.path.exists(nvidia_path):
                # Escanear subcarpetas (cufft, cudart, etc.)
                for item in os.listdir(nvidia_path):
                    bin_path = os.path.join(nvidia_path, item, "bin")
                    if os.path.exists(bin_path):
                        try:
                            os.add_dll_directory(bin_path)
                            # print(f"H-Bit Accelerator: Portable lib -> {bin_path}")
                        except Exception:
                            pass
    except Exception:
        pass

# Intentar importar cupy para aceleración GPU
try:
    import cupy as cp
    
    # 1. Verificar hardware
    if cp.cuda.runtime.getDeviceCount() > 0:
        # 2. Verificar librerías críticas (FFT)
        # Esto detecta si faltan DLLs (cufft64_*.dll) antes de que falle la app
        # Si esto lanza ImportError (DLL load failed), caemos al except
        from cupy.cuda import cufft
        
        xp = cp
        print("H-Bit Accelerator: GPU NVIDIA detectada y funcional. Usando CuPy Backend.")
    else:
        xp = np
        print("H-Bit Accelerator: No se detectaron dispositivos CUDA. Usando NumPy (CPU).")
        
except (ImportError, Exception) as e:
    # Captura tanto ImportError (DLL missing) como errores de runtime
    xp = np
    print(f"H-Bit Accelerator: GPU no disponible o incompleta ({e}). Usando NumPy (CPU).")

def to_device(array):
    """Mueve un array al dispositivo seleccionado (GPU o CPU)."""
    if xp == np:
        return array
    return xp.asarray(array)

def to_cpu(array):
    """Mueve un array desde el dispositivo a la CPU (numpy explícito)."""
    if xp == np:
        return array
    # Si es cupy array, tiene método get() o usamos asnumpy
    if hasattr(array, 'get'):
        return array.get()
    return np.asarray(array)
