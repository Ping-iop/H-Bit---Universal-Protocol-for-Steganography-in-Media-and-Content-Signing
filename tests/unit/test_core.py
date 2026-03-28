"""
Tests unitarios para el core del protocolo H-Bit.

Verifica el flujo completo: generación de claves → firmado → incrustación
→ extracción → verificación.
"""

import struct
import time

import numpy as np
import pytest

from hbit.core.crypto import (
    generate_key_pair,
    generate_author_hash,
    generate_sensor_noise,
    sign_payload,
    verify_signature,
    compute_content_hash,
    HBitKeyPair,
    AuthorIdentity,
)
from hbit.core.kdf import (
    derive_session_key,
    derive_image_key,
    derive_from_passphrase,
    generate_session_salt,
)
from hbit.core.signature import (
    HBitPayload,
    PayloadFlags,
    AUTHOR_HASH_LENGTH,
    CONTENT_HASH_LENGTH,
)
from hbit.core.sync import (
    SYNC_HEADER_BITS,
    SYNC_FOOTER_BITS,
    correlate_barker,
    find_sync_positions,
    find_payload_boundaries,
    wrap_payload_with_sync,
    BARKER_13,
)


# ═══════════════════════════════════════════════════════════════════
# Tests: crypto.py
# ═══════════════════════════════════════════════════════════════════

class TestCrypto:
    """Tests para el módulo criptográfico."""

    def test_generate_key_pair(self):
        """Los pares de claves Ed25519 son únicos."""
        kp1 = generate_key_pair()
        kp2 = generate_key_pair()
        assert kp1.export_public_pem() != kp2.export_public_pem()

    def test_export_pem_format(self):
        """Las claves exportadas tienen formato PEM válido."""
        kp = generate_key_pair()
        private_pem = kp.export_private_pem()
        public_pem = kp.export_public_pem()
        assert private_pem.startswith(b"-----BEGIN PRIVATE KEY-----")
        assert public_pem.startswith(b"-----BEGIN PUBLIC KEY-----")

    def test_generate_author_hash_deterministic_with_same_inputs(self):
        """El hash de autor es determinístico dado los mismos inputs."""
        kp = generate_key_pair()
        noise = generate_sensor_noise()
        ts = time.time()
        h1 = generate_author_hash(kp.private_key, "device-1", noise, ts)
        h2 = generate_author_hash(kp.private_key, "device-1", noise, ts)
        assert h1.author_hash == h2.author_hash

    def test_generate_author_hash_different_with_different_device(self):
        """Diferentes dispositivos producen hashes diferentes."""
        kp = generate_key_pair()
        noise = generate_sensor_noise()
        ts = time.time()
        h1 = generate_author_hash(kp.private_key, "device-1", noise, ts)
        h2 = generate_author_hash(kp.private_key, "device-2", noise, ts)
        assert h1.author_hash != h2.author_hash

    def test_author_hash_length(self):
        """El hash de autor tiene exactamente 32 bytes (SHA-256)."""
        kp = generate_key_pair()
        h = generate_author_hash(kp.private_key, "test-device")
        assert len(h.author_hash) == 32

    def test_sign_and_verify(self):
        """Firma + verificación funciona correctamente."""
        kp = generate_key_pair()
        payload = b"test payload data"
        signature = sign_payload(kp.private_key, payload)
        assert verify_signature(kp.public_key, payload, signature) is True

    def test_verify_fails_with_wrong_key(self):
        """La verificación falla con clave incorrecta."""
        kp1 = generate_key_pair()
        kp2 = generate_key_pair()
        payload = b"test payload data"
        signature = sign_payload(kp1.private_key, payload)
        assert verify_signature(kp2.public_key, payload, signature) is False

    def test_verify_fails_with_modified_payload(self):
        """La verificación falla si el payload fue modificado."""
        kp = generate_key_pair()
        payload = b"original payload"
        signature = sign_payload(kp.private_key, payload)
        assert verify_signature(kp.public_key, b"modified payload", signature) is False

    def test_content_hash_consistency(self):
        """El hash de contenido es consistente."""
        data = b"test image data" * 100
        h1 = compute_content_hash(data)
        h2 = compute_content_hash(data)
        assert h1 == h2
        assert len(h1) == 32


# ═══════════════════════════════════════════════════════════════════
# Tests: kdf.py
# ═══════════════════════════════════════════════════════════════════

