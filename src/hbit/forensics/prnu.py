"""
Análisis PRNU (Photo-Response Non-Uniformity) del protocolo H-Bit.

Contribución Senior 4.1: Extrae la huella dactilar del sensor de la
cámara y la vincula al H-Bit para identificar unívocamente el
dispositivo que capturó la imagen.

PRNU es un patrón de ruido fijo inherente a cada sensor fotográfico,
causado por imperfecciones de fabricación. Es único por dispositivo
(como una huella dactilar) y sobrevive a la mayoría de las
manipulaciones.

Algoritmo:
1. Capturar N imágenes de referencia (flat-field o cielo despejado)
2. Estimar la PRNU promediando el ruido residual
3. Para una imagen sospechosa, verificar la presencia de la PRNU

Ref: Lukáš, Fridrich & Goljan, "Digital Camera Identification from
Sensor Pattern Noise" (2006)
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from dataclasses import dataclass
from typing import Optional
from scipy.ndimage import uniform_filter


@dataclass(frozen=True)
class PRNUFingerprint:
    """Huella dactilar PRNU del sensor.

    Attributes:
        pattern: Patrón PRNU normalizado (misma resolución que la imagen).
        device_id: Identificador del dispositivo (si se conoce).
        num_reference_images: Número de imágenes de referencia usadas.
        quality: Calidad estimada de la huella (0.0 a 1.0).
    """

    pattern: NDArray[np.float64]
    device_id: str
    num_reference_images: int
    quality: float


@dataclass(frozen=True)
class PRNUMatchResult:
    """Resultado de la verificación PRNU.

    Attributes:
        correlation: Coeficiente de correlación normalizado.
        is_match: Si la imagen proviene del mismo sensor.
        confidence: Confianza del match (0.0 a 1.0).
        threshold_used: Umbral de correlación utilizado.
    """

    correlation: float
    is_match: bool
    confidence: float
    threshold_used: float


def extract_noise_residual(
    image_data: NDArray[np.uint8],
    denoising_filter_size: int = 3,
) -> NDArray[np.float64]:
    """Extrae el ruido residual de una imagen.

    El ruido residual = imagen_original - imagen_denoised.
    Contiene la PRNU más ruido aleatorio.

    Args:
        image_data: Array 3D (H, W, 3) de la imagen RGB.
        denoising_filter_size: Tamaño del filtro de suavizado.

    Returns:
        Array 3D con el ruido residual (float64).
    """
    image_float = image_data.astype(np.float64)
    denoised = np.zeros_like(image_float)

    for ch in range(3):
        denoised[:, :, ch] = uniform_filter(
            image_float[:, :, ch],
            size=denoising_filter_size,
        )

    # Ruido residual: diferencia entre original y denoised
    residual = image_float - denoised

    return residual


def estimate_prnu(
    reference_images: list[NDArray[np.uint8]],
    device_id: str = "unknown",
) -> PRNUFingerprint:
    """Estima la huella PRNU de un sensor a partir de imágenes de referencia.

    Promedia el ruido residual normalizado de múltiples imágenes
    para aislar la PRNU (componente fijo) del ruido aleatorio.

    PRNU ≈ (1/N) Σ (I_k - F(I_k)) / F(I_k)

    Donde:
    - I_k = imagen de referencia k
    - F(I_k) = versión denoised de I_k
    - N = número de imágenes

    Args:
        reference_images: Lista de imágenes de referencia del mismo sensor.
        device_id: Identificador del dispositivo.

    Returns:
        PRNUFingerprint con el patrón estimado.
    """
    if not reference_images:
        raise ValueError("Se necesita al menos una imagen de referencia")

    n = len(reference_images)
    shape = reference_images[0].shape
    prnu_sum = np.zeros(shape, dtype=np.float64)

    for img in reference_images:
        if img.shape != shape:
            raise ValueError("Todas las imágenes deben tener la misma resolución")

        residual = extract_noise_residual(img)
        denoised = img.astype(np.float64)

        # Normalizar por luminosidad para aislar la PRNU multiplicativa
        # PRNU_k = residual_k / max(denoised_k, 1)
        safe_denoised = np.maximum(denoised, 1.0)
        normalized = residual / safe_denoised

        prnu_sum += normalized

    # Promediar
    prnu_pattern = prnu_sum / n

    # Estimar calidad basada en la consistencia del patrón
    quality = _estimate_prnu_quality(prnu_pattern, n)

    return PRNUFingerprint(
        pattern=prnu_pattern,
        device_id=device_id,
        num_reference_images=n,
        quality=quality,
    )


def verify_prnu(
    image_data: NDArray[np.uint8],
    fingerprint: PRNUFingerprint,
    threshold: float = 0.1,
) -> PRNUMatchResult:
    """Verifica si una imagen proviene del mismo sensor.

    Calcula la correlación cruzada normalizada entre el ruido
    residual de la imagen y la huella PRNU del sensor.

    NCC = (W · K) / (||W|| · ||K||)

    Donde:
    - W = ruido residual de la imagen × imagen denoised
    - K = patrón PRNU del sensor

    Args:
        image_data: Imagen a verificar.
        fingerprint: Huella PRNU del sensor.
        threshold: Umbral de correlación para match.

    Returns:
        PRNUMatchResult con el resultado.
    """
    # Ajustar dimensiones si es necesario
    if image_data.shape != fingerprint.pattern.shape:
        # Recortar al tamaño menor
        min_h = min(image_data.shape[0], fingerprint.pattern.shape[0])
        min_w = min(image_data.shape[1], fingerprint.pattern.shape[1])
        image_data = image_data[:min_h, :min_w]
        prnu = fingerprint.pattern[:min_h, :min_w]
    else:
        prnu = fingerprint.pattern

    # Extraer ruido residual de la imagen sospechosa
    residual = extract_noise_residual(image_data)

    # Calcular correlación para cada canal y promediar
    correlations = []
    for ch in range(min(3, residual.shape[2])):
        w = residual[:, :, ch]
        k = prnu[:, :, ch]

        # Normalizar
        w_norm = np.sqrt(np.sum(w ** 2))
        k_norm = np.sqrt(np.sum(k ** 2))

        if w_norm < 1e-10 or k_norm < 1e-10:
            correlations.append(0.0)
            continue

        ncc = np.sum(w * k) / (w_norm * k_norm)
        correlations.append(float(ncc))

    avg_correlation = float(np.mean(correlations))
    is_match = bool(avg_correlation > threshold)

    # Confianza basada en la magnitud de la correlación
    confidence = min(1.0, max(0.0, avg_correlation / threshold)) if threshold > 0 else 0.0

    return PRNUMatchResult(
        correlation=float(avg_correlation),
        is_match=is_match,
        confidence=confidence,
        threshold_used=threshold,
    )


def generate_prnu_binding(
    fingerprint: PRNUFingerprint,
) -> bytes:
    """Genera un binding compacto de la PRNU para incluir en el H-Bit.

    En lugar de incrustar todo el patrón PRNU (enorme), genera un
    hash compacto que permite verificar la vinculación.

    Args:
        fingerprint: Huella PRNU del sensor.

    Returns:
        Hash SHA-256 del patrón PRNU (32 bytes).
    """
    import hashlib

    # Cuantizar y hashear el patrón PRNU
    # Cuantizar a 8 bits para estabilidad ante ruido
    quantized = np.clip(fingerprint.pattern * 1000 + 128, 0, 255).astype(np.uint8)
    pattern_bytes = quantized.tobytes()

    return hashlib.sha256(pattern_bytes).digest()


def _estimate_prnu_quality(
    prnu_pattern: NDArray[np.float64],
    num_images: int,
) -> float:
    """Estima la calidad de la huella PRNU estimada."""
    # Más imágenes → mejor calidad
    quality = min(1.0, num_images / 50)  # 50 imágenes = calidad máxima

    # La varianza del patrón debe ser baja pero no nula
    pattern_std = np.std(prnu_pattern)
    if pattern_std < 1e-6:
        quality *= 0.1  # Patrón casi nulo
    elif pattern_std > 0.1:
        quality *= 0.5  # Demasiado ruidoso

    return float(quality)
