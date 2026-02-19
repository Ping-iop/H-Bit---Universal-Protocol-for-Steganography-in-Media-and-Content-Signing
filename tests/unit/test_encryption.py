"""
Tests unitarios para el módulo de cifrado H-Bit (Fase 6).

Verifica:
- Roundtrip de cifrado/descifrado con AES-256-GCM.
- Derivación de claves robusta (PBKDF2/Argon2).
- Integridad: detección de modificaciones en ciphertext/tag.
- Manejo de contraseñas incorrectas.
- Unicidad de salt/nonce.
"""

import pytest
import os
from hbit.core.encryption import HBitEncryptor, EncryptionError

class TestHBitEncryption:
    
    @pytest.fixture
    def encryptor(self):
        """Instancia del encriptador."""
        return HBitEncryptor()

    @pytest.fixture
    def sample_data(self):
        """Datos de prueba para cifrar."""
        return b"H-Bit Secret Payload Data - 2026"

    @pytest.fixture
    def passphrase(self):
        """Passphrase segura."""
        return "correct-horse-battery-staple"

    def test_encrypt_decrypt_roundtrip(self, encryptor, sample_data, passphrase):
        """Verifica que los datos se recuperan intactos."""
        encrypted = encryptor.encrypt(sample_data, passphrase)
        
        assert encrypted.ciphertext != sample_data
        assert len(encrypted.salt) == 16
        assert len(encrypted.nonce) == 12
        assert len(encrypted.tag) == 16
        
        decrypted = encryptor.decrypt(encrypted, passphrase)
        assert decrypted == sample_data

    def test_wrong_passphrase_fails(self, encryptor, sample_data, passphrase):
        """Verifica que una contraseña incorrecta lanza error."""
        encrypted = encryptor.encrypt(sample_data, passphrase)
        
        with pytest.raises(EncryptionError, match="Invalid passphrase"):
            # Intentar descifrar con contraseña incorrecta
            encryptor.decrypt(encrypted, "wrong-password")

    def test_tampered_ciphertext_fails(self, encryptor, sample_data, passphrase):
        """Verifica que la modificación del ciphertext se detecta (GCM auth)."""
        encrypted = encryptor.encrypt(sample_data, passphrase)
        
        # Modificar un byte del ciphertext
        tampered_cipher = bytearray(encrypted.ciphertext)
        tampered_cipher[0] ^= 0xFF  # Flip bits
        encrypted.ciphertext = bytes(tampered_cipher)
        
        with pytest.raises(EncryptionError, match="Decryption failed"):
            encryptor.decrypt(encrypted, passphrase)

    def test_tampered_tag_fails(self, encryptor, sample_data, passphrase):
        """Verifica que la modificación del tag se detecta."""
        encrypted = encryptor.encrypt(sample_data, passphrase)
        
        # Modificar un byte del tag
        tampered_tag = bytearray(encrypted.tag)
        tampered_tag[0] ^= 0xFF
        encrypted.tag = bytes(tampered_tag)
        
        with pytest.raises(EncryptionError):
            encryptor.decrypt(encrypted, passphrase)

    def test_salt_nonce_uniqueness(self, encryptor, sample_data, passphrase):
        """Verifica que dos cifrados idénticos producen salt/nonce distintos."""
        enc1 = encryptor.encrypt(sample_data, passphrase)
        enc2 = encryptor.encrypt(sample_data, passphrase)
        
        assert enc1.salt != enc2.salt
        assert enc1.nonce != enc2.nonce
        assert enc1.ciphertext != enc2.ciphertext  # Ciphertext cambia por nonce distinto

    def test_empty_passphrase(self, encryptor, sample_data):
        """Verifica comportamiento con passphrase vacía (debería funcionar o fallar según política)."""
        # H-Bit debería permitir passphrase vacía (aunque no recomendado) o gestionarlo
        # Asumiremos que es válida técnicamente
        passphrase = ""
        encrypted = encryptor.encrypt(sample_data, passphrase)
        decrypted = encryptor.decrypt(encrypted, passphrase)
        assert decrypted == sample_data


class TestPayloadEncryption:
    """Tests de integración de cifrado en HBitPayload."""

    @pytest.fixture
    def sample_payload(self):
        from hbit.core.signature import HBitPayload, PayloadFlags
        return HBitPayload.create(
            author_hash=b"A" * 32,
            content_hash=b"C" * 32,
            timestamp=123456789.0,
            flags=PayloadFlags.default()
        )

    def test_payload_encryption_roundtrip(self, sample_payload):
        """Verifica que un payload se cifra y descifra correctamente."""
        passphrase = "master-key-2026"
        
        # 1. Cifrar
        encrypted_bytes = sample_payload.encrypt_payload(passphrase)
        
        # Verificar estructura básica
        # Version(1) + Flags(1) + Salt(16) + Nonce(12) + Tag(16) + ...
        # (Min header encrypted payload)
        assert len(encrypted_bytes) > 2 + 16 + 12 + 16
        
        # Verificar flag IS_ENCRYPTED en el byte de flags
        from hbit.core.signature import PayloadFlags
        flags_byte = encrypted_bytes[1]
        assert flags_byte & PayloadFlags.IS_ENCRYPTED

        # 2. Descifrar
        from hbit.core.signature import HBitPayload
        decrypted_payload = HBitPayload.decrypt_payload(encrypted_bytes, passphrase)

        # Verificar integridad de datos
        assert decrypted_payload.author_hash == sample_payload.author_hash
        assert decrypted_payload.content_hash == sample_payload.content_hash
        assert decrypted_payload.timestamp == sample_payload.timestamp
        # Verificar que el flag IS_ENCRYPTED se eliminó del objeto final
        assert not (decrypted_payload.flags & PayloadFlags.IS_ENCRYPTED)

    def test_payload_wrong_passphrase(self, sample_payload):
        """Verifica fallo con clave incorrecta."""
        passphrase = "correct-key"
        encrypted_bytes = sample_payload.encrypt_payload(passphrase)
        
        from hbit.core.encryption import EncryptionError
        from hbit.core.signature import HBitPayload

        with pytest.raises(EncryptionError):
            HBitPayload.decrypt_payload(encrypted_bytes, "wrong-key")

    def test_legacy_payload_passthrough(self, sample_payload):
        """Verifica que payloads no cifrados se deserializan normalmente."""
        # Serializar normal (sin cifrar)
        plaintext_bytes = sample_payload.serialize()
        
        from hbit.core.signature import HBitPayload
        # decrypt_payload debería funcionar igual para no cifrados
        result = HBitPayload.decrypt_payload(plaintext_bytes, "any-key")
        
        assert result.author_hash == sample_payload.author_hash
