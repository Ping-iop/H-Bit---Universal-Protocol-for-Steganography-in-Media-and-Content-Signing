"""
De-warping y corrección geométrica del protocolo H-Bit.

Usa la rejilla de anclaje (anchor_grid) para corregir distorsiones
geométricas antes de intentar leer la firma. Permite extraer el
H-Bit de fotos de fotos, capturas de pantalla o imágenes dobladas.

Hito 2.3: Permite extracción desde fotos de soportes dañados.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from dataclasses import dataclass
from typing import Optional

from hbit.resilience.anchor_grid import detect_anchor_grid


@dataclass(frozen=True)
class DewarpResult:
    """Resultado de la corrección geométrica.

    Attributes:
        corrected_image: Imagen corregida.
        transform_applied: Matriz de transformación inversa aplicada.
        distortion_detected: Si se detectó distorsión significativa.
        anchor_detection_rate: Tasa de detección de anchors.
    """

    corrected_image: NDArray[np.uint8]
    transform_applied: NDArray[np.float64]
    distortion_detected: bool
    anchor_detection_rate: float


def dewarp_image(
    image_data: NDArray[np.uint8],
    channel: int = 2,
    grid_spacing: int = 8,
    distortion_threshold: float = 2.0,
) -> DewarpResult:
    """Corrige distorsiones geométricas de una imagen usando anchor grid.

    Proceso:
    1. Detectar anchor points en la imagen distorsionada
    2. Comparar posiciones detectadas con las esperadas
    3. Estimar transformación afín inversa
    4. Aplicar la transformación para rectificar la imagen

    Args:
        image_data: Array 3D (H, W, 3) de la imagen distorsionada.
        channel: Canal donde buscar anchors.
        grid_spacing: Espaciado esperado de la rejilla.
        distortion_threshold: Umbral de desplazamiento medio (px) para
                              considerar que hay distorsión significativa.

    Returns:
        DewarpResult con la imagen corregida.
    """
    # 1. Detectar anchors
    detection = detect_anchor_grid(
        image_data, channel, grid_spacing,
    )

    if detection.detection_rate < 0.1:
        # Muy pocos anchors detectados — no se puede corregir
        return DewarpResult(
            corrected_image=image_data.copy(),
            transform_applied=np.eye(3),
            distortion_detected=False,
            anchor_detection_rate=detection.detection_rate,
        )

    # 2. Verificar si hay distorsión significativa
    transform = detection.transform_matrix
    # La distorsión se mide como la desviación de la identidad
    identity_deviation = np.abs(transform - np.eye(3)).sum()

    if identity_deviation < 0.01:
        # Sin distorsión significativa
        return DewarpResult(
            corrected_image=image_data.copy(),
            transform_applied=np.eye(3),
            distortion_detected=False,
            anchor_detection_rate=detection.detection_rate,
        )

    # 3. Calcular transformación inversa
    try:
        inverse_transform = np.linalg.inv(transform)
    except np.linalg.LinAlgError:
        return DewarpResult(
            corrected_image=image_data.copy(),
            transform_applied=np.eye(3),
            distortion_detected=True,
            anchor_detection_rate=detection.detection_rate,
        )

    # 4. Aplicar transformación afín inversa
    corrected = _apply_affine_transform(image_data, inverse_transform)

    return DewarpResult(
        corrected_image=corrected,
        transform_applied=inverse_transform,
        distortion_detected=True,
        anchor_detection_rate=detection.detection_rate,
    )


def _apply_affine_transform(
    image_data: NDArray[np.uint8],
    transform: NDArray[np.float64],
) -> NDArray[np.uint8]:
    """Aplica una transformación afín inversa a la imagen.

    Usa mapeo inverso con interpolación bilineal para evitar
    agujeros en la imagen transformada.

    Args:
        image_data: Array 3D (H, W, 3) de la imagen.
        transform: Matriz de transformación afín 3×3.

    Returns:
        Imagen transformada.
    """
    height, width, channels = image_data.shape
    result = np.zeros_like(image_data)

    # Extraer componentes de la transformación
    a, b, tx = transform[0, 0], transform[0, 1], transform[0, 2]
    c, d, ty = transform[1, 0], transform[1, 1], transform[1, 2]

    for y in range(height):
        for x in range(width):
            # Mapeo inverso: obtener coordenada fuente
            src_y = a * y + b * x + tx
            src_x = c * y + d * x + ty

            # Interpolación bilineal
            sy0 = int(np.floor(src_y))
            sx0 = int(np.floor(src_x))
            sy1 = sy0 + 1
            sx1 = sx0 + 1

            if 0 <= sy0 < height - 1 and 0 <= sx0 < width - 1:
                fy = src_y - sy0
                fx = src_x - sx0

                for ch in range(channels):
                    val = (
                        (1 - fy) * (1 - fx) * image_data[sy0, sx0, ch]
                        + (1 - fy) * fx * image_data[sy0, sx1, ch]
                        + fy * (1 - fx) * image_data[sy1, sx0, ch]
                        + fy * fx * image_data[sy1, sx1, ch]
                    )
                    result[y, x, ch] = np.clip(val, 0, 255)

    return result.astype(np.uint8)


def denoise_for_extraction(
    image_data: NDArray[np.uint8],
    strength: float = 3.0,
) -> NDArray[np.uint8]:
    """Aplica denoising adaptativo para mejorar la extracción de firma.

    Reduce el ruido introducido por la captura (foto de foto,
    captura de pantalla) mientras preserva las modificaciones LSB.

    Args:
        image_data: Imagen ruidosa.
        strength: Fuerza del denoising.

    Returns:
        Imagen con ruido reducido.
    """
    from scipy.ndimage import median_filter

    result = image_data.copy()

    # Aplicar filtro de mediana suave (3×3) por canal
    # El filtro de mediana preserva bordes y es bueno para ruido salt-and-pepper
    kernel_size = max(3, int(strength))
    if kernel_size % 2 == 0:
        kernel_size += 1  # Debe ser impar

    for ch in range(result.shape[2]):
        result[:, :, ch] = median_filter(result[:, :, ch], size=kernel_size)

    return result
