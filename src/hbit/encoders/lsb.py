"""
Motor de codificación LSB (Least Significant Bit) del protocolo H-Bit.

Implementa la incrustación esteganográfica en el bit menos significativo
de los píxeles de la imagen con las siguientes mejoras sobre el prototipo:

1. Redundancia cíclica adaptativa basada en mapas de densidad perceptual
2. Soporte para multi-canal
3. Formalización matemática: P'(x,y) = (P(x,y) & 0xFE) | b_k

Referencia: Sección 3.1 de la Especificación Técnica H-Bit.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from dataclasses import dataclass
from typing import Optional

from hbit.core.sync import wrap_payload_with_sync, SYNC_SEQUENCE_LENGTH


@dataclass(frozen=True)
class LSBEncodeResult:
    """Resultado de la codificación LSB.

    Attributes:
        encoded_image: Imagen con la firma incrustada.
        bits_embedded: Número total de bits incrustados.
        units_embedded: Número de unidades de sincronización completas.
        channel_used: Canal utilizado para la incrustación.
        capacity_used: Porcentaje de capacidad utilizada (0.0 a 1.0).
    """

    encoded_image: NDArray[np.uint8]
    bits_embedded: int
    units_embedded: int
    channel_used: int
    capacity_used: float


@dataclass(frozen=True)
class LSBDecodeResult:
    """Resultado de la decodificación LSB.

    Attributes:
        payload_bits: Cadena de bits del payload extraído.
        payloads_found: Número de copias del payload encontradas.
        confidence: Confianza de la extracción (0.0 a 1.0).
        raw_bits: Todos los bits LSB extraídos.
    """

    payload_bits: str
    payloads_found: int
    confidence: float
    raw_bits: str


def encode_lsb(
    image_data: NDArray[np.uint8],
    payload_bits: str,
    channel: int = 2,
    density_map: Optional[NDArray[np.float64]] = None,
) -> LSBEncodeResult:
    """Incrusta bits del payload en el LSB de los píxeles de la imagen.

    Formalización matemática (Sección 3.1):
    P'(x,y) = (P(x,y) & 0xFE) | b_k

    Donde:
    - P(x,y) es el valor original del píxel
    - b_k es el bit k del payload a incrustar
    - & 0xFE limpia el LSB (bit menos significativo)
    - | b_k establece el LSB al valor deseado

    Modos de operación:
    - Sin density_map: redundancia uniforme (llena toda la imagen)
    - Con density_map: redundancia adaptativa (más bits en zonas texturadas)

    Args:
        image_data: Array 3D (H, W, 3) de la imagen RGB.
        payload_bits: Cadena de bits del payload (con sync wrappers).
        channel: Canal a utilizar (0=R, 1=G, 2=B).
        density_map: Mapa de densidad perceptual (opcional).

    Returns:
        LSBEncodeResult con la imagen codificada y estadísticas.

    Raises:
        ValueError: Si no hay suficiente capacidad para al menos una copia.
    """
    result_image = image_data.copy()
    channel_data = result_image[:, :, channel].flatten()
    total_pixels = len(channel_data)
    payload_length = len(payload_bits)

    if payload_length > total_pixels:
        raise ValueError(
            f"Payload ({payload_length} bits) excede capacidad de imagen "
            f"({total_pixels} píxeles). Reduzca el payload o use una imagen mayor."
        )

    if density_map is not None:
        # Modo adaptativo: usar density_map para decidir dónde incrustar
        bits_embedded, units = _encode_adaptive(
            channel_data, payload_bits, density_map,
            result_image.shape[0], result_image.shape[1],
        )
    else:
        # Modo uniforme: llenar toda la imagen con repeticiones del payload
        bits_embedded, units = _encode_uniform(channel_data, payload_bits)

    # Reconstruir la imagen
    result_image[:, :, channel] = channel_data.reshape(
        result_image.shape[0], result_image.shape[1]
    )

    capacity_used = bits_embedded / total_pixels

    return LSBEncodeResult(
        encoded_image=result_image,
        bits_embedded=bits_embedded,
        units_embedded=units,
        channel_used=channel,
        capacity_used=capacity_used,
    )


def decode_lsb(
    image_data: NDArray[np.uint8],
    channel: int = 2,
    payload_bit_length: Optional[int] = None,
) -> LSBDecodeResult:
    """Extrae los bits LSB de la imagen y busca payloads válidos.

    Proceso de extracción:
    1. Extraer todos los LSB del canal especificado
    2. Buscar marcadores de sincronización (Barker-13)
    3. Extraer payloads delimitados por marcadores
    4. Si hay múltiples copias, aplicar votación mayoritaria

    Args:
        image_data: Array 3D (H, W, 3) de la imagen.
        channel: Canal del que extraer (0=R, 1=G, 2=B).
        payload_bit_length: Longitud esperada del payload (opcional, mejora búsqueda).

    Returns:
        LSBDecodeResult con el payload extraído.
    """
    from hbit.core.sync import find_payload_boundaries

    # 1. Extraer todos los LSB
    channel_data = image_data[:, :, channel].flatten()
    raw_bits = "".join(str(b & 1) for b in channel_data)

    # 2. Buscar límites de payload usando marcadores de sincronización
    boundaries = find_payload_boundaries(raw_bits, threshold=0.85)

    if not boundaries:
        # Intentar con umbral más bajo si no se encuentra nada
        boundaries = find_payload_boundaries(raw_bits, threshold=0.70)

    if not boundaries:
        return LSBDecodeResult(
            payload_bits="",
            payloads_found=0,
            confidence=0.0,
            raw_bits=raw_bits,
        )

    # 3. Extraer todos los payloads encontrados
    payloads = []
    for start, end in boundaries:
        payload = raw_bits[start:end]
        if payload_bit_length is None or len(payload) == payload_bit_length:
            payloads.append(payload)
        elif payload_bit_length is not None and len(payload) >= payload_bit_length:
            # Si es más largo, truncar al tamaño esperado
            payloads.append(payload[:payload_bit_length])

    if not payloads:
        return LSBDecodeResult(
            payload_bits="",
            payloads_found=0,
            confidence=0.0,
            raw_bits=raw_bits,
        )

    # 4. Votación mayoritaria si hay múltiples copias
    if len(payloads) > 1:
        final_payload, confidence = _majority_vote(payloads)
    else:
        final_payload = payloads[0]
        confidence = 1.0 / max(1, len(boundaries))  # Una sola copia → baja confianza

    return LSBDecodeResult(
        payload_bits=final_payload,
        payloads_found=len(payloads),
        confidence=confidence,
        raw_bits=raw_bits,
    )


def _encode_uniform(
    channel_data: NDArray[np.uint8],
    payload_bits: str,
) -> tuple[int, int]:
    """Codificación uniforme: repite el payload para llenar toda la imagen.

    Implementa el modelo de redundancia cíclica: R = (W×H) / |S_u|

    Args:
        channel_data: Array 1D con los píxeles del canal (se modifica in-place).
        payload_bits: Cadena de bits del payload con sync wrappers.

    Returns:
        Tupla (bits_embedded, units_embedded).
    """
    total_pixels = len(channel_data)
    payload_length = len(payload_bits)

    # Calcular factor de repetición: R = total_pixels / payload_length
    units_to_fill = total_pixels // payload_length

    # Crear cadena larga con repeticiones
    long_payload = payload_bits * units_to_fill
    bits_to_embed = min(len(long_payload), total_pixels)

    # Incrustación vectorizada: P'(x,y) = (P(x,y) & 0xFE) | b_k
    for i in range(bits_to_embed):
        bit = int(long_payload[i])
        channel_data[i] = (channel_data[i] & 0xFE) | bit

    return bits_to_embed, units_to_fill


def _encode_adaptive(
    channel_data: NDArray[np.uint8],
    payload_bits: str,
    density_map: NDArray[np.float64],
    height: int,
    width: int,
    block_size: int = 8,
) -> tuple[int, int]:
    """Codificación adaptativa: más bits en zonas de alta textura.

    Usa el mapa de densidad perceptual para decidir cuántos bits
    incrustar por bloque. Bloques con alta densidad reciben el payload
    completo; bloques con baja densidad reciben solo parte o nada.

    Args:
        channel_data: Array 1D con los píxeles del canal (modifica in-place).
        payload_bits: Cadena de bits del payload.
        density_map: Mapa de densidad normalizado por bloque.
        height: Altura de la imagen.
        width: Ancho de la imagen.
        block_size: Tamaño de bloque.

    Returns:
        Tupla (bits_embedded, units_embedded).
    """
    payload_length = len(payload_bits)
    bits_embedded = 0
    payload_idx = 0
    units_completed = 0

    block_rows = height // block_size
    block_cols = width // block_size

    # Iterar por bloques
    for row in range(block_rows):
        for col in range(block_cols):
            # Densidad del bloque determina cuántos píxeles se modifican
            if row < density_map.shape[0] and col < density_map.shape[1]:
                density = density_map[row, col]
            else:
                density = 0.5  # Valor por defecto si el mapa no cubre

            # Porcentaje de píxeles del bloque a modificar
            pixels_in_block = block_size * block_size
            pixels_to_modify = max(1, int(pixels_in_block * density))

            for pixel_offset in range(pixels_to_modify):
                # Calcular índice lineal del píxel
                pixel_row = row * block_size + pixel_offset // block_size
                pixel_col = col * block_size + pixel_offset % block_size

                if pixel_row >= height or pixel_col >= width:
                    continue

                linear_idx = pixel_row * width + pixel_col
                if linear_idx >= len(channel_data):
                    continue

                # Incrustar bit actual del payload
                bit = int(payload_bits[payload_idx % payload_length])
                channel_data[linear_idx] = (channel_data[linear_idx] & 0xFE) | bit

                bits_embedded += 1
                payload_idx += 1

                # Contar unidades completadas
                if payload_idx % payload_length == 0:
                    units_completed += 1

    return bits_embedded, units_completed


def _majority_vote(payloads: list[str]) -> tuple[str, float]:
    """Votación mayoritaria bit a bit entre múltiples copias del payload.

    Para cada posición de bit, se cuenta cuántas copias tienen '1'
    y cuántas tienen '0'. El bit con más votos gana.

    Esto permite reconstruir el payload original incluso cuando
    algunas copias están parcialmente dañadas.

    Args:
        payloads: Lista de cadenas de bits (todas deben tener la misma longitud).

    Returns:
        Tupla (payload_reconstruido, confianza).
        La confianza es el promedio de la proporción de votos del bit ganador.
    """
    if not payloads:
        return "", 0.0

    # Usar la longitud más común
    lengths = [len(p) for p in payloads]
    target_length = max(set(lengths), key=lengths.count)
    filtered = [p for p in payloads if len(p) == target_length]

    if not filtered:
        return payloads[0], 0.5

    num_payloads = len(filtered)
    result_bits = []
    confidence_sum = 0.0

    for bit_pos in range(target_length):
        ones = sum(1 for p in filtered if p[bit_pos] == "1")
        zeros = num_payloads - ones

        if ones >= zeros:
            result_bits.append("1")
            confidence_sum += ones / num_payloads
        else:
            result_bits.append("0")
            confidence_sum += zeros / num_payloads

    avg_confidence = confidence_sum / target_length if target_length > 0 else 0.0

    return "".join(result_bits), avg_confidence
