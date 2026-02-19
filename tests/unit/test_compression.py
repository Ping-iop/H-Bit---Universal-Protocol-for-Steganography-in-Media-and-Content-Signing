"""
Tests unitarios para la compresión zlib en HBitPayload.
"""

import os
import struct
import pytest
from hbit.core.signature import HBitPayload, PayloadFlags

class TestPayloadCompression:

    def test_compression_low_entropy(self):
        """Verifica que la compresión se activa con datos de baja entropía."""
        # Crear payload con mucha redundancia (nulos)
        # Nota: author_hash y content_hash son 32 bytes c/u.
        # ecc_parity puede ser grande.
        payload = HBitPayload.create(
            author_hash=b"\x00" * 32, # Muy comprimible
            content_hash=b"\x00" * 32, # Muy comprimible
        )
        # Añadir ECC grande y redundante
        payload.ecc_parity = b"A" * 1000 # 1KB de 'A's
        payload.flags |= PayloadFlags.HAS_ECC

        serialized = payload.serialize()
        
        # Debe ser mucho menor que 1000 bytes
        assert len(serialized) < 100
        
        # Verificar flag IS_COMPRESSED en el header serializado
        version, flags_int = struct.unpack_from("!BB", serialized, 0)
        assert flags_int & PayloadFlags.IS_COMPRESSED
        
        # Roundtrip
        deserialized = HBitPayload.deserialize_core(serialized)
        # deserialize_core restaura el objeto, pero no carga ECC/Signature por defecto
        # porque serialize_core solo serializa el core.
        # Espera, deserialize_core solo lee el CORE de 74 bytes tras descomprimir.
        # Si comprimí TODO (incluido ECC), deserialize_core descomprime TODO, lee los 74 bytes iniciales y descarta el resto.
        # Esto es correcto para HBitPayload.deserialize_core.
        # Pero mi test quiere verificar que TODO el contenido se recupera si implementara deserialize_full?
        # Actualmente no tengo deserialize_full, pero HBitPayload.deserialize_core ignora el resto.
        
        # Lo importante es que deserialice bien el core.
        assert deserialized.author_hash == payload.author_hash
        assert deserialized.timestamp == payload.timestamp
        # Y que NO tenga flag IS_COMPRESSED en el objeto reconstruido
        assert not (deserialized.flags & PayloadFlags.IS_COMPRESSED)

    def test_compression_high_entropy(self):
        """Verifica que NO se comprime si los datos son aleatorios."""
        payload = HBitPayload.create(
            author_hash=os.urandom(32),
            content_hash=os.urandom(32),
        )
        # ECC aleatorio
        payload.ecc_parity = os.urandom(100)
        payload.flags |= PayloadFlags.HAS_ECC

        serialized = payload.serialize()
        
        # Headers (2) + CoreHashes (64) + Time (8) + ECCLen (2) + ECC (100) = ~176 bytes
        # Si zlib comprime random, añade overhead. Así que len > original.
        # Mi lógica rechaza compresión si len_compressed >= len_raw.
        
        # Verificar header
        version, flags_int = struct.unpack_from("!BB", serialized, 0)
        assert not (flags_int & PayloadFlags.IS_COMPRESSED)
        
        # Roundtrip
        deserialized = HBitPayload.deserialize_core(serialized)
        assert deserialized.author_hash == payload.author_hash

    def test_compression_with_encryption(self):
        """Verifica compresión + cifrado (compresión ocurre antes)."""
        passphrase = "secure-passphrase"
        
        payload = HBitPayload.create(author_hash=b"\x00"*32)
        payload.ecc_parity = b"B" * 500
        payload.flags |= PayloadFlags.HAS_ECC
        
        # 1. Encrypt (internamente serializa -> comprime -> cifra)
        encrypted_bytes = payload.encrypt_payload(passphrase)
        
        # Header del paquete cifrado tiene IS_ENCRYPTED
        ver, flags = struct.unpack_from("!BB", encrypted_bytes, 0)
        assert flags & PayloadFlags.IS_ENCRYPTED
        # No necesariamente tiene IS_COMPRESSED en el header EXTERNO, 
        # porque encrypt_payload construye el header externo basado en self.flags.
        # self.flags NO tiene IS_COMPRESSED (es feature de transporte interno).
        assert not (flags & PayloadFlags.IS_COMPRESSED)

        # 2. Decrypt
        decrypted_payload = HBitPayload.decrypt_payload(encrypted_bytes, passphrase)
        
        assert decrypted_payload.author_hash == payload.author_hash
        assert decrypted_payload.timestamp == payload.timestamp

