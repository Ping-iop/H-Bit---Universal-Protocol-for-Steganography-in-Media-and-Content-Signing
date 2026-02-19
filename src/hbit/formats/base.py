"""
Capa de abstracción para soporte universal de archivos en H-Bit.

Define la interfaz `MediaHandler` que cada formato debe implementar,
el contenedor universal `CarrierData`, y el registro dinámico
`MediaRegistry` para resolución automática de handlers por extensión.

Patrón: Strategy + Registry
- Strategy: cada handler sabe cómo incrustar/extraer bits en su formato
- Registry: auto-detección del handler correcto según extensión/MIME
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Optional, Type


class EmbeddingStrategy(Enum):
    """Estrategia de incrustación según el dominio del medio.

    Cada formato usa la estrategia más apropiada para
    maximizar la resiliencia de la firma.
    """

    LSB = auto()          # Least Significant Bit (imágenes, audio PCM)
    DCT = auto()          # Discrete Cosine Transform (JPEG, audio freq.)
    METADATA = auto()     # Metadatos del formato (XMP, EXIF, ID3, etc.)
    STREAM = auto()       # Stream oculto dentro del formato (PDF, Office)
    APPEND = auto()       # Append al final del archivo (genérico)
    HYBRID = auto()       # Combinación de múltiples estrategias


class MediaCategory(Enum):
    """Categoría de medio para agrupación lógica."""

    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    DOCUMENT = "document"
    GENERIC = "generic"


@dataclass
class CarrierData:
    """Contenedor universal de datos portadores.

    Abstrae los datos internos del archivo donde se incrustarán
    los bits del payload H-Bit. El handler sabe cómo convertir
    entre el archivo original y este contenedor.

    Attributes:
        raw_data: Datos crudos del medio (bytes, array, etc.).
        metadata: Metadatos del archivo (formato, resolución, etc.).
        capacity_bits: Capacidad máxima de embedding en bits.
        strategy: Estrategia de embedding recomendada.
        category: Categoría del medio.
        original_path: Ruta al archivo original.
        format_info: Información específica del formato.
        canonical_hash: Hash canónico del contenido, excluye datos H-Bit.
            Los handlers con estrategias stream/append deben setear esto
            para que la verificación funcione tras embedding.
    """

    raw_data: bytes
    metadata: dict = field(default_factory=dict)
    capacity_bits: int = 0
    strategy: EmbeddingStrategy = EmbeddingStrategy.APPEND
    category: MediaCategory = MediaCategory.GENERIC
    original_path: Optional[Path] = None
    format_info: dict = field(default_factory=dict)
    canonical_hash: Optional[bytes] = None

    def content_hash(self) -> bytes:
        """Calcula el hash SHA-256 del contenido del medio.

        Usa canonical_hash si está disponible (para formatos donde
        raw_data cambia tras embedding).
        """
        if self.canonical_hash is not None:
            return self.canonical_hash
        return hashlib.sha256(self.raw_data).digest()


@dataclass(frozen=True)
class EmbedResult:
    """Resultado de la incrustación de bits en un medio.

    Attributes:
        output_data: Datos del medio con bits incrustados.
        bits_embedded: Número de bits incrustados.
        capacity_used: Porcentaje de capacidad utilizada.
        strategy_used: Estrategia de embedding utilizada.
    """

    output_data: bytes
    bits_embedded: int
    capacity_used: float
    strategy_used: EmbeddingStrategy


@dataclass(frozen=True)
class ExtractResult:
    """Resultado de la extracción de bits de un medio.

    Attributes:
        payload_bits: Bits extraídos como cadena de '0' y '1'.
        confidence: Confianza de la extracción (0.0 a 1.0).
        strategy_used: Estrategia utilizada para extraer.
        payloads_found: Número de copias del payload encontradas.
    """

    payload_bits: str
    confidence: float
    strategy_used: EmbeddingStrategy
    payloads_found: int = 1


class MediaHandler(ABC):
    """Interfaz abstracta para handlers de formatos de archivo.

    Cada formato (imagen, audio, video, documento, etc.) implementa
    esta interfaz para soportar incrustación y extracción de H-Bit.

    Ciclo de vida:
        1. handler = MediaRegistry.get_handler(path)
        2. carrier = handler.load(path)
        3. result = handler.embed(carrier, payload_bits)
        4. handler.save(result.output_data, output_path)
    """

    @abstractmethod
    def load(self, path: Path) -> CarrierData:
        """Carga un archivo y extrae los datos portadores.

        Args:
            path: Ruta al archivo de entrada.

        Returns:
            CarrierData con los datos listos para embedding.
        """
        ...

    @abstractmethod
    def save(self, data: bytes, path: Path, carrier: CarrierData) -> Path:
        """Guarda los datos modificados al formato de salida.

        Args:
            data: Datos del medio con embedding aplicado.
            path: Ruta de salida.
            carrier: CarrierData original (para metadata de reconstrucción).

        Returns:
            Path del archivo guardado.
        """
        ...

    @abstractmethod
    def embed(self, carrier: CarrierData, payload_bits: str) -> EmbedResult:
        """Incrusta bits del payload en los datos del medio.

        Args:
            carrier: Datos del medio cargados.
            payload_bits: Cadena de '0' y '1' a incrustar.

        Returns:
            EmbedResult con los datos modificados.
        """
        ...

    @abstractmethod
    def extract(self, carrier: CarrierData, expected_length: Optional[int] = None) -> ExtractResult:
        """Extrae bits del payload de los datos del medio.

        Args:
            carrier: Datos del medio donde buscar.
            expected_length: Longitud esperada del payload en bits.

        Returns:
            ExtractResult con los bits extraídos.
        """
        ...

    @property
    @abstractmethod
    def category(self) -> MediaCategory:
        """Categoría del medio que maneja este handler."""
        ...

    @property
    @abstractmethod
    def supported_extensions(self) -> list[str]:
        """Extensiones de archivo soportadas (sin punto, lowercase)."""
        ...

    @property
    def name(self) -> str:
        """Nombre legible del handler."""
        return self.__class__.__name__


class MediaRegistry:
    """Registro dinámico de handlers de formatos.

    Resuelve automáticamente el handler correcto para un archivo
    según su extensión. Soporta registro de handlers personalizados
    para extensibilidad futura (plugin system).

    Uso:
        registry = MediaRegistry()
        handler = registry.get_handler(Path("foto.jpg"))
        # → ImageHandler

        # Registrar handler personalizado
        registry.register(MyCustomHandler())
    """

    _instance: Optional[MediaRegistry] = None
    _handlers: dict[str, MediaHandler]
    _fallback: Optional[MediaHandler]

    def __init__(self):
        self._handlers = {}
        self._fallback = None

    @classmethod
    def default(cls) -> MediaRegistry:
        """Obtiene la instancia singleton del registry con handlers precargados."""
        if cls._instance is None:
            cls._instance = cls()
            cls._instance._register_defaults()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Resetea el singleton (útil para tests)."""
        cls._instance = None

    def register(self, handler: MediaHandler) -> None:
        """Registra un handler para sus extensiones soportadas.

        Args:
            handler: Handler a registrar.
        """
        for ext in handler.supported_extensions:
            self._handlers[ext.lower()] = handler

    def register_fallback(self, handler: MediaHandler) -> None:
        """Registra un handler de fallback para extensiones desconocidas.

        Args:
            handler: Handler genérico a usar como fallback.
        """
        self._fallback = handler

    def get_handler(self, path: Path) -> MediaHandler:
        """Obtiene el handler apropiado para un archivo.

        Args:
            path: Ruta al archivo.

        Returns:
            MediaHandler registrado para la extensión.

        Raises:
            ValueError: Si no hay handler registrado y no hay fallback.
        """
        ext = path.suffix.lower().lstrip(".")

        if ext in self._handlers:
            return self._handlers[ext]

        if self._fallback:
            return self._fallback

        raise ValueError(
            f"No hay handler registrado para la extensión '.{ext}'. "
            f"Extensiones soportadas: {sorted(self._handlers.keys())}"
        )

    def supports(self, path: Path) -> bool:
        """Verifica si hay un handler disponible para un archivo.

        Args:
            path: Ruta al archivo.

        Returns:
            True si hay handler registrado o fallback disponible.
        """
        ext = path.suffix.lower().lstrip(".")
        return ext in self._handlers or self._fallback is not None

    @property
    def supported_extensions(self) -> list[str]:
        """Lista de extensiones soportadas."""
        return sorted(self._handlers.keys())

    @property
    def registered_handlers(self) -> dict[str, str]:
        """Mapa extensión → nombre del handler."""
        return {ext: h.name for ext, h in self._handlers.items()}

    def _register_defaults(self) -> None:
        """Registra los handlers por defecto."""
        # Importar aquí para evitar dependencias circulares
        from hbit.formats.image import ImageHandler
        from hbit.formats.audio import AudioHandler
        from hbit.formats.video import VideoHandler
        from hbit.formats.document import PDFHandler, OfficeHandler
        from hbit.formats.generic import GenericHandler

        self.register(ImageHandler())
        self.register(AudioHandler())
        self.register(VideoHandler())
        self.register(PDFHandler())
        self.register(OfficeHandler())
        self.register_fallback(GenericHandler())
