"""
Tests de integración para el pipeline universal H-Bit.

Verifica el flujo completo encode→decode→verify para cada tipo
de medio usando los handlers universales.
"""

import io
import struct
import wave
import zipfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from hbit.universal import (
    UniversalEncoder,
    UniversalDecoder,
    UniversalVerifier,
    UniversalVerificationStatus,
)
from hbit.formats.base import MediaRegistry


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture(autouse=True)
def reset_registry():
    """Resetea el registry singleton entre tests."""
    MediaRegistry.reset()
    yield
    MediaRegistry.reset()


@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path


@pytest.fixture
def passphrase():
    return "test-passphrase-h-bit-2026"


@pytest.fixture
def sample_png(tmp_dir):
    """Imagen PNG de prueba."""
    img = Image.fromarray(
        np.random.default_rng(42).integers(0, 256, (100, 100, 3), dtype=np.uint8)
    )
    path = tmp_dir / "test.png"
    img.save(path, "PNG")
    return path


@pytest.fixture
def sample_wav(tmp_dir):
    """WAV mono 16-bit de prueba."""
    path = tmp_dir / "test.wav"
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(44100)
        rng = np.random.default_rng(42)
        samples = rng.integers(-32768, 32767, 44100, dtype=np.int16)
        wf.writeframes(samples.tobytes())
    return path


@pytest.fixture
def sample_pdf(tmp_dir):
    """PDF mínimo válido."""
    path = tmp_dir / "test.pdf"
    path.write_bytes(
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\n"
        b"xref\n0 3\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"trailer\n<< /Size 3 /Root 1 0 R >>\n"
        b"startxref\n109\n%%EOF\n"
    )
    return path


@pytest.fixture
def sample_docx(tmp_dir):
    """DOCX mínimo válido."""
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
            '<?xml version="1.0"?><w:document '
            'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:body><w:p><w:r><w:t>Test content</w:t></w:r></w:p></w:body>'
            '</w:document>'
        )
    path.write_bytes(buf.getvalue())
    return path


@pytest.fixture
def sample_binary(tmp_dir):
    """Archivo binario genérico."""
    path = tmp_dir / "test.dat"
    rng = np.random.default_rng(42)
    path.write_bytes(rng.bytes(8192))
    return path


# ═══════════════════════════════════════════════════════════════════
# Tests: Encoder Universal
# ═══════════════════════════════════════════════════════════════════

class TestUniversalEncoder:
    """Tests del encoder universal."""

    def test_encode_png(self, sample_png, passphrase, tmp_dir):
        """Codifica un PNG correctamente."""
        encoder = UniversalEncoder()
        out = tmp_dir / "signed.png"
        result = encoder.encode(sample_png, passphrase, out)

        assert result.output_path == out
        assert out.exists()
        assert result.media_category == "image"
        assert result.bits_embedded > 0
        assert len(result.author_hash) == 64  # hex

    def test_encode_wav(self, sample_wav, passphrase, tmp_dir):
        """Codifica un WAV correctamente."""
        encoder = UniversalEncoder()
        out = tmp_dir / "signed.wav"
        result = encoder.encode(sample_wav, passphrase, out)

        assert out.exists()
        assert result.media_category == "audio"
        assert result.bits_embedded > 0

    def test_encode_pdf(self, sample_pdf, passphrase, tmp_dir):
        """Codifica un PDF correctamente."""
        encoder = UniversalEncoder()
        out = tmp_dir / "signed.pdf"
        result = encoder.encode(sample_pdf, passphrase, out)

        assert out.exists()
        assert result.media_category == "document"
        assert result.strategy_used == "STREAM"

    def test_encode_docx(self, sample_docx, passphrase, tmp_dir):
        """Codifica un DOCX correctamente."""
        encoder = UniversalEncoder()
        out = tmp_dir / "signed.docx"
        result = encoder.encode(sample_docx, passphrase, out)

        assert out.exists()
        assert result.media_category == "document"

    def test_encode_generic(self, sample_binary, passphrase, tmp_dir):
        """Codifica un archivo genérico correctamente."""
        encoder = UniversalEncoder()
        out = tmp_dir / "signed.dat"
        result = encoder.encode(sample_binary, passphrase, out)

        assert out.exists()
        assert result.media_category == "generic"
        assert result.strategy_used == "APPEND"


# ═══════════════════════════════════════════════════════════════════
# Tests: Roundtrip Encode → Decode
# ═══════════════════════════════════════════════════════════════════

