"""
Tests de integración para el pipeline universal cifrado (Fase 6).

Verifica el flujo completo encode(encrypt=True) → decode(passphrase) → verify.
"""

from pathlib import Path
import struct
import pytest
from hbit.universal import (
    UniversalEncoder,
    UniversalDecoder,
    UniversalVerifier,
    UniversalVerificationStatus,
)
from hbit.formats.base import MediaRegistry
from hbit.core.encryption import EncryptionError

# Fixtures mínimos copiados de test_universal.py (o referenciados si movieramos a conftest)
@pytest.fixture(autouse=True)
def reset_registry():
    MediaRegistry.reset()
    yield
    MediaRegistry.reset()

@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path

@pytest.fixture
def passphrase():
    return "test-passphrase-h-bit-2026-secure"

@pytest.fixture
def sample_pdf(tmp_dir):
    path = tmp_dir / "test.pdf"
    path.write_bytes(b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
                     b"2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\n"
                     b"xref\n0 3\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n"
                     b"trailer\n<< /Size 3 /Root 1 0 R >>\nstartxref\n109\n%%EOF\n")
    return path

class TestUniversalEncryptionFlow:
    """Tests del flujo universal con cifrado."""

    def test_pdf_encrypted_roundtrip(self, sample_pdf, passphrase, tmp_dir):
        """PDF: encode(encrypt=True) → decode(passphrase) funciona."""
        encoder = UniversalEncoder()
        out = tmp_dir / "signed_enc.pdf"
        
        # 1. Encode con cifrado
        result = encoder.encode(sample_pdf, passphrase, out, encrypt=True)
        assert result.bits_embedded > 0

        # 2. Decode SIN passphrase (retorna payload cifrado pero interpretado como basura)
        decoder = UniversalDecoder()
        # El decoder lee el header (Version+Flags) correctamente porque son plaintext.
        # Luego lee hashes basura.
        dec_no_pass = decoder.decode(out)
        assert dec_no_pass.found
        # Verificar que tiene flag IS_ENCRYPTED
        from hbit.core.signature import PayloadFlags
        assert dec_no_pass.payload.flags & PayloadFlags.IS_ENCRYPTED
        # Y que el author_hash no coincide con la versión descifrada correctamente
        # (Aunque podría coincidir por colisión astronómica, es improbable)
        # dec_pass se calcula después.

        # 3. Decode CON passphrase (debe funcionar)
        dec_pass = decoder.decode(out, passphrase=passphrase)
        assert dec_pass.found
        assert dec_pass.author_hash == result.author_hash
        
        # Confirmar que la versión sin pass era diferente (basura)
        assert dec_no_pass.author_hash != dec_pass.author_hash

    def test_verify_encrypted_success(self, sample_pdf, passphrase, tmp_dir):
        """Verificación exitosa de archivo cifrado."""
        encoder = UniversalEncoder()
        out = tmp_dir / "verified_enc.pdf"
        encoder.encode(sample_pdf, passphrase, out, encrypt=True)

        verifier = UniversalVerifier()
        result = verifier.verify(out, passphrase=passphrase)
        
        assert result.status == UniversalVerificationStatus.VERIFIED

    def test_verify_encrypted_wrong_pass(self, sample_pdf, passphrase, tmp_dir):
        """Verificación falla con contraseña incorrecta."""
        encoder = UniversalEncoder()
        out = tmp_dir / "wrong_pass.pdf"
        encoder.encode(sample_pdf, passphrase, out, encrypt=True)

        verifier = UniversalVerifier()
        # Contraseña incorrecta -> Decryption failed -> NOT_FOUND (debido a catch genérico en decode)
        result = verifier.verify(out, passphrase="wrong-password")
        
        assert result.status == UniversalVerificationStatus.NOT_FOUND

    def test_verify_encrypted_no_pass(self, sample_pdf, passphrase, tmp_dir):
        """Verificación falla sin contraseña (integritad comprometida)."""
        encoder = UniversalEncoder()
        out = tmp_dir / "no_pass.pdf"
        encoder.encode(sample_pdf, passphrase, out, encrypt=True)

        verifier = UniversalVerifier()
        # Sin contraseña -> Lee basura -> Hash no coincide -> TAMPERED
        result = verifier.verify(out)
        
        assert result.status == UniversalVerificationStatus.TAMPERED

