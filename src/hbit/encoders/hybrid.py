"""
Encoder/Decoder híbrido del protocolo H-Bit.

Combina LSB (dominio espacial) y DCT (dominio frecuencia) para
máxima resistencia. La firma se incrusta simultáneamente en ambos
dominios, proporcionando redundancia cruzada.

Si la compresión JPEG destruye los bits LSB, los coeficientes DCT
sobreviven. Si una manipulación espacial altera los DCT, los LSB
en las zonas no afectadas permiten reconstruir.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from dataclasses import dataclass
from typing import Optional

from hbit.encoders.lsb import encode_lsb, decode_lsb, LSBEncodeResult, LSBDecodeResult
from hbit.encoders.dct import encode_dct, decode_dct, DCTEncodeResult, DCTDecodeResult
from hbit.core.sync import wrap_payload_with_sync


@dataclass(frozen=True)
class HybridEncodeResult:
    """Resultado de la codificación híbrida.

    Attributes:
        encoded_image: Imagen con firma en ambos dominios.
        lsb_result: Resultado del componente LSB.
        dct_result: Resultado del componente DCT.
        total_bits: Total de bits incrustados (ambos dominios).
    """

    encoded_image: NDArray[np.uint8]
    lsb_result: LSBEncodeResult
    dct_result: DCTEncodeResult
    total_bits: int


@dataclass(frozen=True)
class HybridDecodeResult:
    """Resultado de la decodificación híbrida.

    Attributes:
        payload_bits: Payload reconstruido por fusión.
        lsb_result: Resultado de extracción LSB.
        dct_result: Resultado de extracción DCT.
        source_used: Dominio predominante en la reconstrucción.
        confidence: Confianza combinada.
    """

    payload_bits: str
    lsb_result: LSBDecodeResult
    dct_result: DCTDecodeResult
    source_used: str
    confidence: float


def encode_hybrid(
    image_data: NDArray[np.uint8],
    payload_bits: str,
    lsb_channel: int = 2,
    dct_channel: int = 1,
    dct_strength: float = 25.0,
    density_map: Optional[NDArray[np.float64]] = None,
) -> HybridEncodeResult:
    """Incrusta la firma en ambos dominios (LSB + DCT).

    Estrategia:
    - LSB se aplica en un canal (default: azul)
    - DCT se aplica en otro canal (default: verde) para evitar interferencia

    Args:
        image_data: Array 3D (H, W, 3).
        payload_bits: Cadena de bits del payload (sin sync wrappers).
        lsb_channel: Canal para LSB.
        dct_channel: Canal para DCT.
        dct_strength: Fuerza del QIM en DCT.
        density_map: Mapa de densidad para LSB adaptativo.

    Returns:
        HybridEncodeResult con la imagen codificada.
    """
    # Envolver con sync markers
    wrapped = wrap_payload_with_sync(payload_bits)

    # 1. Aplicar LSB primero
    lsb_result = encode_lsb(
        image_data, wrapped,
        channel=lsb_channel,
        density_map=density_map,
    )

    # 2. Aplicar DCT sobre el resultado de LSB (en canal diferente)
    dct_result = encode_dct(
        lsb_result.encoded_image, wrapped,
        channel=dct_channel,
        strength=dct_strength,
    )

    total = lsb_result.bits_embedded + dct_result.bits_embedded

    return HybridEncodeResult(
        encoded_image=dct_result.encoded_image,
        lsb_result=lsb_result,
        dct_result=dct_result,
        total_bits=total,
    )


def decode_hybrid(
    image_data: NDArray[np.uint8],
    lsb_channel: int = 2,
    dct_channel: int = 1,
    dct_strength: float = 25.0,
    expected_payload_length: Optional[int] = None,
) -> HybridDecodeResult:
    """Extrae la firma de ambos dominios y fusiona resultados.

    Estrategia de fusión:
    1. Extraer de LSB y DCT por separado
    2. Si ambos producen payload, hacer votación bit a bit
    3. Si solo uno produce payload, usar ese
    4. La confianza refleja la concordancia entre dominios

    Args:
        image_data: Array 3D (H, W, 3).
        lsb_channel: Canal donde buscar LSB.
        dct_channel: Canal donde buscar DCT.
        dct_strength: Paso de cuantización DCT.
        expected_payload_length: Longitud esperada del payload.

    Returns:
        HybridDecodeResult con el payload fusionado.
    """
    # 1. Extraer de LSB
    lsb_result = decode_lsb(
        image_data, channel=lsb_channel,
        payload_bit_length=expected_payload_length,
    )

    # 2. Extraer de DCT
    dct_result = decode_dct(
        image_data, channel=dct_channel,
        strength=dct_strength,
        expected_payload_length=expected_payload_length,
    )

    # 3. Fusionar resultados
    has_lsb = lsb_result.payloads_found > 0
    has_dct = len(dct_result.payload_bits) > 0

    if has_lsb and has_dct:
        # Votación bit a bit entre LSB y DCT
        fused, confidence = _fuse_payloads(
            lsb_result.payload_bits,
            dct_result.payload_bits,
            lsb_result.confidence,
            dct_result.confidence,
        )
        source = "hybrid"
    elif has_lsb:
        fused = lsb_result.payload_bits
        confidence = lsb_result.confidence
        source = "lsb"
    elif has_dct:
        fused = dct_result.payload_bits
        confidence = dct_result.confidence
        source = "dct"
    else:
        fused = ""
        confidence = 0.0
        source = "none"

    return HybridDecodeResult(
        payload_bits=fused,
        lsb_result=lsb_result,
        dct_result=dct_result,
        source_used=source,
        confidence=confidence,
    )


def _fuse_payloads(
    lsb_bits: str,
    dct_bits: str,
    lsb_confidence: float,
    dct_confidence: float,
) -> tuple[str, float]:
    """Fusiona payloads de LSB y DCT mediante votación ponderada.

    Args:
        lsb_bits: Bits extraídos de LSB.
        dct_bits: Bits extraídos de DCT.
        lsb_confidence: Confianza LSB.
        dct_confidence: Confianza DCT.

    Returns:
        Tupla (payload_fusionado, confianza_combinada).
    """
    min_len = min(len(lsb_bits), len(dct_bits))
    if min_len == 0:
        return lsb_bits or dct_bits, max(lsb_confidence, dct_confidence)

    result = []
    agreements = 0

    for i in range(min_len):
        lsb_bit = lsb_bits[i]
        dct_bit = dct_bits[i]

        if lsb_bit == dct_bit:
            result.append(lsb_bit)
            agreements += 1
        else:
            # Usar el bit del dominio con mayor confianza
            if lsb_confidence >= dct_confidence:
                result.append(lsb_bit)
            else:
                result.append(dct_bit)

    agreement_ratio = agreements / min_len
    confidence = agreement_ratio * max(lsb_confidence, dct_confidence)

    return "".join(result), confidence
