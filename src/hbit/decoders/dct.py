"""
Decodificador DCT del protocolo H-Bit.

Reexporta la funcionalidad de extracción DCT desde el módulo
hbit.encoders.dct para mantener una separación lógica.
"""

from __future__ import annotations

from hbit.encoders.dct import decode_dct, DCTDecodeResult

__all__ = ["decode_dct", "DCTDecodeResult"]
