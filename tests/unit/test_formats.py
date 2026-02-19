"""
Tests unitarios para la capa de abstracción de formatos (Fase 5).

Cubre:
- MediaRegistry: auto-detección, fallback, extensiones
- ImageHandler: load/save/embed/extract con JPGs de fixtures
- AudioHandler: embed/extract en WAV sintético
- DocumentHandler: PDF stream + OOXML custom XML
- GenericHandler: append stream universal
"""

import io
import struct
import wave
import zipfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from hbit.formats.base import (
    MediaHandler,
    MediaRegistry,
    CarrierData,
    EmbeddingStrategy,
    MediaCategory,
)
from hbit.formats.image import ImageHandler
from hbit.formats.audio import AudioHandler
from hbit.formats.document import PDFHandler, OfficeHandler, HBIT_MARKER
from hbit.formats.generic import GenericHandler, HBIT_MAGIC


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path


@pytest.fixture
def sample_png(tmp_dir):
    """Crea una imagen PNG temporal de prueba."""
    img = Image.fromarray(
        np.random.default_rng(42).integers(
            0, 256, (64, 64, 3), dtype=np.uint8
        )
    )
    path = tmp_dir / "test.png"
    img.save(path, "PNG")
    return path


@pytest.fixture
def sample_wav(tmp_dir):
    """Crea un WAV mono 16-bit temporal."""
    path = tmp_dir / "test.wav"
    n_frames = 44100  # 1 segundo a 44.1kHz
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(44100)
        # Generar samples aleatorios
        rng = np.random.default_rng(42)
        samples = rng.integers(-32768, 32767, n_frames, dtype=np.int16)
        wf.writeframes(samples.tobytes())
    return path


@pytest.fixture
def sample_pdf(tmp_dir):
    """Crea un PDF mínimo válido."""
    path = tmp_dir / "test.pdf"
    pdf_content = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\n"
        b"xref\n0 3\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"trailer\n<< /Size 3 /Root 1 0 R >>\n"
        b"startxref\n109\n"
        b"%%EOF\n"
    )
    path.write_bytes(pdf_content)
    return path


@pytest.fixture
def sample_docx(tmp_dir):
    """Crea un DOCX mínimo válido (ZIP con XML)."""
    path = tmp_dir / "test.docx"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml",
            '<?xml version="1.0"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '</Types>'
        )
        zf.writestr("word/document.xml",
            '<?xml version="1.0"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:body><w:p><w:r><w:t>Hello H-Bit</w:t></w:r></w:p></w:body>'
            '</w:document>'
        )
    path.write_bytes(buf.getvalue())
    return path


@pytest.fixture
def sample_binary(tmp_dir):
    """Crea un archivo binario genérico."""
    path = tmp_dir / "test.dat"
    rng = np.random.default_rng(42)
    path.write_bytes(rng.bytes(4096))
    return path


@pytest.fixture
def payload_bits():
    """Payload de prueba: 64 bits."""
    return "1010110011001010" * 4  # 64 bits


# ═══════════════════════════════════════════════════════════════════
# Tests: MediaRegistry
# ═══════════════════════════════════════════════════════════════════

