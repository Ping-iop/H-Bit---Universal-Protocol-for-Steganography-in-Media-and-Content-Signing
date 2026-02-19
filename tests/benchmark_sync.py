import sys
import os
import time
import numpy as np

# Añadir el directorio raíz al path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src')))

from hbit.core.sync import correlate_barker, BARKER_13
from hbit.core.accelerator import xp

def benchmark_correlation():
    print(f"Backend en uso: {xp.__name__}")
    
    # Crear una señal larga (ej: 1 millón de bits, aprox un archivo de 125KB)
    signal_len = 1_000_000
    print(f"Generando señal de prueba de {signal_len} bits...")
    signal = np.random.randint(0, 2, signal_len).astype(np.int8)
    
    # Patrón a buscar
    pattern = BARKER_13
    
    # Medir tiempo
    start_time = time.time()
    result = correlate_barker(signal, pattern)
    end_time = time.time()
    
    duration = end_time - start_time
    print(f"Tiempo de ejecución: {duration:.4f} segundos")
    print(f"Velocidad: {signal_len / duration / 1_000_000:.2f} Mbits/s")
    
    # Verificación básica de forma
    expected_len = signal_len - len(pattern) * 3 + 1 # HEADER_PATTERN es len(BARKER)*3
    # Actually HEADER_PATTERN is used by default in correlate_barker.
    # Its length is 39. So loop logic was valid len.
    # xp.correlate 'valid' mode output size: N - M + 1. 
    # Let's check result shape.
    print(f"Forma del resultado: {result.shape}")

if __name__ == "__main__":
    benchmark_correlation()
