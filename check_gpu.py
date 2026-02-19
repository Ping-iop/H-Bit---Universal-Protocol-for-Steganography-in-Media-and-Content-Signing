import sys
import os

print(f"Versión de Python: {sys.version}")

try:
    import cupy
    print(f"CuPy instalado: Sí (Versión: {cupy.__version__})")
    
    try:
        count = cupy.cuda.runtime.getDeviceCount()
        print(f"Dispositivos CUDA detectados: {count}")
        for i in range(count):
            props = cupy.cuda.runtime.getDeviceProperties(i)
            name = props['name'].decode('utf-8')
            mem = props['totalGlobalMem'] / (1024**3)
            print(f"  [{i}] {name} - VRAM: {mem:.2f} GB")
    except Exception as e:
        print(f"Error accediendo a runtime CUDA: {e}")

except ImportError:
    print("CuPy instalado: No")
    print("Para activar soporte GPU, instala cupy-cudaXX (donde XX es tu versión de CUDA).")
    print("Ejemplo: pip install cupy-cuda12x")

import numpy
print(f"NumPy instalado: Sí (Versión: {numpy.__version__})")
