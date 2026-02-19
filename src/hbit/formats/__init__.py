"""
hbit.formats — Capa de abstracción para soporte universal de archivos.

Provee handlers específicos para cada familia de formatos,
un registro dinámico para resolución automática, y un handler
genérico como fallback universal.

Uso:
    from hbit.formats import MediaRegistry

    registry = MediaRegistry.default()
    handler = registry.get_handler(Path("foto.jpg"))  # → ImageHandler
    handler = registry.get_handler(Path("audio.wav"))  # → AudioHandler
    handler = registry.get_handler(Path("data.xyz"))   # → GenericHandler
"""

from hbit.formats.base import (
    MediaHandler,
    CarrierData,
    EmbedResult,
    ExtractResult,
    EmbeddingStrategy,
    MediaCategory,
    MediaRegistry,
)

__all__ = [
    "MediaHandler",
    "CarrierData",
    "EmbedResult",
    "ExtractResult",
    "EmbeddingStrategy",
    "MediaCategory",
    "MediaRegistry",
]
