"""
Rejilla de sincronización invisible (Anchor Grid) del protocolo H-Bit.

Contribución Senior 2.2: Red de puntos de referencia esteganográficos
basados en patrones de frecuencia piloto (similar a OFDM en telecomunicaciones).

Si la foto se dobla, arruga o sufre distorsión geométrica, la rejilla
de anclaje permite reconstruir la geometría original antes de leer los bits
de la firma.

El concepto es análogo a los pilotos OFDM: señales conocidas incrustadas
en posiciones predefinidas que permiten estimar y corregir la distorsión
del canal de transmisión.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy.fft import dctn, idctn
from dataclasses import dataclass


# Frecuencia piloto para los anchor points (ciclos/bloque)
# Se elige una frecuencia específica que sea robusta a compresión
# pero detectable mediante correlación espectral.
ANCHOR_FREQUENCY = 3  # 3 ciclos en 8 píxeles

# Fuerza de los anchor points (se modula con JND si disponible)
DEFAULT_ANCHOR_STRENGTH = 15.0


@dataclass(frozen=True)
class AnchorGrid:
    """Rejilla de puntos de anclaje.

    Attributes:
        grid_points: Array (N, 2) con las posiciones esperadas de los anchors.
        grid_spacing: Espaciado entre anchors (en bloques).
        grid_rows: Número de filas de la rejilla.
        grid_cols: Número de columnas de la rejilla.
    """

    grid_points: NDArray[np.float64]
    grid_spacing: int
    grid_rows: int
    grid_cols: int


@dataclass(frozen=True)
class DetectedAnchors:
    """Resultado de la detección de anchor points.

    Attributes:
        detected_points: Array (N, 2) con las posiciones detectadas.
        expected_points: Array (N, 2) con las posiciones esperadas.
        detection_rate: Proporción de anchors detectados (0.0 a 1.0).
        transform_matrix: Matriz de transformación afín estimada (3×3).
    """

    detected_points: NDArray[np.float64]
    expected_points: NDArray[np.float64]
    detection_rate: float
    transform_matrix: NDArray[np.float64]


def compute_anchor_grid(
    image_height: int,
    image_width: int,
    grid_spacing: int = 8,
    block_size: int = 8,
) -> AnchorGrid:
    """Calcula las posiciones de la rejilla de anclaje.

    La rejilla se distribuye uniformemente por la imagen con el
    espaciado especificado (en número de bloques 8×8 entre anchors).

    Args:
        image_height: Altura de la imagen en píxeles.
        image_width: Ancho de la imagen en píxeles.
        grid_spacing: Espaciado entre anchors (en bloques 8×8).
        block_size: Tamaño del bloque base.

    Returns:
        AnchorGrid con las posiciones calculadas.
    """
    block_rows = image_height // block_size
    block_cols = image_width // block_size

    grid_rows = max(1, block_rows // grid_spacing)
    grid_cols = max(1, block_cols // grid_spacing)

    points = []
    for row in range(grid_rows):
        for col in range(grid_cols):
            # Posición central del anchor (en píxeles)
            py = (row * grid_spacing + grid_spacing // 2) * block_size
            px = (col * grid_spacing + grid_spacing // 2) * block_size

            if py + block_size <= image_height and px + block_size <= image_width:
                points.append([py, px])

    return AnchorGrid(
        grid_points=np.array(points, dtype=np.float64),
        grid_spacing=grid_spacing,
        grid_rows=grid_rows,
        grid_cols=grid_cols,
    )


def inject_anchor_grid(
    image_data: NDArray[np.uint8],
    channel: int = 2,
    grid_spacing: int = 8,
    strength: float = DEFAULT_ANCHOR_STRENGTH,
) -> NDArray[np.uint8]:
    """Inyecta la rejilla de anchor points invisible en la imagen.

    Cada anchor point consiste en un patrón sinusoidal de frecuencia
    conocida incrustado en el dominio DCT de un bloque. La detección
    se realiza buscando picos en esa frecuencia específica.

    Algoritmo:
    1. Calcular posiciones de la rejilla
    2. Para cada posición:
       a. Extraer bloque 8×8
       b. Calcular DCT
       c. Inyectar pico en la frecuencia piloto
       d. Reconstruir con IDCT

    Args:
        image_data: Array 3D (H, W, 3) de la imagen RGB.
        channel: Canal donde inyectar los anchors.
        grid_spacing: Espaciado entre anchors (bloques).
        strength: Fuerza del patrón piloto.

    Returns:
        Imagen con la rejilla de anclaje inyectada.
    """
    result = image_data.copy()
    height, width = result.shape[:2]
    block_size = 8

    grid = compute_anchor_grid(height, width, grid_spacing, block_size)

    channel_data = result[:, :, channel].astype(np.float64) - 128.0

    for point in grid.grid_points:
        py, px = int(point[0]), int(point[1])

        if py + block_size > height or px + block_size > width:
            continue

        # Extraer bloque
        block = channel_data[py:py + block_size, px:px + block_size].copy()

        # DCT
        dct_block = dctn(block, type=2, norm="ortho")

        # Inyectar señal piloto en la frecuencia ANCHOR_FREQUENCY
        # Se usa un patrón diagonal para mejor detección
        af = ANCHOR_FREQUENCY
        dct_block[af, 0] += strength
        dct_block[0, af] += strength

        # IDCT
        reconstructed = idctn(dct_block, type=2, norm="ortho")
        channel_data[py:py + block_size, px:px + block_size] = reconstructed

    # Reconstruir imagen
    result[:, :, channel] = np.clip(channel_data + 128.0, 0, 255).astype(np.uint8)

    return result


def detect_anchor_grid(
    image_data: NDArray[np.uint8],
    channel: int = 2,
    grid_spacing: int = 8,
    detection_threshold: float = 5.0,
) -> DetectedAnchors:
    """Detecta los anchor points en una imagen (posiblemente distorsionada).

    Busca picos de energía en la frecuencia piloto en cada bloque
    de la imagen. Los puntos detectados se comparan con la rejilla
    esperada para estimar la transformación geométrica.

    Args:
        image_data: Array 3D (H, W, 3) de la imagen.
        channel: Canal donde buscar.
        grid_spacing: Espaciado esperado de la rejilla.
        detection_threshold: Umbral de energía para detección.

    Returns:
        DetectedAnchors con los puntos encontrados y la transformación.
    """
    height, width = image_data.shape[:2]
    block_size = 8

    channel_data = image_data[:, :, channel].astype(np.float64) - 128.0

    block_rows = height // block_size
    block_cols = width // block_size

    # Escanear todos los bloques buscando la señal piloto
    detected_points = []
    af = ANCHOR_FREQUENCY

    for row in range(block_rows):
        for col in range(block_cols):
            py = row * block_size
            px = col * block_size

            block = channel_data[py:py + block_size, px:px + block_size]
            dct_block = dctn(block, type=2, norm="ortho")

            # Medir energía en la frecuencia piloto
            pilot_energy = abs(dct_block[af, 0]) + abs(dct_block[0, af])

            # Media de otras frecuencias para comparar
            other_energy = np.abs(dct_block).mean()

            if pilot_energy > detection_threshold * other_energy:
                # Anchor detectado en el centro del bloque
                center_y = py + block_size // 2
                center_x = px + block_size // 2
                detected_points.append([center_y, center_x])

    detected_array = np.array(detected_points, dtype=np.float64) if detected_points else np.zeros((0, 2))

    # Rejilla esperada
    expected_grid = compute_anchor_grid(height, width, grid_spacing, block_size)
    expected_points = expected_grid.grid_points

    # Tasa de detección
    expected_count = len(expected_points)
    detected_count = len(detected_array)
    detection_rate = detected_count / max(1, expected_count)

    # Estimar transformación afín (solo si hay suficientes detecciones)
    transform = np.eye(3, dtype=np.float64)

    if detected_count >= 3 and expected_count >= 3:
        transform = _estimate_affine_transform(
            expected_points[:detected_count],
            detected_array[:expected_count] if detected_count <= expected_count else detected_array,
        )

    return DetectedAnchors(
        detected_points=detected_array,
        expected_points=expected_points,
        detection_rate=min(1.0, detection_rate),
        transform_matrix=transform,
    )


def _estimate_affine_transform(
    src_points: NDArray[np.float64],
    dst_points: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Estima una transformación afín entre dos conjuntos de puntos.

    Usa el método de mínimos cuadrados para encontrar la transformación
    que mejor mapea src_points a dst_points.

    Args:
        src_points: Puntos de referencia (N, 2).
        dst_points: Puntos detectados (N, 2).

    Returns:
        Matriz de transformación afín 3×3.
    """
    n = min(len(src_points), len(dst_points))
    if n < 3:
        return np.eye(3, dtype=np.float64)

    # Usar solo los primeros n puntos
    src = src_points[:n]
    dst = dst_points[:n]

    # Construir sistema de ecuaciones para transformación afín
    # [x'] = [a b tx] [x]
    # [y']   [c d ty] [y]
    # [1 ]   [0 0 1 ] [1]
    A = np.zeros((2 * n, 6), dtype=np.float64)
    b = np.zeros(2 * n, dtype=np.float64)

    for i in range(n):
        A[2 * i] = [src[i, 0], src[i, 1], 1, 0, 0, 0]
        A[2 * i + 1] = [0, 0, 0, src[i, 0], src[i, 1], 1]
        b[2 * i] = dst[i, 0]
        b[2 * i + 1] = dst[i, 1]

    # Resolver por mínimos cuadrados
    try:
        params, _, _, _ = np.linalg.lstsq(A, b, rcond=None)
        transform = np.array([
            [params[0], params[1], params[2]],
            [params[3], params[4], params[5]],
            [0, 0, 1],
        ], dtype=np.float64)
    except np.linalg.LinAlgError:
        transform = np.eye(3, dtype=np.float64)

    return transform
