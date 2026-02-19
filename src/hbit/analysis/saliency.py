"""
Mapeo de saliencia visual para el protocolo H-Bit.

Contribución Senior 1.1: Identifica las zonas donde el ojo humano se
enfoca más (puntos de interés) y combina con análisis de entropía para
generar un mapa de densidad perceptual.

La firma H-Bit es más densa en zonas de alta textura y más tenue en
degradados suaves (como cielos), donde el LSB es más propenso a
generar banding visible.

Integra el modelo de respuesta visual humana (Ley de Weber-Fechner)
para ajustar la fuerza de incrustación.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from hbit.analysis.entropy import generate_density_map


def compute_saliency_map(image_data: NDArray[np.uint8]) -> NDArray[np.float64]:
    """Calcula el mapa de saliencia visual de la imagen.

    Usa el método de Spectral Residual Saliency, una alternativa eficiente
    que no requiere deep learning. Detecta regiones que llaman la atención
    visual mediante análisis espectral (FFT).

    Algoritmo:
    1. Convertir a escala de grises
    2. Calcular FFT 2D
    3. Computar log-spectrum
    4. Obtener spectral residual = log_spectrum - mean_filtered(log_spectrum)
    5. Reconstruir con IFFT → mapa de saliencia

    Args:
        image_data: Array 3D de la imagen (H, W, 3) en formato RGB.

    Returns:
        Array 2D normalizado (0.0 a 1.0) donde valores altos = alta saliencia.
    """
    # Convertir a escala de grises (luminancia perceptual)
    gray = (
        0.2126 * image_data[:, :, 0].astype(np.float64)
        + 0.7152 * image_data[:, :, 1].astype(np.float64)
        + 0.0722 * image_data[:, :, 2].astype(np.float64)
    )

    # FFT 2D
    fft_result = np.fft.fft2(gray)
    log_amplitude = np.log(np.abs(fft_result) + 1e-10)
    phase = np.angle(fft_result)

    # Spectral residual: diferencia entre log-spectrum y su media local
    # Usamos un kernel de promediado 3×3 implementado con convolución
    kernel_size = 3
    kernel = np.ones((kernel_size, kernel_size)) / (kernel_size ** 2)
    mean_log_amplitude = _convolve2d_simple(log_amplitude, kernel)
    spectral_residual = log_amplitude - mean_log_amplitude

    # Reconstruir con el spectral residual
    saliency_fft = np.exp(spectral_residual) * np.exp(1j * phase)
    saliency_map = np.abs(np.fft.ifft2(saliency_fft)) ** 2

    # Suavizar con Gaussiana para eliminar ruido alto-frecuencia
    saliency_map = _gaussian_blur(saliency_map, sigma=8.0)

    # Normalizar al rango [0, 1]
    saliency_min = saliency_map.min()
    saliency_max = saliency_map.max()
    if saliency_max > saliency_min:
        saliency_map = (saliency_map - saliency_min) / (saliency_max - saliency_min)
    else:
        saliency_map = np.zeros_like(saliency_map)

    return saliency_map


def compute_weber_fechner_threshold(
    image_data: NDArray[np.uint8],
    channel: int = 2,
    block_size: int = 8,
) -> NDArray[np.float64]:
    """Calcula el umbral de Weber-Fechner por bloque.

    La Ley de Weber-Fechner establece que la diferencia apenas
    perceptible (JND) es proporcional a la intensidad del estímulo:
    ΔI / I = k (constante de Weber)

    En zonas oscuras (I bajo), incluso un cambio de 1 en el LSB
    puede ser perceptible. En zonas brillantes, el cambio es invisible.

    Args:
        image_data: Array 3D de la imagen (H, W, 3).
        channel: Canal a analizar (0=R, 1=G, 2=B).
        block_size: Tamaño de bloque en píxeles.

    Returns:
        Array 2D con el umbral de Weber por bloque (0.0 a 1.0).
        Valores altos = más tolerancia a modificación.
    """
    channel_data = image_data[:, :, channel].astype(np.float64)
    height, width = channel_data.shape

    block_rows = height // block_size
    block_cols = width // block_size

    threshold_map = np.zeros((block_rows, block_cols), dtype=np.float64)

    # Constante de Weber para el sistema visual humano (~0.02 para luminancia)
    weber_constant = 0.02

    for row in range(block_rows):
        for col in range(block_cols):
            block = channel_data[
                row * block_size:(row + 1) * block_size,
                col * block_size:(col + 1) * block_size,
            ]
            mean_intensity = block.mean()

            # JND = k * I (Weber-Fechner)
            # Normalizado: a mayor intensidad, mayor tolerancia
            if mean_intensity > 0:
                jnd = weber_constant * mean_intensity
                # Normalizar respecto al máximo posible (255 * k)
                threshold_map[row, col] = jnd / (weber_constant * 255.0)
            else:
                threshold_map[row, col] = 0.0

    return threshold_map


def generate_perceptual_density_map(
    image_data: NDArray[np.uint8],
    channel: int = 2,
    block_size: int = 8,
    saliency_weight: float = 0.3,
    entropy_weight: float = 0.4,
    weber_weight: float = 0.3,
) -> NDArray[np.float64]:
    """Genera un mapa de densidad perceptual combinando múltiples factores.

    Combina tres señales para determinar cuántos bits de firma puede
    soportar cada bloque sin degradación visual perceptible:

    1. Entropía/Varianza: Alta varianza → más capacidad de ocultación
    2. Saliencia: Baja saliencia → zona ignorada por el ojo → más seguro
    3. Weber-Fechner: Alta intensidad → más tolerancia a cambios

    density = w1 * entropy_norm + w2 * (1 - saliency_norm) + w3 * weber_norm

    Args:
        image_data: Array 3D de la imagen (H, W, 3).
        channel: Canal a utilizar.
        block_size: Tamaño de bloque.
        saliency_weight: Peso del factor de saliencia (0.0 a 1.0).
        entropy_weight: Peso del factor de entropía.
        weber_weight: Peso del factor de Weber-Fechner.

    Returns:
        Array 2D con densidad perceptual por bloque (0.0 a 1.0).
        Valores altos = más bits de firma en este bloque.
    """
    # Normalizar pesos
    total_weight = saliency_weight + entropy_weight + weber_weight
    saliency_weight /= total_weight
    entropy_weight /= total_weight
    weber_weight /= total_weight

    # Componente 1: Mapa de densidad por varianza (entropía)
    entropy_density = generate_density_map(image_data, channel, block_size)

    # Componente 2: Saliencia visual (invertida: baja saliencia = más seguro)
    full_saliency = compute_saliency_map(image_data)
    saliency_blocks = _downsample_to_blocks(full_saliency, block_size)
    saliency_inverted = 1.0 - saliency_blocks

    # Componente 3: Umbral de Weber-Fechner
    weber_threshold = compute_weber_fechner_threshold(image_data, channel, block_size)

    # Asegurar dimensiones iguales
    min_rows = min(entropy_density.shape[0], saliency_inverted.shape[0], weber_threshold.shape[0])
    min_cols = min(entropy_density.shape[1], saliency_inverted.shape[1], weber_threshold.shape[1])

    entropy_density = entropy_density[:min_rows, :min_cols]
    saliency_inverted = saliency_inverted[:min_rows, :min_cols]
    weber_threshold = weber_threshold[:min_rows, :min_cols]

    # Combinación ponderada
    perceptual_density = (
        entropy_weight * entropy_density
        + saliency_weight * saliency_inverted
        + weber_weight * weber_threshold
    )

    # Aplicar umbral mínimo: ningún bloque con densidad < 0.1
    # para garantizar al menos una copia del payload
    perceptual_density = np.clip(perceptual_density, 0.1, 1.0)

    return perceptual_density


def _downsample_to_blocks(
    full_map: NDArray[np.float64],
    block_size: int,
) -> NDArray[np.float64]:
    """Reduce un mapa de píxeles a un mapa de bloques por promediado.

    Args:
        full_map: Mapa de tamaño completo (H, W).
        block_size: Tamaño de bloque para reducción.

    Returns:
        Mapa reducido (H // block_size, W // block_size).
    """
    height, width = full_map.shape
    block_rows = height // block_size
    block_cols = width // block_size

    trimmed = full_map[:block_rows * block_size, :block_cols * block_size]
    blocks = trimmed.reshape(block_rows, block_size, block_cols, block_size)

    return blocks.mean(axis=(1, 3))


def _convolve2d_simple(
    data: NDArray[np.float64],
    kernel: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Convolución 2D simple sin dependencias externas.

    Args:
        data: Array 2D de entrada.
        kernel: Kernel de convolución.

    Returns:
        Array 2D convolucionado (mismo tamaño que data, con padding).
    """
    from scipy.ndimage import uniform_filter
    kernel_size = kernel.shape[0]
    return uniform_filter(data, size=kernel_size, mode="reflect")


def _gaussian_blur(
    data: NDArray[np.float64],
    sigma: float = 4.0,
) -> NDArray[np.float64]:
    """Aplica desenfoque Gaussiano.

    Args:
        data: Array 2D de entrada.
        sigma: Desviación estándar del kernel Gaussiano.

    Returns:
        Array 2D suavizado.
    """
    from scipy.ndimage import gaussian_filter
    return gaussian_filter(data, sigma=sigma)