class TestKDF:
    """Tests para el módulo de derivación de claves."""

    def test_session_key_uniqueness(self):
        """Cada sesión produce una clave diferente."""
        master = b"master_key_32_bytes_long_enough!!"
        dk1 = derive_session_key(master)
        dk2 = derive_session_key(master)
        assert dk1.key_material != dk2.key_material  # Salts diferentes

    def test_session_key_deterministic_with_salt(self):
        """Con el mismo salt, la derivación es determinística."""
        master = b"master_key_32_bytes_long_enough!!"
        salt = generate_session_salt()
        dk1 = derive_session_key(master, salt)
        dk2 = derive_session_key(master, salt)
        assert dk1.key_material == dk2.key_material

    def test_image_key_deterministic(self):
        """La clave por imagen es determinística."""
        master = b"master_key_32_bytes_long_enough!!"
        image_hash = b"\x00" * 32
        dk1 = derive_image_key(master, image_hash)
        dk2 = derive_image_key(master, image_hash)
        assert dk1.key_material == dk2.key_material

    def test_different_images_different_keys(self):
        """Diferentes imágenes producen claves diferentes."""
        master = b"master_key_32_bytes_long_enough!!"
        dk1 = derive_image_key(master, b"\x00" * 32)
        dk2 = derive_image_key(master, b"\xFF" * 32)
        assert dk1.key_material != dk2.key_material

    def test_passphrase_derivation(self):
        """La derivación desde passphrase es funcional."""
        dk = derive_from_passphrase("contraseña segura")
        assert len(dk.key_material) == 32

    def test_key_material_length(self):
        """Las claves derivadas tienen 32 bytes."""
        master = b"any_key_material"
        dk = derive_session_key(master)
        assert len(dk.key_material) == 32


# ═══════════════════════════════════════════════════════════════════
# Tests: signature.py
# ═══════════════════════════════════════════════════════════════════

class TestSignature:
    """Tests para la estructura del payload."""

    def test_payload_create(self):
        """Creación de payload con valores válidos."""
        author_hash = b"\x01" * 32
        content_hash = b"\x02" * 32
        payload = HBitPayload.create(author_hash=author_hash, content_hash=content_hash)
        assert payload.version == 1
        assert payload.author_hash == author_hash
        assert payload.content_hash == content_hash

    def test_payload_create_invalid_hash_length(self):
        """Rechaza hashes con longitud incorrecta."""
        with pytest.raises(ValueError, match="author_hash"):
            HBitPayload.create(author_hash=b"\x01" * 16)

    def test_serialize_deserialize_roundtrip(self):
        """Serialización → deserialización preserva los campos."""
        author_hash = b"\xAA" * 32
        content_hash = b"\xBB" * 32
        original = HBitPayload.create(
            author_hash=author_hash,
            content_hash=content_hash,
        )
        serialized = original.serialize_core()
        restored = HBitPayload.deserialize_core(serialized)

        assert restored.version == original.version
        assert restored.author_hash == author_hash
        assert restored.content_hash == content_hash
        assert abs(restored.timestamp - original.timestamp) < 0.001

    def test_to_binary_string(self):
        """La representación binaria del core tiene la longitud correcta."""
        payload = HBitPayload.create(author_hash=b"\x00" * 32)
        # serialize_core() siempre produce 107 bytes (sin compresión)
        core = payload.serialize_core()
        core_binary = "".join(format(byte, "08b") for byte in core)
        # Core: 1(ver) + 1(flags) + 1(origin) + 32(author) + 32(content)
        #      + 8(timestamp) + 32(ai_model_id) = 107 bytes = 856 bits
        assert len(core_binary) == 107 * 8

    def test_flags_default(self):
        """Los flags por defecto incluyen hash de contenido y ECC."""
        flags = PayloadFlags.default()
        assert flags & PayloadFlags.HAS_CONTENT_HASH
        assert flags & PayloadFlags.HAS_ECC
        assert flags & PayloadFlags.USES_KDF


# ═══════════════════════════════════════════════════════════════════
# Tests: sync.py
# ═══════════════════════════════════════════════════════════════════

class TestSync:
    """Tests para los marcadores de sincronización Barker."""

    def test_barker_header_footer_different(self):
        """Header y footer son diferentes."""
        assert SYNC_HEADER_BITS != SYNC_FOOTER_BITS

    def test_correlation_perfect_match(self):
        """La correlación perfecta produce valor 1.0."""
        signal = BARKER_13.copy()
        correlation = correlate_barker(signal, BARKER_13)
        assert abs(correlation[0] - 1.0) < 0.01

    def test_find_sync_position_exact(self):
        """Encuentra el header en una posición conocida."""
        # Construir señal: ruido + header + payload + footer
        noise = "0" * 50
        payload = "1" * 20
        bit_stream = noise + SYNC_HEADER_BITS + payload + SYNC_FOOTER_BITS + noise

        positions = find_sync_positions(bit_stream, threshold=0.95, search_header=True)
        assert 50 in positions

    def test_find_payload_boundaries(self):
        """Encuentra los límites del payload correctamente."""
        noise = "0" * 30
        payload = "10110011" * 5  # 40 bits
        bit_stream = noise + SYNC_HEADER_BITS + payload + SYNC_FOOTER_BITS + noise

        boundaries = find_payload_boundaries(bit_stream, threshold=0.85)
        assert len(boundaries) >= 1
        start, end = boundaries[0]
        extracted = bit_stream[start:end]
        assert extracted == payload

    def test_wrap_payload(self):
        """El wrap agrega header y footer correctamente."""
        payload = "101010"
        wrapped = wrap_payload_with_sync(payload)
        assert wrapped.startswith(SYNC_HEADER_BITS)
        assert wrapped.endswith(SYNC_FOOTER_BITS)
        assert payload in wrapped

    def test_multiple_copies_detected(self):
        """Detecta múltiples copias del payload."""
        payload = "10101010"
        wrapped = wrap_payload_with_sync(payload)
        bit_stream = wrapped + "0" * 10 + wrapped + "0" * 10

        boundaries = find_payload_boundaries(bit_stream, threshold=0.85)
        assert len(boundaries) >= 2


