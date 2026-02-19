"""
Análisis de entropía por canal de imagen.

Calcula la entropía Shannon de cada canal de color (R, G, B) para
determinar en qué canal la firma esteganográfica será menos detectable.
También genera mapas de densidad por bloques para la redundancia adaptativa.

Hito 1.1: Redundancia espacial dinámica
Hito 1.2: Selección de canal inteligente
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from dataclasses import dataclass


@dataclass(frozen=True)
class ChannelEntropy:
    """Resultado del análisis de entropía por canal.

    Attributes:
        red: Entropía Shannon del canal rojo (0.0 a 8.0 bits).
        green: Entropía Shannon del canal verde.
        blue: Entropía Shannon del canal azul.
    """

    red: float
    green: float
    blue: float

    @property
    def values(self) -> tuple[float, float, float]:
        """Valores como tupla (R, G, B)."""
        return (self.red, self.green, self.blue)

    @property
    def best_channel(self) -> int:
        """Índice del canal con mayor entropía (mejor para ocultación)."""
        return int(np.argmax(self.values))

    @property
    def best_channel_name(self) -> str:
        """Nombre del canal con mayor entropía."""
        names = ("Red", "Green", "Blue")
        return names[self.best_channel]


def compute_shannon_entropy(channel_data: NDArray[np.uint8]) -> float:
    """Calcula la entropía Shannon de un canal de imagen.

    La entropía mide la cantidad de información (o "desorden") en los
    valores de los píxeles. Un canal con mayor entropía tiene más
    variabilidad natural, lo que permite ocultar mejor las modificaciones LSB.

    H = -Σ p(x) * log2(p(x))  para cada valor de píxel x

    Args:
        channel_data: Array 2D con los valores del canal (0-255).

    Returns:
        Entropía Shannon en bits (rango: 0.0 a 8.0).
    """
    # Calcular histograma normalizado (función de probabilidad)
    histogram, _ = np.histogram(channel_data.flatten(), bins=256, range=(0, 256))
    probabilities = histogram / histogram.sum()

    # Filtrar probabilidades cero (log2(0) es indefinido)
    nonzero_probs = probabilities[probabilities > 0]

    # H = -Σ p(x) * log2(p(x))
    entropy = -np.sum(nonzero_probs * np.log2(nonzero_probs))

    return float(entropy)


def analyze_channel_entropy(image_data: NDArray[np.uint8]) -> ChannelEntropy:
    """Analiza la entropía Shannon de cada canal de color.

    Args:
        image_data: Array 3D de la imagen (H, W, 3) en formato RGB.

    Returns:
        ChannelEntropy con la entropía de cada canal.

    Raises:
        ValueError: Si la imagen no tiene 3 canales.
    """
    if image_data.ndim != 3 or image_data.shape[2] != 3:
        raise ValueError(
            f"Se esperaba imagen RGB (H, W, 3), recibido: {image_data.shape}"
        )

    return ChannelEntropy(
        red=compute_shannon_entropy(image_data[:, :, 0]),
        green=compute_shannon_entropy(image_data[:, :, 1]),
        blue=compute_shannon_entropy(image_data[:, :, 2]),
    )


def generate_density_map(
    image_data: NDArray[np.uint8],
    channel: int = 2,
    block_size: int = 8,
) -> NDArray[np.float64]:
    """Genera un mapa de densidad por bloques basado en la varianza local.

    Bloques con alta varianza (textura) pueden ocultar más bits.
    Bloques con baja varianza (gradientes suaves, cielos) deben
    recibir menos bits para evitar banding visible.

    Args:
        image_data: Array 3D de la imagen (H, W, 3).
        channel: Índice del canal a analizar (0=R, 1=G, 2=B).
        block_size: Tamaño del bloque en píxeles.

    Returns:
        Array 2D con la densidad normalizada por bloque (0.0 a 1.0).
        Dimensiones: (H // block_size, W // block_size).
    """
    channel_data = image_data[:, :, channel].astype(np.float64)
    height, width = channel_data.shape

    # Calcular dimensiones del mapa de bloques
    block_rows = height // block_size
    block_cols = width // block_size

    # Recortar para que sea divisible por block_size
    trimmed = channel_data[:block_rows * block_size, :block_cols * block_size]

    # Reshape en bloques y calcular varianza por bloque
    blocks = trimmed.reshape(block_rows, block_size, block_cols, block_size)
    variance_map = blocks.var(axis=(1, 3))

    # Normalizar al rango [0, 1]
    max_variance = variance_map.max()
    if max_variance > 0:
        density_map = variance_map / max_variance
    else:
        density_map = np.zeros_like(variance_map)

    return density_map


def compute_block_entropy_map(
    image_data: NDArray[np.uint8],
    channel: int = 2,
    block_size: int = 8,
) -> NDArray[np.float64]:
    """Genera un mapa de entropía por bloques.

    Similar a generate_density_map pero usando entropía Shannon
    en lugar de varianza, lo que es más preciso para detectar
    zonas con distribución compleja de valores.

    Args:
        image_data: Array 3D de la imagen (H, W, 3).
        channel: Índice del canal a analizar.
        block_size: Tamaño del bloque en píxeles.

    Returns:
        Array 2D con la entropía por bloque (0.0 a 8.0).
    """
    channel_data = image_data[:, :, channel]
    height, width = channel_data.shape

    block_rows = height // block_size
    block_cols = width // block_size

    entropy_map = np.zeros((block_rows, block_cols), dtype=np.float64)

    for row in range(block_rows):
        for col in range(block_cols):
            block = channel_data[
                row * block_size:(row + 1) * block_size,
                col * block_size:(col + 1) * block_size,
            ]
            entropy_map[row, col] = compute_shannon_entropy(block)

    return entropy_map
