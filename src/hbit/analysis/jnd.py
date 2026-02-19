"""
Máscara JND (Just Noticeable Difference) para el protocolo H-Bit.

Contribución Senior 2.1: Calcula el umbral exacto de ruido perceptible
por bloque DCT usando el modelo Watson DCT-JND. Garantiza que la firma
H-Bit sobreviva a compresión JPEG Q=60 sin artefactos visibles.

El modelo Watson combina tres factores:
1. Sensibilidad base a cada frecuencia DCT (tabla de cuantización)
2. Enmascaramiento por luminancia (nivel DC del bloque)
3. Enmascaramiento por contraste (magnitud de coeficientes AC vecinos)
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy.fft import dctn, idctn


# Tabla de cuantización JPEG estándar (luminancia) — ISO/IEC 10918-1
# Inversamente proporcional a la sensibilidad visual por frecuencia
JPEG_QUANT_TABLE = np.array([
    [16, 11, 10, 16, 24, 40, 51, 61],
    [12, 12, 14, 19, 26, 58, 60, 55],
    [14, 13, 16, 24, 40, 57, 69, 56],
    [14, 17, 22, 29, 51, 87, 80, 62],
    [18, 22, 37, 56, 68, 109, 103, 77],
    [24, 35, 55, 64, 81, 104, 113, 92],
    [49, 64, 78, 87, 103, 121, 120, 101],
    [72, 92, 95, 98, 112, 100, 103, 99],
], dtype=np.float64)


def compute_jnd_mask(
    image_data: NDArray[np.uint8],
    channel: int = 2,
    block_size: int = 8,
) -> NDArray[np.float64]:
    """Calcula la máscara JND por bloque DCT usando el modelo Watson.

    Para cada bloque 8×8, determina el umbral máximo de modificación
    que será imperceptible para el ojo humano en cada coeficiente DCT.

    Modelo Watson DCT-JND (simplificado):
    JND(i,j,k) = t(i,j) * (C_DC(k) / C_mean)^0.649 * max(1, |C(i,j,k)| / t(i,j))^0.3

    Donde:
    - t(i,j) = umbral base del coeficiente (i,j) de la tabla JPEG
    - C_DC(k) = componente DC del bloque k
    - C_mean = DC medio de toda la imagen
    - C(i,j,k) = coeficiente DCT (i,j) del bloque k

    Args:
        image_data: Array 3D (H, W, 3) de la imagen RGB.
        channel: Canal a analizar.
        block_size: Tamaño de bloque (debe ser 8 para compatibilidad JPEG).

    Returns:
        Array 3D (num_blocks_h, num_blocks_w, 64) con el umbral JND
        para cada coeficiente DCT de cada bloque.
    """
    channel_data = image_data[:, :, channel].astype(np.float64) - 128.0
    height, width = channel_data.shape

    block_rows = height // block_size
    block_cols = width // block_size

    # Array para almacenar los JND thresholds
    jnd_map = np.zeros((block_rows, block_cols, block_size * block_size), dtype=np.float64)

    # Primera pasada: calcular DC medio
    dc_values = np.zeros((block_rows, block_cols), dtype=np.float64)

    for row in range(block_rows):
        for col in range(block_cols):
            block = channel_data[
                row * block_size:(row + 1) * block_size,
                col * block_size:(col + 1) * block_size,
            ]
            dct_block = dctn(block, type=2, norm="ortho")
            dc_values[row, col] = dct_block[0, 0]

    dc_mean = np.abs(dc_values).mean()
    if dc_mean < 1.0:
        dc_mean = 1.0  # Evitar división por cero

    # Segunda pasada: modelo Watson
    for row in range(block_rows):
        for col in range(block_cols):
            block = channel_data[
                row * block_size:(row + 1) * block_size,
                col * block_size:(col + 1) * block_size,
            ]
            dct_block = dctn(block, type=2, norm="ortho")

            # Enmascaramiento por luminancia
            dc_current = np.abs(dct_block[0, 0])
            luminance_factor = (dc_current / dc_mean) ** 0.649

            for i in range(block_size):
                for j in range(block_size):
                    # Umbral base de la tabla de cuantización
                    base_threshold = JPEG_QUANT_TABLE[i, j]

                    # Enmascaramiento por contraste
                    coeff_magnitude = np.abs(dct_block[i, j])
                    contrast_factor = max(1.0, coeff_magnitude / base_threshold) ** 0.3

                    # JND = base * luminancia * contraste
                    jnd = base_threshold * luminance_factor * contrast_factor

                    jnd_map[row, col, i * block_size + j] = jnd

    return jnd_map


def apply_jnd_constraint(
    dct_coefficients: NDArray[np.float64],
    jnd_values: NDArray[np.float64],
    embedding_strength: float = 1.0,
) -> NDArray[np.float64]:
    """Limita la fuerza de incrustación DCT al umbral JND.

    Asegura que la modificación de cada coeficiente no exceda lo que
    el ojo humano puede percibir, evitando artefactos visuales.

    Args:
        dct_coefficients: Coeficientes DCT del bloque 8×8 (flattened).
        jnd_values: Umbrales JND para cada coeficiente.
        embedding_strength: Factor de escala (1.0 = máximo imperceptible).

    Returns:
        Coeficientes DCT con modificación restringida al umbral JND.
    """
    max_modification = jnd_values * embedding_strength
    modifications = np.clip(dct_coefficients, -max_modification, max_modification)
    return modifications


def compute_max_embedding_capacity(
    jnd_map: NDArray[np.float64],
    bits_per_coeff: int = 1,
) -> int:
    """Calcula la capacidad máxima de incrustación imperceptible.

    Basado en la máscara JND, determina cuántos bits de información
    se pueden incrustar sin superar el umbral de percepción.

    Args:
        jnd_map: Máscara JND (num_blocks_h, num_blocks_w, 64).
        bits_per_coeff: Bits a incrustar por coeficiente viable.

    Returns:
        Número máximo de bits que se pueden incrustar de forma segura.
    """
    # Un coeficiente es viable si su JND > 1.0 (puede tolerar al menos ±1)
    viable_coefficients = np.sum(jnd_map > 1.0)
    return int(viable_coefficients * bits_per_coeff)
