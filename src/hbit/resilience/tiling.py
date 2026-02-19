"""
Patrón de teselado para redundancia cíclica del protocolo H-Bit.

Organiza la distribución del payload en la imagen mediante patrones
de teselado (tiling) que maximizan la redundancia espacial.

El payload se repite en múltiples regiones de la imagen para que,
incluso si una zona se daña (recorte, artefactos JPEG, manchas),
las copias en otras zonas permitan reconstruir la firma completa.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TileLayout:
    """Distribución del teselado en la imagen.

    Attributes:
        tile_positions: Lista de posiciones (row, col) de cada tile.
        tile_size: Tamaño de cada tile (rows, cols) en bloques.
        total_tiles: Número total de tiles.
        redundancy_factor: Factor de redundancia (copias del payload).
    """

    tile_positions: list[tuple[int, int]]
    tile_size: tuple[int, int]
    total_tiles: int
    redundancy_factor: int


def compute_tile_layout(
    image_height: int,
    image_width: int,
    payload_bits: int,
    block_size: int = 8,
    min_redundancy: int = 3,
) -> TileLayout:
    """Calcula la distribución óptima de tiles para la imagen.

    Divide la imagen en tiles rectangulares que contienen exactamente
    una copia del payload. La disposición maximiza la distancia entre
    copias para resistir daños localizados (recortes, manchas).

    El factor de redundancia R = (W×H) / |S_u| donde:
    - W×H = área total disponible en píxeles
    - |S_u| = tamaño de una unidad de firma en bits

    Args:
        image_height: Altura de la imagen en píxeles.
        image_width: Ancho de la imagen en píxeles.
        payload_bits: Longitud del payload en bits (incluyendo sync).
        block_size: Tamaño del bloque base.
        min_redundancy: Redundancia mínima deseada.

    Returns:
        TileLayout con la distribución calculada.
    """
    total_pixels = image_height * image_width

    # Factor de redundancia máximo posible
    max_redundancy = total_pixels // payload_bits

    if max_redundancy < 1:
        raise ValueError(
            f"Imagen demasiado pequeña: {total_pixels} píxeles para "
            f"{payload_bits} bits de payload."
        )

    # Usar el factor de redundancia máximo (llena toda la imagen)
    actual_redundancy = max(min_redundancy, max_redundancy)

    # Calcular tiles: dividir la imagen en filas de tiles
    # Cada tile contiene payload_bits / image_width filas de bits
    pixels_per_tile = payload_bits
    tile_height_px = max(block_size, int(np.sqrt(pixels_per_tile)))
    tile_width_px = max(block_size, pixels_per_tile // tile_height_px)

    # Ajustar a múltiplos del block_size
    tile_height_px = (tile_height_px // block_size) * block_size
    tile_width_px = (tile_width_px // block_size) * block_size

    if tile_height_px == 0:
        tile_height_px = block_size
    if tile_width_px == 0:
        tile_width_px = block_size

    # Generar posiciones de tiles
    positions = []
    for row in range(0, image_height - tile_height_px + 1, tile_height_px):
        for col in range(0, image_width - tile_width_px + 1, tile_width_px):
            positions.append((row, col))

    return TileLayout(
        tile_positions=positions,
        tile_size=(tile_height_px // block_size, tile_width_px // block_size),
        total_tiles=len(positions),
        redundancy_factor=min(len(positions), actual_redundancy),
    )


def generate_interleaved_sequence(
    payload_bits: str,
    num_copies: int,
    interleave_depth: int = 4,
) -> str:
    """Genera una secuencia interleaved del payload.

    En lugar de poner copias consecutivas (AAABBB), se entrelazan
    los bits de cada copia (ABABAB). Esto distribuye los bits de
    cada copia en toda la imagen, haciendo que un daño localizado
    afecte a todas las copias uniformemente en lugar de destruir
    una copia completa.

    Ejemplo con depth=2:
    Copia1: ABCDEF, Copia2: abcdef
    Resultado: AaBbCcDdEeFf

    Args:
        payload_bits: Cadena de bits del payload.
        num_copies: Número de copias a entrelazar.
        interleave_depth: Profundidad de interleaving (bits por grupo).

    Returns:
        Cadena de bits interleaved.
    """
    payload_len = len(payload_bits)
    copies = [payload_bits] * num_copies

    result = []
    pos = 0

    while pos < payload_len:
        for copy_idx in range(num_copies):
            chunk = copies[copy_idx][pos:pos + interleave_depth]
            result.append(chunk)
        pos += interleave_depth

    return "".join(result)


def deinterleave_sequence(
    interleaved_bits: str,
    payload_length: int,
    num_copies: int,
    interleave_depth: int = 4,
) -> list[str]:
    """Des-entrelaza una secuencia para recuperar las copias individuales.

    Args:
        interleaved_bits: Cadena de bits interleaved.
        payload_length: Longitud de una copia del payload.
        num_copies: Número de copias entrelazadas.
        interleave_depth: Profundidad de interleaving usada.

    Returns:
        Lista de copias individuales del payload.
    """
    copies = [""] * num_copies
    pos = 0
    total_len = len(interleaved_bits)

    while pos < total_len:
        for copy_idx in range(num_copies):
            chunk_start = pos
            chunk_end = min(pos + interleave_depth, total_len)
            if chunk_start < total_len:
                copies[copy_idx] += interleaved_bits[chunk_start:chunk_end]
            pos += interleave_depth

    # Truncar cada copia a la longitud esperada
    copies = [c[:payload_length] for c in copies]

    return copies
