"""
Doble hash de integridad del protocolo H-Bit.

Hito 1.4: No solo se firma la autoría, sino que se genera un hash del
contenido visual. Si se modifica un solo píxel (por ejemplo, para borrar
un objeto en una foto periodística), el H-Bit detectará la discrepancia.

El hash de contenido se calcula excluyendo el canal donde se incrusta
la firma, para evitar la paradoja circular (la firma modifica el contenido
que estamos hashando).
"""

from __future__ import annotations

import hashlib

import numpy as np
from numpy.typing import NDArray
from dataclasses import dataclass
from enum import Enum


class IntegrityStatus(Enum):
    """Estado de la verificación de integridad."""

    INTACT = "INTACT"
    TAMPERED = "TAMPERED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class IntegrityResult:
    """Resultado de la verificación de integridad.

    Attributes:
        status: Estado de la integridad de la imagen.
        computed_hash: Hash calculado de la imagen actual.
        expected_hash: Hash esperado (extraído del payload H-Bit).
        difference_ratio: Proporción de diferencia (0.0 = idénticos).
    """

    status: IntegrityStatus
    computed_hash: bytes
    expected_hash: bytes
    difference_ratio: float

    @property
    def is_intact(self) -> bool:
        """True si la imagen no ha sido manipulada."""
        return self.status == IntegrityStatus.INTACT


def compute_content_hash(
    image_data: NDArray[np.uint8],
    exclude_channel: int = 2,
) -> bytes:
    """Calcula el hash SHA-256 del contenido visual excluyendo un canal.

    El canal excluido es donde se incrusta la firma H-Bit. Al excluirlo,
    evitamos la paradoja circular donde la firma modifica el hash que
    la firma contiene.

    Args:
        image_data: Array 3D (H, W, 3) de la imagen RGB.
        exclude_channel: Índice del canal a excluir (0=R, 1=G, 2=B).

    Returns:
        Hash SHA-256 del contenido (32 bytes).
    """
    # Seleccionar los canales que NO se excluyen
    channels_to_hash = [i for i in range(3) if i != exclude_channel]

    # Concatenar los datos de los canales incluidos
    content = b"".join(
        image_data[:, :, ch].tobytes() for ch in channels_to_hash
    )

    return hashlib.sha256(content).digest()


def compute_perceptual_hash(
    image_data: NDArray[np.uint8],
    hash_size: int = 16,
) -> bytes:
    """Calcula un hash perceptual robusto de la imagen.

    A diferencia del hash criptográfico, el hash perceptual es
    tolerante a cambios menores (compresión, redimensionamiento suave)
    pero detecta cambios significativos en el contenido visual.

    Algoritmo: DCT-based perceptual hash (pHash simplificado)
    1. Reducir la imagen a un tamaño fijo
    2. Convertir a escala de grises
    3. Calcular DCT
    4. Extraer coeficientes de baja frecuencia
    5. Binarizar respecto a la media

    Args:
        image_data: Array 3D (H, W, 3) de la imagen RGB.
        hash_size: Tamaño del hash en bits por lado (hash_size² bits total).

    Returns:
        Hash perceptual como bytes.
    """
    from scipy.fft import dctn

    # 1. Convertir a escala de grises
    gray = (
        0.2126 * image_data[:, :, 0].astype(np.float64)
        + 0.7152 * image_data[:, :, 1].astype(np.float64)
        + 0.0722 * image_data[:, :, 2].astype(np.float64)
    )

    # 2. Reducir a tamaño fijo usando promedios por bloque
    target_size = hash_size * 4  # Trabajamos con 4x el tamaño del hash
    resized = _resize_simple(gray, target_size, target_size)

    # 3. DCT 2D
    dct_result = dctn(resized, type=2, norm="ortho")

    # 4. Extraer esquina superior izquierda (baja frecuencia)
    low_freq = dct_result[:hash_size, :hash_size]

    # 5. Binarizar respecto a la media (excluyendo DC component)
    median_value = np.median(low_freq[1:, 1:])  # Excluir DC (0,0)
    hash_bits = (low_freq >= median_value).flatten()

    # Convertir bits a bytes
    hash_bytes = np.packbits(hash_bits).tobytes()
    return hash_bytes


def verify_content_integrity(
    image_data: NDArray[np.uint8],
    embedded_hash: bytes,
    exclude_channel: int = 2,
) -> IntegrityResult:
    """Verifica la integridad del contenido de la imagen.

    Compara el hash calculado de la imagen actual con el hash
    que fue incrustado en el payload H-Bit al momento de firmar.

    Args:
        image_data: Array 3D (H, W, 3) de la imagen actual.
        embedded_hash: Hash extraído del payload H-Bit (32 bytes).
        exclude_channel: Canal que contiene la firma H-Bit.

    Returns:
        IntegrityResult con el estado de la verificación.
    """
    computed = compute_content_hash(image_data, exclude_channel)

    if computed == embedded_hash:
        return IntegrityResult(
            status=IntegrityStatus.INTACT,
            computed_hash=computed,
            expected_hash=embedded_hash,
            difference_ratio=0.0,
        )

    # Calcular qué tan diferentes son (distancia de Hamming normalizada)
    computed_bits = np.unpackbits(np.frombuffer(computed, dtype=np.uint8))
    expected_bits = np.unpackbits(np.frombuffer(embedded_hash, dtype=np.uint8))
    diff_ratio = float(np.sum(computed_bits != expected_bits)) / len(computed_bits)

    return IntegrityResult(
        status=IntegrityStatus.TAMPERED,
        computed_hash=computed,
        expected_hash=embedded_hash,
        difference_ratio=diff_ratio,
    )


def _resize_simple(
    image: NDArray[np.float64],
    target_height: int,
    target_width: int,
) -> NDArray[np.float64]:
    """Redimensiona una imagen 2D por promediado de bloques.

    Args:
        image: Imagen 2D de entrada.
        target_height: Alto objetivo.
        target_width: Ancho objetivo.

    Returns:
        Imagen redimensionada.
    """
    height, width = image.shape
    row_ratio = height / target_height
    col_ratio = width / target_width

    result = np.zeros((target_height, target_width), dtype=np.float64)

    for row in range(target_height):
        for col in range(target_width):
            row_start = int(row * row_ratio)
            row_end = int((row + 1) * row_ratio)
            col_start = int(col * col_ratio)
            col_end = int((col + 1) * col_ratio)
            result[row, col] = image[row_start:row_end, col_start:col_end].mean()

    return result
