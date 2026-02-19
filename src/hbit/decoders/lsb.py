"""
Decodificador LSB del protocolo H-Bit.

Reexporta la funcionalidad de extracción desde el módulo
hbit.encoders.lsb para mantener una separación lógica
entre codificación y decodificación.
"""

from __future__ import annotations

from hbit.encoders.lsb import decode_lsb, LSBDecodeResult

__all__ = ["decode_lsb", "LSBDecodeResult"]
