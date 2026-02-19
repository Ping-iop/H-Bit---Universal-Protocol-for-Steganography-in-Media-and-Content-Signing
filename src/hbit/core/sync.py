"""
Módulo de sincronización del protocolo H-Bit.

Implementa marcadores de sincronización robustos basados en secuencias Barker
(usadas en telecomunicaciones) para delimitar el payload incrustado y permitir
su detección incluso con bits dañados mediante correlación cruzada.

Mejora sobre el prototipo original que usaba '10101010' como marcador.
Las secuencias Barker tienen propiedades de autocorrelación óptimas,
minimizando falsos positivos durante la búsqueda de sincronización.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


# ═══════════════════════════════════════════════════════════════════
# Secuencias Barker (óptimas para sincronización)
# ═══════════════════════════════════════════════════════════════════

# Secuencia Barker de 13 bits original
BARKER_13 = np.array([1, 1, 1, 1, 1, -1, -1, 1, 1, -1, 1, -1, 1], dtype=np.int8)

# Complemento de Barker 13 (negado)
# Usado para sincronización cuando search_header=False
BARKER_13_COMPLEMENT = -BARKER_13

# Secuencia compuesta para Header (39 bits): [B13, ~B13, B13]
# Esto aumenta drásticamente la resistencia a falsos positivos en datos aleatorios.
HEADER_PATTERN = np.concatenate([BARKER_13, -BARKER_13, BARKER_13])
HEADER_BINARY = ((HEADER_PATTERN + 1) // 2).astype(np.uint8)

# Secuencia compuesta para Footer (39 bits): [~B13, B13, ~B13]
FOOTER_PATTERN = np.concatenate([-BARKER_13, BARKER_13, -BARKER_13])
FOOTER_BINARY = ((FOOTER_PATTERN + 1) // 2).astype(np.uint8)


# Cadenas de texto para las secuencias
SYNC_HEADER_BITS = "".join(str(b) for b in HEADER_BINARY)
SYNC_FOOTER_BITS = "".join(str(b) for b in FOOTER_BINARY)

# Longitud de la secuencia en bits
SYNC_SEQUENCE_LENGTH = len(HEADER_PATTERN)  # 39 bits

from hbit.core.accelerator import xp, to_device, to_cpu

# ... (imports unchanged)

def correlate_barker(
    signal: NDArray[np.int8],
    pattern: NDArray[np.int8] = HEADER_PATTERN,
) -> NDArray[np.float64]:
    """Calcula la correlación cruzada normalizada entre la señal y el patrón Barker.
    OPTIMIZADO: Usa numpy/cupy.correlate (vectorizado y acelerado).
    """
    # Mover datos al dispositivo (CPU/GPU)
    # Convertir 0/1 a -1/+1 si es necesario
    if signal.min() >= 0:
        signal_dev = to_device(signal.astype(np.int8) * 2 - 1)
    else:
        signal_dev = to_device(signal)
        
    pattern_dev = to_device(pattern)

    pattern_len = len(pattern)
    signal_len = len(signal_dev)

    if signal_len < pattern_len:
        return np.array([], dtype=np.float64)

    # Correlación cruzada eficiente (modo 'valid' = solo solapamiento completo)
    # Resultado devuelto como float para precisión
    correlation = xp.correlate(signal_dev.astype(xp.float64), pattern_dev.astype(xp.float64), mode='valid')

    # Normalizar (resultado estará en rango -1.0 a 1.0)
    correlation = correlation / pattern_len
    
    # Devolver a CPU como numpy array
    return to_cpu(correlation)


def find_sync_positions(
    bit_stream: str | NDArray,
    threshold: float = 0.85,
    search_header: bool = True,
) -> list[int]:
    """Encuentra las posiciones del marcador de sincronización en un flujo de bits.

    Usa correlación cruzada para detectar el patrón incluso con bits dañados.
    Un threshold de 0.85 permite hasta ~2 bits erróneos en los 13 de la secuencia.

    Args:
        bit_stream: Cadena de bits ('0' y '1') o array numpy.
        threshold: Umbral de correlación normalizada (0.0 a 1.0).
                   0.85 ≈ tolera 2 bits erróneos de 13.
                   1.0 = coincidencia perfecta.
        search_header: True para buscar header, False para footer.

    Returns:
        Lista de posiciones (índices) donde se encontraron marcadores.
    """
    if isinstance(bit_stream, str):
        signal = np.array([int(b) for b in bit_stream], dtype=np.int8)
    else:
        signal = bit_stream.astype(np.int8)

    pattern = BARKER_13 if search_header else BARKER_13_COMPLEMENT
    correlation = correlate_barker(signal, pattern)

    # Encontrar posiciones por encima del umbral
    positions = np.where(correlation >= threshold)[0].tolist()

    return positions


def find_payload_boundaries(
    bit_stream: str | NDArray,
    threshold: float = 0.85,
) -> list[tuple[int, int]]:
    """Encuentra los límites de todos los payloads en el flujo de bits.

    Busca pares (header, footer) para delimitar cada copia del payload.
    Útil para la redundancia cíclica donde el payload se repite múltiples veces.

    Args:
        bit_stream: Cadena de bits completa.
        threshold: Umbral de correlación para detección.

    Returns:
        Lista de tuplas (inicio_payload, fin_payload) donde:
        - inicio_payload: posición del primer bit después del header
        - fin_payload: posición del último bit antes del footer
    """
    headers = find_sync_positions(bit_stream, threshold, search_header=True)
    footers = find_sync_positions(bit_stream, threshold, search_header=False)

    boundaries = []
    for header_pos in headers:
        payload_start = header_pos + SYNC_SEQUENCE_LENGTH
        # Buscar TODOS los footers válidos después de este header
        # Antes solo tomábamos el primero (valid_footers[0]), pero si hay un falso positivo
        # corto, perdíamos el real. Ahora devolvemos todas las combinaciones y dejamos
        # que el llamador filtre por longitud/validez.
        valid_footers = [f for f in footers if f > payload_start]
        for footer_pos in valid_footers:
            boundaries.append((payload_start, footer_pos))

    return boundaries


def wrap_payload_with_sync(payload_bits: str) -> str:
    """Envuelve un payload con marcadores de sincronización.

    Args:
        payload_bits: Cadena de bits del payload.

    Returns:
        Cadena con formato: [SYNC_HEADER][payload_bits][SYNC_FOOTER]
    """
    return SYNC_HEADER_BITS + payload_bits + SYNC_FOOTER_BITS


def compute_sync_unit_length(payload_bit_length: int) -> int:
    """Calcula la longitud total de una unidad de sincronización.

    Una unidad = HEADER + PAYLOAD + FOOTER

    Args:
        payload_bit_length: Longitud del payload en bits.

    Returns:
        Longitud total de la unidad en bits.
    """
    return SYNC_SEQUENCE_LENGTH + payload_bit_length + SYNC_SEQUENCE_LENGTH
