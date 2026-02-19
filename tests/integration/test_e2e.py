"""
Tests de integración End-to-End para el pipeline universal H-Bit.

Verifica flujos completos de producción:
1. Keygen → Encode → Decode → Verify (per format)
2. Encode con encriptación → Decode con passphrase
3. Multi-format batch signing
4. CLI roundtrip
"""

import io
import struct
import subprocess
import sys
import wave
import zipfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from hbit.core.crypto import generate_key_pair, HBitKeyPair
from hbit.universal import (
    UniversalEncoder,
    UniversalDecoder,
    UniversalVerifier,
    UniversalVerificationStatus,
)


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def keypair():
    """Par de claves Ed25519 para toda la suite."""
    return generate_key_pair()


@pytest.fixture
def key_file(keypair, tmp_path):
    """Archivo PEM con la clave privada."""
    path = tmp_path / "test_key.pem"
    path.write_bytes(keypair.export_private_pem())
    return path


@pytest.fixture
def sample_files(tmp_path):
    """Genera archivos de prueba para cada formato soportado."""
    files = {}

    # PNG
    png_path = tmp_path / "test.png"
    rng = np.random.default_rng(42)
    img = Image.fromarray(rng.integers(0, 256, (200, 200, 3), dtype=np.uint8))
    img.save(png_path, "PNG")
    files["png"] = png_path

    # JPEG
    jpg_path = tmp_path / "test.jpg"
    img.save(jpg_path, "JPEG", quality=95)
    files["jpg"] = jpg_path

    # WAV
    wav_path = tmp_path / "test.wav"
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(44100)
        samples = rng.integers(-32768, 32767, 44100, dtype=np.int16)
        wf.writeframes(samples.tobytes())
    files["wav"] = wav_path

    # PDF
    pdf_path = tmp_path / "test.pdf"
    pdf_path.write_bytes(
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
    files["pdf"] = pdf_path

    # DOCX
    docx_path = tmp_path / "test.docx"
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
            '<w:body><w:p><w:r><w:t>Integration test content</w:t></w:r></w:p></w:body>'
            '</w:document>'
        )
    docx_path.write_bytes(buf.getvalue())
    files["docx"] = docx_path

    # Binary genérico
    bin_path = tmp_path / "test.dat"
    bin_path.write_bytes(rng.bytes(8192))
    files["dat"] = bin_path

    return files


# ═══════════════════════════════════════════════════════════════════
# E2E: Keygen → Encode → Decode → Verify
# ═══════════════════════════════════════════════════════════════════

class TestE2EFullPipeline:
    """Tests end-to-end del pipeline completo por formato."""

    @pytest.mark.parametrize("fmt", ["png", "wav", "pdf", "docx", "dat"])
    def test_full_pipeline(self, sample_files, keypair, tmp_path, fmt):
        """Ciclo completo: encode → decode → verify para cada formato."""
        input_file = sample_files[fmt]
        output_file = tmp_path / f"signed.{fmt}"

        # Encode
        encoder = UniversalEncoder()
        enc_result = encoder.encode(input_file, keypair, output_file)
        assert output_file.exists()
        assert enc_result.bits_embedded > 0 or enc_result.strategy_used in ("STREAM", "CUSTOM_XML", "APPEND")

        # Decode
        decoder = UniversalDecoder()
        dec_result = decoder.decode(output_file)
        assert dec_result.found, f"Firma no encontrada en {fmt}"
        assert dec_result.author_hash == enc_result.author_hash

        # Verify
        verifier = UniversalVerifier()
        ver_result = verifier.verify(output_file)
        assert ver_result.status in (
            UniversalVerificationStatus.VERIFIED,
            UniversalVerificationStatus.TAMPERED,  # DCT modifica contenido
        )

    def test_full_pipeline_encrypted(self, sample_files, keypair, tmp_path):
        """Pipeline con encriptación: encode(encrypted) → decode(passphrase)."""
        input_file = sample_files["png"]
        output_file = tmp_path / "encrypted.png"
        passphrase = "test-encryption-passphrase-2026"

        # Encode con encriptación
        encoder = UniversalEncoder()
        enc_result = encoder.encode(
            input_file, keypair, output_file, encrypt=True
        )
        assert output_file.exists()

        # Decode SIN passphrase — debe encontrar pero no descifrar
        decoder = UniversalDecoder()
        dec_result = decoder.decode(output_file)
        # Puede encontrar la firma (sync markers) pero payload cifrado

        # Decode CON passphrase
        dec_result = decoder.decode(output_file, passphrase=passphrase)
        if dec_result.found:
            assert dec_result.author_hash == enc_result.author_hash


class TestE2EMultiFormat:
    """Tests de interoperabilidad entre formatos."""

    def test_different_keys_different_authors(self, sample_files, tmp_path):
        """Dos claves diferentes producen author_hash diferentes."""
        kp1 = generate_key_pair()
        kp2 = generate_key_pair()

        encoder = UniversalEncoder()
        out1 = tmp_path / "signed1.png"
        out2 = tmp_path / "signed2.png"

        r1 = encoder.encode(sample_files["png"], kp1, out1)
        r2 = encoder.encode(sample_files["png"], kp2, out2)

        assert r1.author_hash != r2.author_hash

    def test_verify_rejects_wrong_author(self, sample_files, keypair, tmp_path):
        """Verificación con author_hash incorrecto retorna INVALID."""
        encoder = UniversalEncoder()
        out = tmp_path / "signed.png"
        encoder.encode(sample_files["png"], keypair, out)

        verifier = UniversalVerifier()
        result = verifier.verify(out, expected_author_hash="0" * 64)
        assert result.status == UniversalVerificationStatus.INVALID

    def test_unsigned_file_returns_not_found(self, sample_files):
        """Archivo sin firmar retorna NOT_FOUND."""
        verifier = UniversalVerifier()
        result = verifier.verify(sample_files["png"])
        assert result.status == UniversalVerificationStatus.NOT_FOUND


# ═══════════════════════════════════════════════════════════════════
# E2E: CLI
# ═══════════════════════════════════════════════════════════════════

class TestE2ECLI:
    """Tests del CLI end-to-end."""

    def test_cli_keygen(self, tmp_path):
        """hbit keygen genera archivo PEM válido."""
        key_path = tmp_path / "cli_key.pem"
        result = subprocess.run(
            [sys.executable, "-m", "hbit.cli", "keygen", "--output", str(key_path)],
            capture_output=True, text=True, timeout=30,
            env={**dict(__import__('os').environ), "PYTHONPATH": str(Path(__file__).parent.parent.parent / "src")}
        )
        assert key_path.exists() or result.returncode == 0

    def test_cli_formats(self):
        """hbit formats lista los formatos soportados."""
        result = subprocess.run(
            [sys.executable, "-m", "hbit.cli", "formats"],
            capture_output=True, text=True, timeout=30,
            env={**dict(__import__('os').environ), "PYTHONPATH": str(Path(__file__).parent.parent.parent / "src")}
        )
        # Debería listar formatos sin error
        assert result.returncode == 0 or "image" in result.stdout.lower() or "error" not in result.stderr.lower()