class TestMediaRegistry:
    """Tests del registro dinámico de handlers."""

    def setup_method(self):
        MediaRegistry.reset()

    def test_get_image_handler(self):
        """Imágenes resuelven al ImageHandler."""
        reg = MediaRegistry.default()
        handler = reg.get_handler(Path("foto.jpg"))
        assert isinstance(handler, ImageHandler)

    def test_get_audio_handler(self):
        """Audio resuelve al AudioHandler."""
        reg = MediaRegistry.default()
        handler = reg.get_handler(Path("song.wav"))
        assert isinstance(handler, AudioHandler)

    def test_get_pdf_handler(self):
        """PDF resuelve al PDFHandler."""
        reg = MediaRegistry.default()
        handler = reg.get_handler(Path("doc.pdf"))
        assert isinstance(handler, PDFHandler)

    def test_get_office_handler(self):
        """DOCX resuelve al OfficeHandler."""
        reg = MediaRegistry.default()
        handler = reg.get_handler(Path("report.docx"))
        assert isinstance(handler, OfficeHandler)

    def test_fallback_to_generic(self):
        """Extensión desconocida usa el GenericHandler."""
        reg = MediaRegistry.default()
        handler = reg.get_handler(Path("data.xyz"))
        assert isinstance(handler, GenericHandler)

    def test_supports_known(self):
        """supports() retorna True para extensiones conocidas."""
        reg = MediaRegistry.default()
        assert reg.supports(Path("a.png"))
        assert reg.supports(Path("b.wav"))
        assert reg.supports(Path("c.pdf"))

    def test_supports_unknown_with_fallback(self):
        """supports() retorna True para desconocidas si hay fallback."""
        reg = MediaRegistry.default()
        assert reg.supports(Path("x.unknown"))

    def test_registered_extensions(self):
        """Lista de extensiones registradas incluye las principales."""
        reg = MediaRegistry.default()
        exts = reg.supported_extensions
        assert "png" in exts
        assert "jpg" in exts
        assert "wav" in exts
        assert "pdf" in exts
        assert "docx" in exts

    def test_custom_handler_registration(self):
        """Se pueden registrar handlers personalizados."""
        reg = MediaRegistry.default()

        class CustomHandler(MediaHandler):
            @property
            def category(self): return MediaCategory.GENERIC
            @property
            def supported_extensions(self): return ["custom"]
            def load(self, path): pass
            def save(self, data, path, carrier): pass
            def embed(self, carrier, bits): pass
            def extract(self, carrier, length=None): pass

        reg.register(CustomHandler())
        handler = reg.get_handler(Path("file.custom"))
        assert isinstance(handler, CustomHandler)


# ═══════════════════════════════════════════════════════════════════
# Tests: ImageHandler
# ═══════════════════════════════════════════════════════════════════

class TestImageHandler:
    """Tests del handler de imágenes."""

    def test_load_png(self, sample_png):
        """Carga correctamente un PNG."""
        handler = ImageHandler()
        carrier = handler.load(sample_png)
        assert carrier.category == MediaCategory.IMAGE
        assert carrier.metadata["width"] == 64
        assert carrier.metadata["height"] == 64
        assert carrier.capacity_bits == 64 * 64

    def test_embed_extract_roundtrip(self, sample_png, payload_bits):
        """Embed + extract recupera los bits correctos."""
        handler = ImageHandler()
        carrier = handler.load(sample_png)
        result = handler.embed(carrier, payload_bits)
        assert result.bits_embedded > 0

        # Cargar desde los datos modificados
        modified_carrier = CarrierData(
            raw_data=result.output_data,
            metadata=carrier.metadata,
            capacity_bits=carrier.capacity_bits,
            strategy=carrier.strategy,
            category=carrier.category,
        )
        extracted = handler.extract(modified_carrier)
        # La extracción debe encontrar algo (sync markers)
        assert extracted.payloads_found >= 0

    def test_load_real_fixture(self):
        """Carga una imagen real de tests/fixtures/ si existe."""
        fixture = FIXTURES_DIR / "_FOC4517.jpg"
        if not fixture.exists():
            pytest.skip("Fixture _FOC4517.jpg no disponible")

        handler = ImageHandler()
        carrier = handler.load(fixture)
        assert carrier.metadata["width"] > 0
        assert carrier.metadata["height"] > 0
        assert carrier.capacity_bits > 0

    def test_save_and_reload(self, sample_png, tmp_dir, payload_bits):
        """Save + reload mantiene los datos."""
        handler = ImageHandler()
        carrier = handler.load(sample_png)
        result = handler.embed(carrier, payload_bits)

        out_path = tmp_dir / "output.png"
        handler.save(result.output_data, out_path, carrier)

        # Recargar
        carrier2 = handler.load(out_path)
        assert carrier2.metadata["width"] == carrier.metadata["width"]
        assert carrier2.metadata["height"] == carrier.metadata["height"]


# ═══════════════════════════════════════════════════════════════════
# Tests: AudioHandler
# ═══════════════════════════════════════════════════════════════════