# ═══════════════════════════════════════════════════════════════════
# Tests: Integración LSB
# ═══════════════════════════════════════════════════════════════════

class TestLSBIntegration:
    """Tests de integración para el motor LSB."""

    @pytest.fixture
    def sample_image(self):
        """Genera una imagen sintética de prueba (256×256 RGB)."""
        rng = np.random.default_rng(42)
        return rng.integers(0, 256, size=(256, 256, 3), dtype=np.uint8)

    def test_encode_decode_roundtrip(self, sample_image):
        """El payload se puede incrustar y extraer correctamente."""
        from hbit.encoders.lsb import encode_lsb, decode_lsb
        from hbit.core.sync import wrap_payload_with_sync

        payload = "10110011" * 8  # 64 bits
        wrapped = wrap_payload_with_sync(payload)

        # Codificar
        result = encode_lsb(sample_image, wrapped, channel=2)
        assert result.bits_embedded > 0
        assert result.units_embedded >= 1

        # Decodificar
        decoded = decode_lsb(result.encoded_image, channel=2)
        assert decoded.payloads_found >= 1

    def test_lsb_non_destructive(self, sample_image):
        """La modificación LSB cambia como máximo ±1 por píxel."""
        from hbit.encoders.lsb import encode_lsb
        from hbit.core.sync import wrap_payload_with_sync

        payload = "11001100" * 4
        wrapped = wrap_payload_with_sync(payload)

        result = encode_lsb(sample_image, wrapped, channel=2)

        # La diferencia máxima debe ser ±1 en el canal modificado
        diff = np.abs(
            result.encoded_image[:, :, 2].astype(np.int16)
            - sample_image[:, :, 2].astype(np.int16)
        )
        assert diff.max() <= 1

    def test_other_channels_unchanged(self, sample_image):
        """Los canales no utilizados permanecen intactos."""
        from hbit.encoders.lsb import encode_lsb
        from hbit.core.sync import wrap_payload_with_sync

        payload = "10101010"
        wrapped = wrap_payload_with_sync(payload)

        result = encode_lsb(sample_image, wrapped, channel=2)

        # Canales R y G no deben cambiar
        np.testing.assert_array_equal(
            result.encoded_image[:, :, 0], sample_image[:, :, 0]
        )
        np.testing.assert_array_equal(
            result.encoded_image[:, :, 1], sample_image[:, :, 1]
        )


# ═══════════════════════════════════════════════════════════════════
# Tests: Análisis
# ═══════════════════════════════════════════════════════════════════

class TestAnalysis:
    """Tests para los módulos de análisis."""

    @pytest.fixture
    def sample_image(self):
        rng = np.random.default_rng(42)
        return rng.integers(0, 256, size=(256, 256, 3), dtype=np.uint8)

    def test_channel_entropy_range(self, sample_image):
        """La entropía está en el rango [0, 8]."""
        from hbit.analysis.entropy import analyze_channel_entropy

        entropy = analyze_channel_entropy(sample_image)
        for val in entropy.values:
            assert 0.0 <= val <= 8.0

    def test_random_image_high_entropy(self, sample_image):
        """Una imagen aleatoria tiene alta entropía (~8 bits)."""
        from hbit.analysis.entropy import analyze_channel_entropy

        entropy = analyze_channel_entropy(sample_image)
        for val in entropy.values:
            assert val > 7.0  # Imagen aleatoria → entropía cerca de 8

    def test_density_map_shape(self, sample_image):
        """El mapa de densidad tiene las dimensiones correctas."""
        from hbit.analysis.entropy import generate_density_map

        density = generate_density_map(sample_image, channel=2, block_size=8)
        assert density.shape == (256 // 8, 256 // 8)

    def test_channel_selector(self, sample_image):
        """El selector de canal devuelve un canal válido."""
        from hbit.analysis.channel_selector import select_optimal_channel

        result = select_optimal_channel(sample_image)
        assert result.selected_channel in (0, 1, 2)
        assert len(result.reason) > 0

    def test_content_hash_excludes_channel(self, sample_image):
        """El hash de contenido es diferente al excluir canales diferentes."""
        from hbit.analysis.integrity import compute_content_hash

        hash_excl_r = compute_content_hash(sample_image, exclude_channel=0)
        hash_excl_b = compute_content_hash(sample_image, exclude_channel=2)
        assert hash_excl_r != hash_excl_b
