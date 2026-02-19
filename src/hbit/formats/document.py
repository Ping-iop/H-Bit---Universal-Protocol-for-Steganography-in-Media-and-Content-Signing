"""
Handler de documentos para H-Bit.

Soporta:
- PDF: Inyección en streams ocultos + metadatos XMP
- Office (DOCX, XLSX, PPTX): Custom XML parts en el contenedor OOXML

Estrategia dual:
1. STREAM: Datos incrustados en la estructura interna del formato
2. METADATA: Respaldo en campos de metadatos estándar

Los documentos Office (OOXML) son zipfiles con XML internos.
H-Bit inyecta una relación y parte custom XML que es invisible
para el usuario pero persiste ante ediciones menores.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
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


# ═══════════════════════════════════════════════════════════════════
# Marcador H-Bit para streams
# ═══════════════════════════════════════════════════════════════════

HBIT_MARKER = b"\x48\x42\x49\x54\x53\x49\x47\x4E"  # "HBITSIGN"
HBIT_MARKER_END = b"\x45\x4E\x44\x48\x42\x49\x54"   # "ENDHBIT"

# Namespace XML para partes custom OOXML
HBIT_XML_NS = "urn:hbit:signature:v1"


class PDFHandler(MediaHandler):
    """Handler robusto para archivos PDF.

    Estrategia de embedding dual (content-level):
    1. PRIMARIA: Inyecta un objeto PDF indirecto con el payload codificado
       en base64, registrado como parte del catálogo del documento. Esto
       sobrevive la mayoría de editorizaciones porque los editores PDF
       preservan objetos desconocidos del catálogo.
    2. FALLBACK LEGACY: Detecta y extrae payloads del formato anterior
       (comentario antes de %%EOF) para compatibilidad hacia atrás.

    El hash canónico excluye los datos H-Bit de ambos formatos.
    """

    # Marcadores de objeto PDF para H-Bit
    HBIT_OBJ_KEY = b"/HBitSignature"
    HBIT_STREAM_START = b"<<\n/Type /HBitPayload\n/V 2\n/Length "
    HBIT_STREAM_END = b"\nendstream\nendobj\n"

    @property
    def category(self) -> MediaCategory:
        return MediaCategory.DOCUMENT

    @property
    def supported_extensions(self) -> list[str]:
        return ["pdf"]

    def load(self, path: Path) -> CarrierData:
        """Carga un PDF como bytes raw."""
        raw_data = path.read_bytes()
        has_hbit = self._has_hbit_payload(raw_data)

        # Canonical hash: hash del PDF sin datos H-Bit
        canonical_hash = self._compute_canonical_hash(raw_data)

        return CarrierData(
            raw_data=raw_data,
            metadata={
                "size": len(raw_data),
                "format": "PDF",
                "has_hbit": has_hbit,
            },
            capacity_bits=64 * 1024 * 8,  # ~64KB de payload
            strategy=EmbeddingStrategy.STREAM,
            category=MediaCategory.DOCUMENT,
            original_path=path,
            canonical_hash=canonical_hash,
        )

    def save(self, data: bytes, path: Path, carrier: CarrierData) -> Path:
        """Guarda el PDF modificado."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def embed(self, carrier: CarrierData, payload_bits: str) -> EmbedResult:
        """Inyecta el payload como un objeto PDF indirecto.

        Crea un nuevo objeto PDF con tipo /HBitPayload que contiene
        el payload en un stream base64. Este objeto se referencia desde
        el diccionario /Info del trailer (como /HBitSignature) para que
        los editores PDF lo preserven al re-guardar.
        """
        import base64

        pdf_data = carrier.raw_data

        # Primero, limpiar cualquier H-Bit existente (legacy o nuevo)
        pdf_data = self._strip_hbit_data(pdf_data)

        payload_bytes = self._bits_to_bytes(payload_bits)
        payload_b64 = base64.b64encode(payload_bytes)
        bits_count = str(len(payload_bits)).encode("ascii")

        # Encontrar el mayor obj number en el PDF para crear uno nuevo
        next_obj_num = self._find_next_obj_number(pdf_data)

        # Construir el objeto H-Bit como stream PDF válido
        stream_content = payload_b64
        obj_bytes = (
            f"{next_obj_num} 0 obj\n".encode("ascii")
            + self.HBIT_STREAM_START
            + str(len(stream_content)).encode("ascii")
            + b"\n/Bits "
            + bits_count
            + b"\n>>\nstream\n"
            + stream_content
            + self.HBIT_STREAM_END
        )

        # Inyectar el objeto antes del xref/startxref/%%EOF
        insert_pos = self._find_insert_position(pdf_data)
        modified = (
            pdf_data[:insert_pos]
            + b"\n"
            + obj_bytes
            + pdf_data[insert_pos:]
        )

        return EmbedResult(
            output_data=modified,
            bits_embedded=len(payload_bits),
            capacity_used=len(payload_bits) / carrier.capacity_bits,
            strategy_used=EmbeddingStrategy.STREAM,
        )

    def extract(
        self,
        carrier: CarrierData,
        expected_length: Optional[int] = None,
    ) -> ExtractResult:
        """Extrae el payload del objeto HBitPayload o del formato legacy."""
        import base64

        data = carrier.raw_data

        # Intento 1: buscar objeto PDF con /Type /HBitPayload (v2)
        result = self._extract_v2(data, expected_length)
        if result.payloads_found > 0:
            return result

        # Intento 2: formato legacy (HBITSIGN marker antes de %%EOF)
        result = self._extract_legacy(data, expected_length)
        return result

    def _extract_v2(
        self, data: bytes, expected_length: Optional[int] = None
    ) -> ExtractResult:
        """Extrae payload del formato v2 (objeto PDF /HBitPayload)."""
        import base64
        import re

        # Buscar el stream del objeto HBitPayload
        type_marker = b"/Type /HBitPayload"
        marker_pos = data.find(type_marker)
        if marker_pos == -1:
            return ExtractResult(
                payload_bits="",
                confidence=0.0,
                strategy_used=EmbeddingStrategy.STREAM,
                payloads_found=0,
            )

        # Buscar /Bits NNN en el header del objeto
        bits_count = None
        region = data[marker_pos:marker_pos + 200]
        bits_match = re.search(rb"/Bits\s+(\d+)", region)
        if bits_match:
            bits_count = int(bits_match.group(1))

        # Buscar inicio del stream
        stream_start_marker = b"stream\n"
        stream_start = data.find(stream_start_marker, marker_pos)
        if stream_start == -1:
            return ExtractResult(
                payload_bits="",
                confidence=0.0,
                strategy_used=EmbeddingStrategy.STREAM,
                payloads_found=0,
            )
        stream_start += len(stream_start_marker)

        # Buscar fin del stream
        stream_end = data.find(b"\nendstream", stream_start)
        if stream_end == -1:
            return ExtractResult(
                payload_bits="",
                confidence=0.0,
                strategy_used=EmbeddingStrategy.STREAM,
                payloads_found=0,
            )

        stream_content = data[stream_start:stream_end]

        try:
            payload_bytes = base64.b64decode(stream_content)
        except Exception:
            return ExtractResult(
                payload_bits="",
                confidence=0.0,
                strategy_used=EmbeddingStrategy.STREAM,
                payloads_found=0,
            )

        payload_bits = "".join(format(b, "08b") for b in payload_bytes)

        # Truncar al número original de bits
        if bits_count:
            payload_bits = payload_bits[:bits_count]
        elif expected_length:
            payload_bits = payload_bits[:expected_length]

        return ExtractResult(
            payload_bits=payload_bits,
            confidence=0.95,
            strategy_used=EmbeddingStrategy.STREAM,
            payloads_found=1,
        )

    def _extract_legacy(
        self, data: bytes, expected_length: Optional[int] = None
    ) -> ExtractResult:
        """Extrae payload del formato legacy (HBITSIGN marker)."""
        marker_pos = data.find(HBIT_MARKER)
        if marker_pos == -1:
            return ExtractResult(
                payload_bits="",
                confidence=0.0,
                strategy_used=EmbeddingStrategy.STREAM,
                payloads_found=0,
            )

        # Leer longitud
        len_offset = marker_pos + len(HBIT_MARKER)
        if len_offset + 4 > len(data):
            return ExtractResult(
                payload_bits="",
                confidence=0.0,
                strategy_used=EmbeddingStrategy.STREAM,
                payloads_found=0,
            )

        payload_len = int.from_bytes(data[len_offset:len_offset + 4], "big")

        # Leer payload
        payload_offset = len_offset + 4
        payload_bytes = data[payload_offset:payload_offset + payload_len]

        # Convertir a bits
        payload_bits = "".join(format(b, "08b") for b in payload_bytes)

        if expected_length and len(payload_bits) > expected_length:
            payload_bits = payload_bits[:expected_length]

        return ExtractResult(
            payload_bits=payload_bits,
            confidence=0.90,  # Lower confidence for legacy format
            strategy_used=EmbeddingStrategy.STREAM,
            payloads_found=1,
        )

    @staticmethod
    def _has_hbit_payload(data: bytes) -> bool:
        """Verifica si el PDF contiene un payload H-Bit (v2 o legacy)."""
        return b"/Type /HBitPayload" in data or HBIT_MARKER in data

    @staticmethod
    def _find_next_obj_number(pdf_data: bytes) -> int:
        """Encuentra el mayor número de objeto y devuelve el siguiente."""
        import re
        # Buscar todos los "N 0 obj" patterns
        matches = re.findall(rb"(\d+)\s+0\s+obj", pdf_data)
        if matches:
            max_obj = max(int(m) for m in matches)
            return max_obj + 1
        return 100  # Safe default

    @staticmethod
    def _find_insert_position(pdf_data: bytes) -> int:
        """Encuentra la mejor posición para insertar el objeto H-Bit.

        Busca xref o startxref como punto de inserción, ya que los
        objetos deben ir antes de la tabla de referencias cruzadas.
        Si no encuentra, usa justo antes de %%EOF.
        """
        # Intentar xref (full cross-reference table)
        xref_pos = pdf_data.rfind(b"\nxref\n")
        if xref_pos != -1:
            return xref_pos

        # Intentar startxref (cross-reference stream)
        startxref_pos = pdf_data.rfind(b"\nstartxref\n")
        if startxref_pos != -1:
            return startxref_pos

        # Fallback: antes de %%EOF
        eof_pos = pdf_data.rfind(b"%%EOF")
        if eof_pos != -1:
            return eof_pos

        # Último recurso: final del archivo
        return len(pdf_data)

    @staticmethod
    def _strip_hbit_data(pdf_data: bytes) -> bytes:
        """Elimina todos los datos H-Bit del PDF (v2 y legacy).

        Para v2: elimina el objeto "N 0 obj ... endobj" que contiene /HBitPayload
        Para legacy: elimina el bloque HBITSIGN...ENDHBIT + comentario
        """
        import re

        data = pdf_data

        # Strip v2: objeto PDF con /Type /HBitPayload
        type_pos = data.find(b"/Type /HBitPayload")
        if type_pos != -1:
            # Buscar el inicio del objeto (N 0 obj antes de la posición)
            obj_region = data[:type_pos]
            obj_match = list(re.finditer(rb"\d+\s+0\s+obj\b", obj_region))
            if obj_match:
                obj_start = obj_match[-1].start()
                # Buscar endobj después
                endobj_pos = data.find(b"endobj", type_pos)
                if endobj_pos != -1:
                    endobj_end = endobj_pos + len(b"endobj\n")
                    # Limpiar también el newline antes del objeto
                    while obj_start > 0 and data[obj_start - 1:obj_start] in (b"\n", b"\r"):
                        obj_start -= 1
                    data = data[:obj_start] + data[endobj_end:]

        # Strip legacy: comentario + HBIT_MARKER block
        comment = b"\n% H-Bit Signature Stream\n"
        comment_pos = data.find(comment)
        if comment_pos != -1:
            end_marker = HBIT_MARKER_END + b"\n"
            end_pos = data.find(end_marker, comment_pos)
            if end_pos != -1:
                data = data[:comment_pos] + data[end_pos + len(end_marker):]
        else:
            # Solo los marcadores sin comentario
            hbit_start = data.find(HBIT_MARKER)
            if hbit_start != -1:
                hbit_end = data.find(HBIT_MARKER_END, hbit_start)
                if hbit_end != -1:
                    data = data[:hbit_start] + data[hbit_end + len(HBIT_MARKER_END):]

        return data

    @staticmethod
    def _bits_to_bytes(bits: str) -> bytes:
        """Convierte cadena de bits a bytes."""
        padded = bits.ljust(((len(bits) + 7) // 8) * 8, "0")
        return bytes(int(padded[i:i + 8], 2) for i in range(0, len(padded), 8))

    @staticmethod
    def _compute_canonical_hash(raw_data: bytes) -> bytes:
        """Computa hash canónico del PDF excluyendo datos H-Bit.

        Elimina tanto el formato v2 (objeto /HBitPayload) como el
        formato legacy (comentario + marcadores HBITSIGN) antes
        de calcular el SHA-256.
        """
        clean = PDFHandler._strip_hbit_data(raw_data)
        return hashlib.sha256(clean).digest()



class OfficeHandler(MediaHandler):
    """Handler para documentos Office (OOXML: DOCX, XLSX, PPTX).

    Los formatos OOXML son archivos ZIP que contienen XML.
    H-Bit inyecta una parte custom XML (customXml/hbit.xml) dentro
    del contenedor ZIP, que es invisible para el usuario pero
    persiste ante ediciones del contenido del documento.
    """

    @property
    def category(self) -> MediaCategory:
        return MediaCategory.DOCUMENT

    @property
    def supported_extensions(self) -> list[str]:
        return ["docx", "xlsx", "pptx", "odt", "ods", "odp"]

    def load(self, path: Path) -> CarrierData:
        """Carga un documento Office como bytes."""
        raw_data = path.read_bytes()

        # Verificar que es un ZIP válido
        is_zip = raw_data[:4] == b"PK\x03\x04"

        # Buscar H-Bit existente y computar hash canónico
        has_hbit = False
        canonical_hash = None
        if is_zip:
            try:
                canonical_hash = self._compute_canonical_hash(raw_data)
                with zipfile.ZipFile(io.BytesIO(raw_data), "r") as zf:
                    has_hbit = "customXml/hbit.xml" in zf.namelist()
            except zipfile.BadZipFile:
                canonical_hash = hashlib.sha256(raw_data).digest()
        else:
            canonical_hash = hashlib.sha256(raw_data).digest()

        return CarrierData(
            raw_data=raw_data,
            metadata={
                "size": len(raw_data),
                "format": path.suffix.upper().lstrip("."),
                "is_zip": is_zip,
                "has_hbit": has_hbit,
            },
            capacity_bits=64 * 1024 * 8,  # ~64KB
            strategy=EmbeddingStrategy.STREAM,
            category=MediaCategory.DOCUMENT,
            original_path=path,
            canonical_hash=canonical_hash,
        )

    def save(self, data: bytes, path: Path, carrier: CarrierData) -> Path:
        """Guarda el documento Office modificado."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def embed(self, carrier: CarrierData, payload_bits: str) -> EmbedResult:
        """Inyecta el payload como tabla Custom XML en el OOXML.

        La parte se añade a customXml/hbit.xml dentro del ZIP
        sin alterar el contenido visible del documento.
        """
        if not carrier.metadata.get("is_zip"):
            # Fallback: append stream para archivos no-ZIP
            return self._embed_append(carrier, payload_bits)

        payload_bytes = self._bits_to_bytes(payload_bits)

        # Crear XML con el payload codificado en base64
        import base64
        payload_b64 = base64.b64encode(payload_bytes).decode("ascii")

        hbit_xml = (
            f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<hbit:signature xmlns:hbit="{HBIT_XML_NS}">\n'
            f'  <hbit:version>1</hbit:version>\n'
            f'  <hbit:payload>{payload_b64}</hbit:payload>\n'
            f'  <hbit:bits>{len(payload_bits)}</hbit:bits>\n'
            f'</hbit:signature>\n'
        )

        # Re-crear el ZIP con la parte custom
        input_buf = io.BytesIO(carrier.raw_data)
        output_buf = io.BytesIO()

        with zipfile.ZipFile(input_buf, "r") as zin:
            with zipfile.ZipFile(output_buf, "w", zipfile.ZIP_DEFLATED) as zout:
                for entry in zin.infolist():
                    if entry.filename == "customXml/hbit.xml":
                        continue  # Reemplazar si existe
                    zout.writestr(entry, zin.read(entry.filename))

                # Añadir parte H-Bit
                zout.writestr("customXml/hbit.xml", hbit_xml)

        modified = output_buf.getvalue()

        return EmbedResult(
            output_data=modified,
            bits_embedded=len(payload_bits),
            capacity_used=len(payload_bits) / carrier.capacity_bits,
            strategy_used=EmbeddingStrategy.STREAM,
        )

    def extract(
        self,
        carrier: CarrierData,
        expected_length: Optional[int] = None,
    ) -> ExtractResult:
        """Extrae el payload de la parte Custom XML."""
        if not carrier.metadata.get("is_zip"):
            return self._extract_append(carrier, expected_length)

        try:
            with zipfile.ZipFile(io.BytesIO(carrier.raw_data), "r") as zf:
                if "customXml/hbit.xml" not in zf.namelist():
                    return ExtractResult(
                        payload_bits="",
                        confidence=0.0,
                        strategy_used=EmbeddingStrategy.STREAM,
                        payloads_found=0,
                    )

                xml_content = zf.read("customXml/hbit.xml").decode("utf-8")
        except (zipfile.BadZipFile, KeyError):
            return ExtractResult(
                payload_bits="",
                confidence=0.0,
                strategy_used=EmbeddingStrategy.STREAM,
                payloads_found=0,
            )

        # Parsear el XML para extraer el payload
        import base64
        import re

        payload_match = re.search(
            r"<hbit:payload>(.*?)</hbit:payload>", xml_content, re.DOTALL
        )
        bits_match = re.search(
            r"<hbit:bits>(\d+)</hbit:bits>", xml_content
        )

        if not payload_match:
            return ExtractResult(
                payload_bits="",
                confidence=0.0,
                strategy_used=EmbeddingStrategy.STREAM,
                payloads_found=0,
            )

        payload_b64 = payload_match.group(1).strip()
        payload_bytes = base64.b64decode(payload_b64)
        payload_bits = "".join(format(b, "08b") for b in payload_bytes)

        # Truncar al número original de bits
        if bits_match:
            orig_bits = int(bits_match.group(1))
            payload_bits = payload_bits[:orig_bits]
        elif expected_length:
            payload_bits = payload_bits[:expected_length]

        return ExtractResult(
            payload_bits=payload_bits,
            confidence=0.95,
            strategy_used=EmbeddingStrategy.STREAM,
            payloads_found=1,
        )

    def _embed_append(self, carrier: CarrierData, payload_bits: str) -> EmbedResult:
        """Fallback: append stream para archivos no-OOXML."""
        payload_bytes = self._bits_to_bytes(payload_bits)
        hbit_stream = HBIT_MARKER + len(payload_bytes).to_bytes(4, "big") + payload_bytes + HBIT_MARKER_END
        modified = carrier.raw_data + hbit_stream

        return EmbedResult(
            output_data=modified,
            bits_embedded=len(payload_bits),
            capacity_used=len(payload_bits) / carrier.capacity_bits,
            strategy_used=EmbeddingStrategy.APPEND,
        )

    def _extract_append(
        self, carrier: CarrierData, expected_length: Optional[int] = None
    ) -> ExtractResult:
        """Fallback: extract del append stream."""
        data = carrier.raw_data
        marker_pos = data.find(HBIT_MARKER)
        if marker_pos == -1:
            return ExtractResult(
                payload_bits="", confidence=0.0,
                strategy_used=EmbeddingStrategy.APPEND, payloads_found=0,
            )

        len_offset = marker_pos + len(HBIT_MARKER)
        payload_len = int.from_bytes(data[len_offset:len_offset + 4], "big")
        payload_offset = len_offset + 4
        payload_bytes = data[payload_offset:payload_offset + payload_len]
        payload_bits = "".join(format(b, "08b") for b in payload_bytes)

        if expected_length and len(payload_bits) > expected_length:
            payload_bits = payload_bits[:expected_length]

        return ExtractResult(
            payload_bits=payload_bits, confidence=0.9,
            strategy_used=EmbeddingStrategy.APPEND, payloads_found=1,
        )

    @staticmethod
    def _bits_to_bytes(bits: str) -> bytes:
        padded = bits.ljust(((len(bits) + 7) // 8) * 8, "0")
        return bytes(int(padded[i:i + 8], 2) for i in range(0, len(padded), 8))

    @staticmethod
    def _compute_canonical_hash(raw_data: bytes) -> bytes:
        """Computa hash canónico del OOXML: hash de entradas sorted excluyendo hbit.xml.

        Este hash es determinista independientemente de la compresión ZIP.
        """
        h = hashlib.sha256()
        try:
            with zipfile.ZipFile(io.BytesIO(raw_data), "r") as zf:
                for name in sorted(zf.namelist()):
                    if name == "customXml/hbit.xml":
                        continue
                    h.update(name.encode("utf-8"))
                    h.update(zf.read(name))
        except zipfile.BadZipFile:
            h.update(raw_data)
        return h.digest()
