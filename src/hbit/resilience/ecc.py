"""
Reed-Solomon Error Correction para el protocolo H-Bit.

Agrega paridad Reed-Solomon al payload para permitir la recuperación
de bits dañados por compresión, manipulación analógica o degradación.

El nivel de corrección se adapta al factor de redundancia disponible:
- nsym=10: corrige hasta 5 errores de símbolo (uso estándar)
- nsym=32: corrige hasta 16 errores (modo forense, más robusto)
"""

from __future__ import annotations

from dataclasses import dataclass

import reedsolo


@dataclass(frozen=True)
class ECCResult:
    """Resultado de la codificación/decodificación ECC.

    Attributes:
        data: Datos (originales o corregidos).
        parity: Bytes de paridad RS (solo en encode).
        corrected_errors: Número de errores corregidos (solo en decode).
        is_valid: Si la decodificación fue exitosa.
    """

    data: bytes
    parity: bytes
    corrected_errors: int
    is_valid: bool


# Presets de nivel de corrección
ECC_PRESETS = {
    "light": 10,     # Corrige hasta 5 errores — compresión JPEG leve
    "standard": 20,  # Corrige hasta 10 errores — uso general
    "heavy": 32,     # Corrige hasta 16 errores — manipulación analógica
    "forensic": 50,  # Corrige hasta 25 errores — modo forense máximo
}


def encode_ecc(
    payload: bytes,
    nsym: int | str = "standard",
) -> ECCResult:
    """Agrega paridad Reed-Solomon al payload.

    Args:
        payload: Datos crudros del payload H-Bit.
        nsym: Número de símbolos de paridad (int) o preset string.

    Returns:
        ECCResult con los datos y la paridad.
    """
    if isinstance(nsym, str):
        nsym = ECC_PRESETS.get(nsym, ECC_PRESETS["standard"])

    rs = reedsolo.RSCodec(nsym)
    encoded = rs.encode(payload)

    # La paridad son los últimos nsym bytes del encoded
    data_part = bytes(encoded[:len(payload)])
    parity_part = bytes(encoded[len(payload):])

    return ECCResult(
        data=data_part,
        parity=parity_part,
        corrected_errors=0,
        is_valid=True,
    )


def decode_ecc(
    data: bytes,
    parity: bytes,
    nsym: int | str = "standard",
) -> ECCResult:
    """Decodifica y corrige errores usando Reed-Solomon.

    Args:
        data: Datos potencialmente corruptos.
        parity: Bytes de paridad RS.
        nsym: Número de símbolos de paridad (debe coincidir con encode).

    Returns:
        ECCResult con los datos corregidos.
    """
    if isinstance(nsym, str):
        nsym = ECC_PRESETS.get(nsym, ECC_PRESETS["standard"])

    rs = reedsolo.RSCodec(nsym)
    combined = data + parity

    try:
        decoded = rs.decode(combined)
        # reedsolo.decode() retorna (data, remaining, errata_pos)
        corrected_data = bytes(decoded[0])
        errata_positions = decoded[2]
        num_errors = len(errata_positions) if errata_positions else 0

        return ECCResult(
            data=corrected_data,
            parity=parity,
            corrected_errors=num_errors,
            is_valid=True,
        )
    except reedsolo.ReedSolomonError:
        # Demasiados errores para corregir
        return ECCResult(
            data=data,
            parity=parity,
            corrected_errors=-1,
            is_valid=False,
        )


def compute_optimal_nsym(
    payload_length: int,
    expected_error_rate: float = 0.05,
) -> int:
    """Calcula el nsym óptimo basado en la tasa de error esperada.

    Args:
        payload_length: Longitud del payload en bytes.
        expected_error_rate: Tasa de error esperada (0.0 a 1.0).

    Returns:
        Número óptimo de símbolos de paridad.
    """
    # RS puede corregir nsym/2 errores de símbolo
    # Necesitamos corregir ceil(payload_length * error_rate) símbolos
    import math
    expected_errors = math.ceil(payload_length * expected_error_rate)
    nsym = expected_errors * 2

    # Limitar al rango práctico
    nsym = max(10, min(nsym, 255 - payload_length))

    return nsym
