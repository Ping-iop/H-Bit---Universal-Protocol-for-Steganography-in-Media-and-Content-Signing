"""
Auditoría de Coherencia Lumínica del protocolo H-Bit.

Contribución Senior 4.2: Analiza la consistencia de la iluminación
en la imagen para detectar composiciones (photoshop) y manipulaciones.

Si una imagen ha sido manipulada insertando elementos de otras fotos,
la dirección e intensidad de la luz en las zonas manipuladas será
inconsistente con el resto de la imagen.

El módulo analiza:
1. Dirección principal de la luz por región
2. Gradientes de sombra
3. Consistencia de reflejos especulares

Si la imagen tiene un H-Bit válido pero la coherencia lumínica falla,
la imagen probablemente fue manipulada DESPUÉS de la firma.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy.ndimage import sobel, uniform_filter
from dataclasses import dataclass


@dataclass(frozen=True)
class LightAnalysis:
    """Resultado del análisis de coherencia lumínica.

    Attributes:
        is_consistent: Si la iluminación es consistente.
        consistency_score: Puntuación de consistencia (0.0 a 1.0).
        dominant_direction: Dirección dominante de la luz (grados).
        regional_directions: Direcciones por región (para visualización).
        anomalous_regions: Regiones con iluminación inconsistente.
    """

    is_consistent: bool
    consistency_score: float
    dominant_direction: float
    regional_directions: NDArray[np.float64]
    anomalous_regions: list[tuple[int, int, int, int]]


def analyze_light_coherence(
    image_data: NDArray[np.uint8],
    grid_size: int = 4,
    consistency_threshold: float = 0.6,
) -> LightAnalysis:
    """Analiza la coherencia de iluminación de la imagen.

    Divide la imagen en una rejilla y calcula la dirección dominante
    de la luz en cada celda usando gradientes de intensidad.

    La dirección de la luz se estima a partir del gradiente de luminancia:
    las zonas más brillantes indican de dónde viene la luz.

    Args:
        image_data: Array 3D (H, W, 3) de la imagen RGB.
        grid_size: Número de celdas por dimensión.
        consistency_threshold: Umbral para considerar consistente.

    Returns:
        LightAnalysis con el resultado.
    """
    # Convertir a luminancia (grayscale perceptual)
    luminance = (
        0.2126 * image_data[:, :, 0].astype(np.float64)
        + 0.7152 * image_data[:, :, 1].astype(np.float64)
        + 0.0722 * image_data[:, :, 2].astype(np.float64)
    )

    height, width = luminance.shape
    cell_h = height // grid_size
    cell_w = width // grid_size

    # Calcular dirección de luz por celda
    regional_directions = np.zeros((grid_size, grid_size), dtype=np.float64)
    regional_magnitudes = np.zeros((grid_size, grid_size), dtype=np.float64)

    for row in range(grid_size):
        for col in range(grid_size):
            y0 = row * cell_h
            y1 = (row + 1) * cell_h
            x0 = col * cell_w
            x1 = (col + 1) * cell_w

            cell = luminance[y0:y1, x0:x1]

            # Gradientes de Sobel
            grad_x = sobel(cell, axis=1)
            grad_y = sobel(cell, axis=0)

            # Dirección media del gradiente (≈ dirección opuesta a la luz)
            mean_gx = np.mean(grad_x)
            mean_gy = np.mean(grad_y)

            direction = np.arctan2(mean_gy, mean_gx) * 180 / np.pi
            magnitude = np.sqrt(mean_gx ** 2 + mean_gy ** 2)

            regional_directions[row, col] = direction
            regional_magnitudes[row, col] = magnitude

    # Dirección dominante (media ponderada por magnitud)
    weights = regional_magnitudes / (np.sum(regional_magnitudes) + 1e-10)
    
    # Para promediar ángulos correctamente, usar componentes vectoriales
    mean_x = np.sum(weights * np.cos(regional_directions * np.pi / 180))
    mean_y = np.sum(weights * np.sin(regional_directions * np.pi / 180))
    dominant_direction = np.arctan2(mean_y, mean_x) * 180 / np.pi

    # Calcular desviación de cada celda respecto a la media
    anomalous_regions = []
    deviations = []

    for row in range(grid_size):
        for col in range(grid_size):
            # Solo considerar celdas con magnitud significativa
            if regional_magnitudes[row, col] < np.median(regional_magnitudes) * 0.1:
                continue

            # Diferencia angular (circular)
            diff = abs(regional_directions[row, col] - dominant_direction)
            diff = min(diff, 360 - diff)  # Distancia circular
            deviations.append(diff)

            # Si la desviación es > 60°, marcar como anómala
            if diff > 60:
                y0 = row * cell_h
                x0 = col * cell_w
                anomalous_regions.append((x0, y0, cell_w, cell_h))

    # Puntuación de consistencia
    if deviations:
        mean_deviation = np.mean(deviations)
        # 0° = perfectamente consistente, 90° = totalmente inconsistente
        consistency_score = max(0.0, 1.0 - mean_deviation / 90.0)
    else:
        consistency_score = 0.5

    return LightAnalysis(
        is_consistent=bool(consistency_score >= consistency_threshold),
        consistency_score=float(consistency_score),
        dominant_direction=float(dominant_direction),
        regional_directions=regional_directions,
        anomalous_regions=anomalous_regions,
    )


def analyze_shadow_gradients(
    image_data: NDArray[np.uint8],
    shadow_threshold: float = 50.0,
) -> dict:
    """Analiza la consistencia de gradientes de sombra.

    Las sombras en una imagen natural tienen gradientes suaves
    y direcciones consistentes. Las composiciones a menudo tienen
    sombras con bordes artificiales o direcciones inconsistentes.

    Args:
        image_data: Imagen RGB.
        shadow_threshold: Umbral de luminancia para detectar sombras.

    Returns:
        Dict con métricas de sombra.
    """
    luminance = (
        0.2126 * image_data[:, :, 0].astype(np.float64)
        + 0.7152 * image_data[:, :, 1].astype(np.float64)
        + 0.0722 * image_data[:, :, 2].astype(np.float64)
    )

    # Detectar regiones de sombra
    shadow_mask = luminance < shadow_threshold

    # Calcular gradientes en los bordes de las sombras
    grad_x = sobel(luminance, axis=1)
    grad_y = sobel(luminance, axis=0)
    gradient_magnitude = np.sqrt(grad_x ** 2 + grad_y ** 2)

    # Los bordes de sombra naturales tienen gradientes suaves
    shadow_edges = shadow_mask & (gradient_magnitude > np.percentile(gradient_magnitude, 75))

    # Suavidad de los bordes de sombra
    if np.sum(shadow_edges) > 0:
        # Gradiente medio en los bordes de sombra
        edge_gradient = gradient_magnitude[shadow_edges].mean()
        # Gradiente medio general
        overall_gradient = gradient_magnitude[gradient_magnitude > 0].mean()
        # Las sombras naturales tienen bordes más suaves que los bordes generales
        shadow_softness = 1.0 - min(1.0, edge_gradient / (overall_gradient + 1e-10))
    else:
        shadow_softness = 1.0  # No hay sombras detectables

    return {
        "shadow_coverage": float(np.mean(shadow_mask)),
        "shadow_softness": float(shadow_softness),
        "edge_count": int(np.sum(shadow_edges)),
        "is_natural": shadow_softness > 0.3,
    }