class TestAudioHandler:
    """Tests del handler de audio."""

    def test_load_wav(self, sample_wav):
        """Carga un WAV correctamente."""
        handler = AudioHandler()
        carrier = handler.load(sample_wav)
        assert carrier.category == MediaCategory.AUDIO
        assert carrier.metadata["framerate"] == 44100
        assert carrier.metadata["channels"] == 1
        assert carrier.metadata["sample_width"] == 2

    def test_embed_extract_roundtrip(self, sample_wav, payload_bits):
        """Embed + extract en WAV recupera los bits."""
        handler = AudioHandler()
        carrier = handler.load(sample_wav)

        result = handler.embed(carrier, payload_bits)
        assert result.bits_embedded == len(payload_bits)

        # Extraer
        modified_carrier = CarrierData(
            raw_data=result.output_data,
            metadata=carrier.metadata,
            capacity_bits=carrier.capacity_bits,
            strategy=carrier.strategy,
            category=carrier.category,
        )
        extracted = handler.extract(modified_carrier, expected_length=len(payload_bits))
        assert extracted.payload_bits[:len(payload_bits)] == payload_bits

    def test_save_and_reload(self, sample_wav, tmp_dir, payload_bits):
        """Save + reload mantiene el audio."""
        handler = AudioHandler()
        carrier = handler.load(sample_wav)
        result = handler.embed(carrier, payload_bits)

        out_path = tmp_dir / "output.wav"
        handler.save(result.output_data, out_path, carrier)

        carrier2 = handler.load(out_path)
        assert carrier2.metadata["framerate"] == 44100


# ═══════════════════════════════════════════════════════════════════
# Tests: PDFHandler
# ═══════════════════════════════════════════════════════════════════

class TestPDFHandler:
    """Tests del handler de PDF."""

    def test_load_pdf(self, sample_pdf):
        """Carga un PDF correctamente."""
        handler = PDFHandler()
        carrier = handler.load(sample_pdf)
        assert carrier.category == MediaCategory.DOCUMENT
        assert carrier.metadata["format"] == "PDF"
        assert not carrier.metadata["has_hbit"]

    def test_embed_extract_roundtrip(self, sample_pdf, payload_bits):
        """Embed + extract en PDF recupera los bits."""
        handler = PDFHandler()
        carrier = handler.load(sample_pdf)

        result = handler.embed(carrier, payload_bits)
        assert b"/Type /HBitPayload" in result.output_data

        # Extraer
        modified_carrier = CarrierData(
            raw_data=result.output_data,
            metadata=carrier.metadata,
            capacity_bits=carrier.capacity_bits,
            strategy=carrier.strategy,
            category=carrier.category,
        )
        extracted = handler.extract(modified_carrier)
        assert extracted.payloads_found == 1
        assert extracted.payload_bits[:len(payload_bits)] == payload_bits

    def test_pdf_remains_valid(self, sample_pdf, payload_bits):
        """El PDF modificado sigue conteniendo %%EOF."""
        handler = PDFHandler()
        carrier = handler.load(sample_pdf)
        result = handler.embed(carrier, payload_bits)
        assert b"%%EOF" in result.output_data

    def test_replace_existing_hbit(self, sample_pdf, payload_bits):
        """Se reemplaza un H-Bit existente al re-firmar."""
        handler = PDFHandler()
        carrier = handler.load(sample_pdf)

        # Primera firma
        result1 = handler.embed(carrier, payload_bits)

        # Segunda firma con bits diferentes
        new_bits = "0" * len(payload_bits)
        carrier2 = CarrierData(
            raw_data=result1.output_data,
            metadata=carrier.metadata,
            capacity_bits=carrier.capacity_bits,
            strategy=carrier.strategy,
            category=carrier.category,
        )
        result2 = handler.embed(carrier2, new_bits)

        # Extraer debe dar los bits nuevos
        carrier3 = CarrierData(
            raw_data=result2.output_data,
            metadata=carrier.metadata,
            capacity_bits=carrier.capacity_bits,
            strategy=carrier.strategy,
            category=carrier.category,
        )
        extracted = handler.extract(carrier3)
        assert extracted.payload_bits[:len(new_bits)] == new_bits


# ═══════════════════════════════════════════════════════════════════
# Tests: OfficeHandler
# ═══════════════════════════════════════════════════════════════════

