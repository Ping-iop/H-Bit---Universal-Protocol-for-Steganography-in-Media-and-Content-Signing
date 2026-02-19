"""
Handler genérico para H-Bit.

Fallback universal para cualquier formato de archivo no reconocido.

Estrategia: Append stream al final del archivo con marcadores
delimitadores. La firma sobrevive copias bit-a-bit pero NO
sobrevive re-codificaciones ni transformaciones del formato.

Este es el handler de último recurso que garantiza que H-Bit
pueda firmar CUALQUIER archivo, presente o futuro.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from hbit.formats.base import (
    MediaHandler,
    CarrierData,
    EmbedResult,
    ExtractResult,
    EmbeddingStrategy,
    MediaCategory,
)


# Marcadores binarios para delimitar el stream H-Bit
HBIT_MAGIC = b"\x00\x48\x42\x49\x54\x00"        # \0HBIT\0
HBIT_MAGIC_END = b"\x00\x45\x4E\x44\x48\x42\x00"  # \0ENDHB\0
HBIT_VERSION = b"\x01"


class GenericHandler(MediaHandler):
    """Handler genérico universal para cualquier formato.

    Funciona con CUALQUIER archivo binario añadiendo un stream
    H-Bit al final del archivo, delimitado por marcadores mágicos.

    Formato del stream:
        MAGIC | VERSION | LEN(4 bytes BE) | PAYLOAD | CRC32 | MAGIC_END

    Limitaciones:
    - La firma NO sobrevive re-codificación del formato
    - La firma NO sobrevive truncamiento
    - La firma SÍ sobrevive copias exactas (bytes idénticos)
    - Algunos formatos pueden ignorar los bytes extra al final

    Formatos con buena compatibilidad (ignoran trailing data):
    - ZIP, JAR, APK, OOXML
    - JPEG (ignora datos después de EOI marker)
    - PDF (después de %%EOF)
    - EXE/DLL (PE format tiene longitud explícita)
    """

    @property
    def category(self) -> MediaCategory:
        return MediaCategory.GENERIC

    @property
    def supported_extensions(self) -> list[str]:
        # El handler genérico no registra extensiones específicas;
        # se usa como fallback cuando ningún otro handler aplica.
        return []

    def load(self, path: Path) -> CarrierData:
        """Carga cualquier archivo como bytes raw.

        Args:
            path: Ruta al archivo.

        Returns:
            CarrierData con los bytes del archivo.
        """
        import hashlib
        raw_data = path.read_bytes()

        # Canonical hash: hash sin el stream H-Bit
        clean_data = raw_data
        magic_pos = raw_data.rfind(HBIT_MAGIC)
        if magic_pos != -1:
            clean_data = raw_data[:magic_pos]
        canonical_hash = hashlib.sha256(clean_data).digest()

        return CarrierData(
            raw_data=raw_data,
            metadata={
                "size": len(raw_data),
                "format": path.suffix.upper().lstrip(".") or "BINARY",
                "has_hbit": HBIT_MAGIC in raw_data,
            },
            capacity_bits=64 * 1024 * 8,  # ~64KB payload
            strategy=EmbeddingStrategy.APPEND,
            category=MediaCategory.GENERIC,
            original_path=path,
            canonical_hash=canonical_hash,
        )

    def save(self, data: bytes, path: Path, carrier: CarrierData) -> Path:
        """Guarda los bytes modificados al archivo.

        Args:
            data: Bytes del archivo con stream H-Bit.
            path: Ruta de salida.
            carrier: CarrierData original.

        Returns:
            Path del archivo guardado.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def embed(self, carrier: CarrierData, payload_bits: str) -> EmbedResult:
        """Añade un stream H-Bit al final del archivo.

        Si ya existe un stream H-Bit, lo reemplaza.

        Args:
            carrier: Datos del archivo.
            payload_bits: Bits a incrustar.

        Returns:
            EmbedResult con los bytes modificados.
        """
        file_data = bytearray(carrier.raw_data)

        # Remover H-Bit existente si hay
        existing_start = file_data.find(HBIT_MAGIC)
        if existing_start != -1:
            existing_end = file_data.find(HBIT_MAGIC_END, existing_start)
            if existing_end != -1:
                file_data = (
                    file_data[:existing_start]
                    + file_data[existing_end + len(HBIT_MAGIC_END):]
                )

        # Convertir bits a bytes
        payload_bytes = self._bits_to_bytes(payload_bits)

        # CRC32 para verificación de integridad del stream
        import zlib
        crc = zlib.crc32(payload_bytes) & 0xFFFFFFFF

        # Construir stream H-Bit
        hbit_stream = (
            HBIT_MAGIC
            + HBIT_VERSION
            + len(payload_bits).to_bytes(4, "big")  # Longitud en BITS
            + len(payload_bytes).to_bytes(4, "big")  # Longitud en BYTES
            + payload_bytes
            + crc.to_bytes(4, "big")
            + HBIT_MAGIC_END
        )

        modified = bytes(file_data) + hbit_stream

        return EmbedResult(
            output_data=modified,
            bits_embedded=len(payload_bits),
            capacity_used=len(payload_bits) / carrier.capacity_bits,
            strategy_used=EmbeddingStrategy.APPEND,
        )

    def extract(
        self,
        carrier: CarrierData,
        expected_length: Optional[int] = None,
    ) -> ExtractResult:
        """Extrae el stream H-Bit del final del archivo.

        Args:
            carrier: Datos del archivo.
            expected_length: Longitud esperada (ignorada, se usa la del stream).

        Returns:
            ExtractResult con los bits extraídos.
        """
        data = carrier.raw_data

        # Buscar marcador
        magic_pos = data.rfind(HBIT_MAGIC)  # Último ocurrencia
        if magic_pos == -1:
            return ExtractResult(
                payload_bits="",
                confidence=0.0,
                strategy_used=EmbeddingStrategy.APPEND,
                payloads_found=0,
            )

        # Parsear header
        offset = magic_pos + len(HBIT_MAGIC)

        # Versión
        version = data[offset]
        offset += 1

        # Longitud en bits
        bit_length = int.from_bytes(data[offset:offset + 4], "big")
        offset += 4

        # Longitud en bytes
        byte_length = int.from_bytes(data[offset:offset + 4], "big")
        offset += 4

        # Payload
        payload_bytes = data[offset:offset + byte_length]
        offset += byte_length

        # CRC32
        stored_crc = int.from_bytes(data[offset:offset + 4], "big")
        offset += 4

        # Verificar integridad
        import zlib
        computed_crc = zlib.crc32(payload_bytes) & 0xFFFFFFFF
        crc_valid = stored_crc == computed_crc

        # Convertir a bits
        payload_bits = "".join(format(b, "08b") for b in payload_bytes)
        payload_bits = payload_bits[:bit_length]  # Truncar al original

        return ExtractResult(
            payload_bits=payload_bits,
            confidence=0.95 if crc_valid else 0.3,
            strategy_used=EmbeddingStrategy.APPEND,
            payloads_found=1,
        )

    @staticmethod
    def _bits_to_bytes(bits: str) -> bytes:
        """Convierte cadena de bits a bytes."""
        padded = bits.ljust(((len(bits) + 7) // 8) * 8, "0")
        return bytes(int(padded[i:i + 8], 2) for i in range(0, len(padded), 8))