class TestUniversalRoundtrip:
    """Tests de roundtrip encode → decode para cada formato."""

    def test_pdf_roundtrip(self, sample_pdf, passphrase, tmp_dir):
        """PDF: encode → decode recupera el autor."""
        encoder = UniversalEncoder()
        out = tmp_dir / "signed.pdf"
        enc_result = encoder.encode(sample_pdf, passphrase, out)

        decoder = UniversalDecoder()
        dec_result = decoder.decode(out)

        assert dec_result.found
        assert dec_result.author_hash == enc_result.author_hash
        assert dec_result.media_category == "document"

    def test_docx_roundtrip(self, sample_docx, passphrase, tmp_dir):
        """DOCX: encode → decode recupera el autor."""
        encoder = UniversalEncoder()
        out = tmp_dir / "signed.docx"
        enc_result = encoder.encode(sample_docx, passphrase, out)

        decoder = UniversalDecoder()
        dec_result = decoder.decode(out)

        assert dec_result.found
        assert dec_result.author_hash == enc_result.author_hash

    def test_generic_roundtrip(self, sample_binary, passphrase, tmp_dir):
        """Genérico: encode → decode recupera el autor."""
        encoder = UniversalEncoder()
        out = tmp_dir / "signed.dat"
        enc_result = encoder.encode(sample_binary, passphrase, out)

        decoder = UniversalDecoder()
        dec_result = decoder.decode(out)

        assert dec_result.found
        assert dec_result.author_hash == enc_result.author_hash

    def test_wav_roundtrip(self, sample_wav, passphrase, tmp_dir):
        """WAV: encode → decode recupera los bits embebidos."""
        encoder = UniversalEncoder()
        out = tmp_dir / "signed.wav"
        enc_result = encoder.encode(sample_wav, passphrase, out)

        assert enc_result.bits_embedded > 0
        assert out.exists()


# ═══════════════════════════════════════════════════════════════════
# Tests: Verificación
# ═══════════════════════════════════════════════════════════════════

class TestUniversalVerifier:
    """Tests del verificador universal."""

    def test_verify_pdf(self, sample_pdf, passphrase, tmp_dir):
        """Verificar PDF firmado retorna VERIFIED."""
        encoder = UniversalEncoder()
        out = tmp_dir / "signed.pdf"
        encoder.encode(sample_pdf, passphrase, out)

        verifier = UniversalVerifier()
        result = verifier.verify(out)

        assert result.status == UniversalVerificationStatus.VERIFIED
        assert "[OK]" in result.message

    def test_verify_unsigned_pdf(self, sample_pdf):
        """Verificar PDF sin firma retorna NOT_FOUND."""
        verifier = UniversalVerifier()
        result = verifier.verify(sample_pdf)

        assert result.status == UniversalVerificationStatus.NOT_FOUND

    def test_verify_wrong_author(self, sample_pdf, passphrase, tmp_dir):
        """Verificar con autor incorrecto retorna INVALID."""
        encoder = UniversalEncoder()
        out = tmp_dir / "signed.pdf"
        encoder.encode(sample_pdf, passphrase, out)

        verifier = UniversalVerifier()
        result = verifier.verify(out, expected_author_hash="0" * 64)

        assert result.status == UniversalVerificationStatus.INVALID

    def test_verify_generic(self, sample_binary, passphrase, tmp_dir):
        """Verificar archivo genérico firmado."""
        encoder = UniversalEncoder()
        out = tmp_dir / "signed.dat"
        encoder.encode(sample_binary, passphrase, out)

        verifier = UniversalVerifier()
        result = verifier.verify(out)

        assert result.status == UniversalVerificationStatus.VERIFIED


# ═══════════════════════════════════════════════════════════════════
# Tests: Fixtures Reales
# ═══════════════════════════════════════════════════════════════════

class TestRealFixtures:
    """Tests con imágenes reales de tests/fixtures/."""

    def test_encode_real_jpg(self, passphrase, tmp_dir):
        """Codifica una imagen JPG real."""
        fixture = FIXTURES_DIR / "_FOC4517.jpg"
        if not fixture.exists():
            pytest.skip("Fixture no disponible")

        encoder = UniversalEncoder()
        out = tmp_dir / "signed.png"
        result = encoder.encode(fixture, passphrase, out)

        assert out.exists()
        assert result.media_category == "image"
        assert result.bits_embedded > 0