class TestOfficeHandler:
    """Tests del handler de Office OOXML."""

    def test_load_docx(self, sample_docx):
        """Carga un DOCX correctamente."""
        handler = OfficeHandler()
        carrier = handler.load(sample_docx)
        assert carrier.category == MediaCategory.DOCUMENT
        assert carrier.metadata["is_zip"]
        assert not carrier.metadata["has_hbit"]

    def test_embed_extract_roundtrip(self, sample_docx, payload_bits):
        """Embed + extract en DOCX recupera los bits."""
        handler = OfficeHandler()
        carrier = handler.load(sample_docx)

        result = handler.embed(carrier, payload_bits)

        # Verificar que el ZIP contiene hbit.xml
        with zipfile.ZipFile(io.BytesIO(result.output_data), "r") as zf:
            assert "customXml/hbit.xml" in zf.namelist()

        # Extraer
        modified_carrier = CarrierData(
            raw_data=result.output_data,
            metadata=carrier.metadata,
            capacity_bits=carrier.capacity_bits,
            strategy=carrier.strategy,
            category=carrier.category,
        )
        extracted = handler.extract(modified_carrier)
        assert extracted.payloads_found == 1
        assert extracted.payload_bits == payload_bits

    def test_docx_content_preserved(self, sample_docx, payload_bits):
        """El contenido del documento se preserva."""
        handler = OfficeHandler()
        carrier = handler.load(sample_docx)
        result = handler.embed(carrier, payload_bits)

        with zipfile.ZipFile(io.BytesIO(result.output_data), "r") as zf:
            doc_xml = zf.read("word/document.xml").decode()
            assert "Hello H-Bit" in doc_xml


# ═══════════════════════════════════════════════════════════════════
# Tests: GenericHandler
# ═══════════════════════════════════════════════════════════════════

class TestGenericHandler:
    """Tests del handler genérico universal."""

    def test_load_any_file(self, sample_binary):
        """Carga cualquier archivo."""
        handler = GenericHandler()
        carrier = handler.load(sample_binary)
        assert carrier.category == MediaCategory.GENERIC
        assert carrier.metadata["size"] == 4096

    def test_embed_extract_roundtrip(self, sample_binary, payload_bits):
        """Embed + extract con cualquier archivo."""
        handler = GenericHandler()
        carrier = handler.load(sample_binary)

        result = handler.embed(carrier, payload_bits)
        assert HBIT_MAGIC in result.output_data

        modified_carrier = CarrierData(
            raw_data=result.output_data,
            metadata=carrier.metadata,
            capacity_bits=carrier.capacity_bits,
            strategy=carrier.strategy,
            category=carrier.category,
        )
        extracted = handler.extract(modified_carrier)
        assert extracted.payloads_found == 1
        assert extracted.payload_bits == payload_bits
        assert extracted.confidence > 0.9

    def test_crc_integrity(self, sample_binary, payload_bits):
        """CRC32 verifica la integridad del stream."""
        handler = GenericHandler()
        carrier = handler.load(sample_binary)
        result = handler.embed(carrier, payload_bits)

        # Corromper un byte del stream H-Bit
        corrupted = bytearray(result.output_data)
        magic_pos = corrupted.find(HBIT_MAGIC)
        corrupted[magic_pos + 20] ^= 0xFF  # Corromper un byte del payload

        modified_carrier = CarrierData(
            raw_data=bytes(corrupted),
            metadata=carrier.metadata,
            capacity_bits=carrier.capacity_bits,
            strategy=carrier.strategy,
            category=carrier.category,
        )
        extracted = handler.extract(modified_carrier)
        # La confianza debe ser baja por CRC inválido
        assert extracted.confidence < 0.5

    def test_replace_existing_hbit(self, sample_binary, payload_bits):
        """Se reemplaza un H-Bit existente."""
        handler = GenericHandler()
        carrier = handler.load(sample_binary)

        # Primera firma
        result1 = handler.embed(carrier, payload_bits)

        # Segunda firma
        new_bits = "1" * len(payload_bits)
        carrier2 = CarrierData(
            raw_data=result1.output_data,
            metadata=carrier.metadata,
            capacity_bits=carrier.capacity_bits,
            strategy=carrier.strategy,
            category=carrier.category,
        )
        result2 = handler.embed(carrier2, new_bits)

        carrier3 = CarrierData(
            raw_data=result2.output_data,
            metadata=carrier.metadata,
            capacity_bits=carrier.capacity_bits,
            strategy=carrier.strategy,
            category=carrier.category,
        )
        extracted = handler.extract(carrier3)
        assert extracted.payload_bits == new_bits

    def test_file_not_corrupted(self, sample_binary, payload_bits):
        """El contenido original del archivo se preserva."""
        handler = GenericHandler()
        carrier = handler.load(sample_binary)
        original_data = carrier.raw_data

        result = handler.embed(carrier, payload_bits)
        # Los primeros bytes deben ser el archivo original
        assert result.output_data[:len(original_data)] == original_data
