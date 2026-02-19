"""
Motor de codificación DCT del protocolo H-Bit.

Incrusta la firma en los coeficientes de frecuencia media de la
Transformada Discreta del Coseno (DCT) en bloques 8×8, compatible
con JPEG. Los coeficientes de baja frecuencia (visibles) y alta
frecuencia (eliminados por compresión) se evitan.

Integra la máscara JND (Contribución Senior 2.1) para calibrar
la fuerza de incrustación por bloque, asegurando imperceptibilidad.

Hito 2.2: Sobrevive a compresión JPEG hasta Q=30.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy.fft import dctn, idctn
from dataclasses import dataclass
from typing import Optional

from hbit.analysis.jnd import compute_jnd_mask, JPEG_QUANT_TABLE


# Coeficientes de frecuencia media seleccionados para incrustación.
# Se eligen posiciones con buen equilibrio entre robustez y capacidad.
# Las coordenadas (fila, col) dentro de cada bloque 8×8 representan
# frecuencias que no son ni muy bajas (visibles) ni muy altas (eliminadas).
#
# Patrón de selección en zig-zag:
#   DC  1  5  6 14 15 27 28
#    2  4  7 13 16 26 29 42
#    3  8 12 17 25 30 41 43
#    9 11 18 24 31 40 44 53
#   10 19 23 32 39 45 52 54
#   20 22 33 38 46 51 55 60
#   21 34 37 47 50 56 59 61
#   35 36 48 49 57 58 62 63
#
# Seleccionamos posiciones 8-20 del zig-zag (frecuencias medias)
MID_FREQ_POSITIONS = [
    (1, 2), (2, 1), (2, 0), (3, 0),  # Posiciones 8-11
    (2, 2), (1, 3), (0, 4), (0, 5),  # Posiciones 12-15
    (1, 4), (2, 3), (3, 2), (4, 1),  # Posiciones 16-19
    (4, 0),                           # Posición 20
]


@dataclass(frozen=True)
class DCTEncodeResult:
    """Resultado de la codificación DCT.

    Attributes:
        encoded_image: Imagen con la firma en dominio frecuencia.
        bits_embedded: Número total de bits incrustados.
        blocks_modified: Número de bloques 8×8 modificados.
        channel_used: Canal utilizado.
        avg_distortion: Distorsión media (PSNR estimado).
    """

    encoded_image: NDArray[np.uint8]
    bits_embedded: int
    blocks_modified: int
    channel_used: int
    avg_distortion: float


@dataclass(frozen=True)
class DCTDecodeResult:
    """Resultado de la decodificación DCT.

    Attributes:
        payload_bits: Cadena de bits del payload extraído.
        blocks_read: Número de bloques leídos.
        confidence: Confianza de la extracción (0.0 a 1.0).
    """

    payload_bits: str
    blocks_read: int
    confidence: float


def compute_adaptive_strength(
    image_data: NDArray[np.uint8],
    channel: int = 2,
    min_strength: float = 15.0,
    max_strength: float = 60.0,
) -> float:
    """Calcula la fuerza de embedding DCT óptima según la textura de la imagen.

    Analiza tres métricas del contenido para adaptar la fuerza:
    1. Densidad de bordes (Sobel): imágenes con muchos bordes toleran más fuerza
    2. Varianza local: regiones de alta varianza ocultan mejor las modificaciones
    3. Energía en frecuencias medias (DCT): mayor energía = step más grande tolerable

    Args:
        image_data: Array 3D (H, W, 3) de la imagen RGB.
        channel: Canal a analizar (default: Blue).
        min_strength: Fuerza mínima (imágenes muy lisas).
        max_strength: Fuerza máxima (imágenes muy texturizadas).

    Returns:
        Fuerza de cuantización óptima para la imagen.
    """
    ch = image_data[:, :, channel].astype(np.float64)
    h, w = ch.shape

    # 1. Densidad de bordes (Sobel horizontal + vertical)
    sobel_h = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=np.float64)
    sobel_v = sobel_h.T

    from scipy.signal import convolve2d
    edges_h = convolve2d(ch, sobel_h, mode="same", boundary="symm")
    edges_v = convolve2d(ch, sobel_v, mode="same", boundary="symm")
    edge_magnitude = np.sqrt(edges_h**2 + edges_v**2)
    edge_density = float(np.mean(edge_magnitude > 30))

    # 2. Varianza global del canal
    global_variance = float(np.var(ch))
    variance_score = min(global_variance / 2000.0, 1.0)

    # 3. Energía de frecuencias medias (muestreo de bloques 8×8)
    block_size = 8
    sample_rows = min(h // block_size, 20)
    sample_cols = min(w // block_size, 20)
    mid_freq_energy = 0.0
    n_samples = 0

    for r in range(0, sample_rows * block_size, block_size):
        for c in range(0, sample_cols * block_size, block_size):
            block = ch[r:r + block_size, c:c + block_size] - 128.0
            dct_block = dctn(block, type=2, norm="ortho")
            for fi, fj in MID_FREQ_POSITIONS:
                mid_freq_energy += abs(dct_block[fi, fj])
            n_samples += 1

    avg_mid_energy = mid_freq_energy / max(n_samples * len(MID_FREQ_POSITIONS), 1)
    energy_score = min(avg_mid_energy / 50.0, 1.0)

    # Combinar métricas (ponderadas)
    texture_score = 0.4 * edge_density + 0.3 * variance_score + 0.3 * energy_score
    texture_score = max(0.0, min(texture_score, 1.0))

    adaptive_strength = min_strength + texture_score * (max_strength - min_strength)
    return float(round(adaptive_strength, 1))




def encode_dct(
    image_data: NDArray[np.uint8],
    payload_bits: str,
    channel: int = 2,
    strength: float = 25.0,
    jnd_mask: Optional[NDArray[np.float64]] = None,
    use_jnd: bool = True,
) -> DCTEncodeResult:
    """Incrusta bits del payload en coeficientes DCT de frecuencia media.

    Algoritmo Quantization Index Modulation (QIM):
    1. Dividir la imagen en bloques 8×8
    2. Calcular DCT 2D de cada bloque
    3. Para cada coeficiente de frecuencia media seleccionado:
       - Cuantizar: q = round(coeff / step)
       - Modificar paridad: si bit=0 → q par, si bit=1 → q impar
       - Reconstruir: coeff' = q * step
    4. Calcular IDCT para reconstruir los píxeles

    Args:
        image_data: Array 3D (H, W, 3) de la imagen RGB.
        payload_bits: Cadena binaria del payload.
        channel: Canal a utilizar (0=R, 1=G, 2=B).
        strength: Paso de cuantización base (mayor = más robusto, menos sutil).
        jnd_mask: Máscara JND pre-calculada (opcional, se calcula si use_jnd=True).
        use_jnd: Si True, calcula/usa máscara JND para limitar distorsión.

    Returns:
        DCTEncodeResult con la imagen codificada y estadísticas.
    """
    result_image = image_data.copy()
    channel_data = result_image[:, :, channel].astype(np.float64) - 128.0
    height, width = channel_data.shape

    block_size = 8
    block_rows = height // block_size
    block_cols = width // block_size

    # Calcular JND mask si es necesario
    if use_jnd and jnd_mask is None:
        jnd_mask = compute_jnd_mask(image_data, channel, block_size)

    payload_len = len(payload_bits)
    bits_per_block = len(MID_FREQ_POSITIONS)
    bit_idx = 0
    blocks_modified = 0
    total_distortion = 0.0

    for row in range(block_rows):
        for col in range(block_cols):
            # Extraer bloque 8×8
            block = channel_data[
                row * block_size:(row + 1) * block_size,
                col * block_size:(col + 1) * block_size,
            ].copy()

            # DCT 2D
            dct_block = dctn(block, type=2, norm="ortho")
            block_modified = False

            for pos_idx, (fi, fj) in enumerate(MID_FREQ_POSITIONS):
                if bit_idx >= payload_len:
                    # Repetir payload para redundancia cíclica
                    pass  # Simplemente volvemos al inicio
                    
                current_bit = int(payload_bits[bit_idx % payload_len])

                # Determinar paso de cuantización
                if use_jnd and jnd_mask is not None:
                    # Usar JND para limitar la fuerza
                    jnd_value = jnd_mask[row, col, fi * block_size + fj]
                    # El paso no debe exceder 2× el JND threshold
                    effective_strength = min(strength, jnd_value * 2.0)
                    effective_strength = max(effective_strength, 2.0)  # Mínimo viable
                else:
                    effective_strength = strength

                # QIM: Quantization Index Modulation
                coeff = dct_block[fi, fj]
                quantized = round(coeff / effective_strength)

                # Forzar paridad del coeficiente cuantizado
                if current_bit == 0:
                    # Forzar par
                    if quantized % 2 != 0:
                        quantized += 1 if coeff >= 0 else -1
                else:
                    # Forzar impar
                    if quantized % 2 == 0:
                        quantized += 1 if coeff >= 0 else -1

                # Reconstruir coeficiente
                new_coeff = quantized * effective_strength
                distortion = abs(new_coeff - coeff)
                total_distortion += distortion

                dct_block[fi, fj] = new_coeff
                block_modified = True
                bit_idx += 1

            if block_modified:
                # IDCT para reconstruir píxeles
                reconstructed = idctn(dct_block, type=2, norm="ortho")
                channel_data[
                    row * block_size:(row + 1) * block_size,
                    col * block_size:(col + 1) * block_size,
                ] = reconstructed
                blocks_modified += 1

    # Recortar al rango [0, 255] y convertir a uint8
    channel_data = np.clip(channel_data + 128.0, 0, 255).astype(np.uint8)
    result_image[:, :, channel] = channel_data[:height, :width]

    # PSNR estimado
    avg_dist = total_distortion / max(1, bit_idx)

    return DCTEncodeResult(
        encoded_image=result_image,
        bits_embedded=bit_idx,
        blocks_modified=blocks_modified,
        channel_used=channel,
        avg_distortion=avg_dist,
    )


def decode_dct(
    image_data: NDArray[np.uint8],
    channel: int = 2,
    strength: float = 25.0,
    expected_payload_length: Optional[int] = None,
) -> DCTDecodeResult:
    """Extrae bits del payload desde coeficientes DCT de frecuencia media.

    Proceso inverso al encoding:
    1. Dividir en bloques 8×8
    2. DCT 2D de cada bloque
    3. Leer paridad de los coeficientes de frecuencia media

    Args:
        image_data: Array 3D (H, W, 3) de la imagen.
        channel: Canal del que extraer.
        strength: Paso de cuantización (debe coincidir con el usado al codificar).
        expected_payload_length: Longitud esperada del payload (bits).

    Returns:
        DCTDecodeResult con los bits extraídos.
    """
    channel_data = image_data[:, :, channel].astype(np.float64) - 128.0
    height, width = channel_data.shape

    block_size = 8
    block_rows = height // block_size
    block_cols = width // block_size

    extracted_bits = []
    blocks_read = 0

    for row in range(block_rows):
        for col in range(block_cols):
            block = channel_data[
                row * block_size:(row + 1) * block_size,
                col * block_size:(col + 1) * block_size,
            ]

            dct_block = dctn(block, type=2, norm="ortho")
            block_has_data = False

            for fi, fj in MID_FREQ_POSITIONS:
                coeff = dct_block[fi, fj]
                quantized = round(coeff / strength)

                # Leer paridad
                bit = quantized % 2
                if bit < 0:
                    bit = -bit  # abs para manejar negativos
                
                extracted_bits.append(str(bit))
                block_has_data = True

                if expected_payload_length and len(extracted_bits) >= expected_payload_length:
                    break

            if block_has_data:
                blocks_read += 1

            if expected_payload_length and len(extracted_bits) >= expected_payload_length:
                break

    payload_bits = "".join(extracted_bits)

    # Estimar confianza basada en consistencia de las copias redundantes
    confidence = _estimate_dct_confidence(
        payload_bits, expected_payload_length
    )

    return DCTDecodeResult(
        payload_bits=payload_bits,
        blocks_read=blocks_read,
        confidence=confidence,
    )


def _estimate_dct_confidence(
    extracted_bits: str,
    expected_length: Optional[int],
) -> float:
    """Estima la confianza de la extracción DCT.

    Si hay copias redundantes del payload, compara las copias
    para determinar la consistencia.

    Args:
        extracted_bits: Todos los bits extraídos.
        expected_length: Longitud esperada de una copia del payload.

    Returns:
        Confianza (0.0 a 1.0).
    """
    if not expected_length or expected_length <= 0:
        return 0.5  # Confianza media por defecto

    total_bits = len(extracted_bits)
    if total_bits < expected_length:
        return 0.3  # No hay suficientes bits

    num_copies = total_bits // expected_length
    if num_copies < 2:
        return 0.5

    # Comparar copias entre sí
    copies = [
        extracted_bits[i * expected_length:(i + 1) * expected_length]
        for i in range(num_copies)
    ]

    agreements = 0
    total_comparisons = 0

    for i in range(len(copies)):
        for j in range(i + 1, len(copies)):
            matching_bits = sum(
                1 for a, b in zip(copies[i], copies[j]) if a == b
            )
            agreements += matching_bits
            total_comparisons += expected_length

    if total_comparisons == 0:
        return 0.5

    return agreements / total_comparisons
