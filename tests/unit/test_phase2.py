"""
Tests unitarios para la Fase 2: Resistencia Analógica.

Verifica: motor DCT, Reed-Solomon ECC, tiling, anchor grid,
encoder híbrido LSB+DCT.
"""

import numpy as np
import pytest

from hbit.encoders.dct import encode_dct, decode_dct, MID_FREQ_POSITIONS
from hbit.encoders.hybrid import encode_hybrid, decode_hybrid
from hbit.resilience.ecc import encode_ecc, decode_ecc, compute_optimal_nsym
from hbit.resilience.tiling import (
    compute_tile_layout,
    generate_interleaved_sequence,
    deinterleave_sequence,
)
from hbit.resilience.anchor_grid import (
    compute_anchor_grid,
    inject_anchor_grid,
    detect_anchor_grid,
)
from hbit.analysis.jnd import compute_jnd_mask, compute_max_embedding_capacity


@pytest.fixture
def sample_image():
    """Imagen sintética 256×256 para pruebas."""
    rng = np.random.default_rng(42)
    return rng.integers(0, 256, size=(256, 256, 3), dtype=np.uint8)


@pytest.fixture
def gradient_image():
    """Imagen con gradiente suave (peor caso para steganografía)."""
    h, w = 256, 256
    img = np.zeros((h, w, 3), dtype=np.uint8)
    for y in range(h):
        for x in range(w):
            img[y, x] = [x, y, (x + y) // 2]
    return img


# ═══════════════════════════════════════════════════════════════════
# Tests: DCT Encoder/Decoder
# ═══════════════════════════════════════════════════════════════════

class TestDCTEncoder:
    """Tests para el motor DCT."""

    def test_dct_encode_decode_roundtrip(self, sample_image):
        """El payload DCT se puede codificar y decodificar."""
        payload = "10110011" * 8  # 64 bits
        result = encode_dct(sample_image, payload, channel=1, strength=30.0, use_jnd=False)

        assert result.bits_embedded >= len(payload)
        assert result.blocks_modified > 0

        decoded = decode_dct(result.encoded_image, channel=1, strength=30.0)
        # Los primeros bits deben coincidir
        first_bits = decoded.payload_bits[:len(payload)]
        matching = sum(1 for a, b in zip(first_bits, payload) if a == b)
        assert matching / len(payload) > 0.7  # >70% de coincidencia

    def test_dct_preserves_image_quality(self, sample_image):
        """La incrustación DCT no produce cambios drásticos."""
        payload = "10101010" * 4
        result = encode_dct(sample_image, payload, channel=1, strength=20.0, use_jnd=False)

        # El PSNR debe ser razonable (>30 dB típicamente)
        diff = (result.encoded_image.astype(np.float64) - sample_image.astype(np.float64))
        mse = np.mean(diff ** 2)
        assert mse < 100  # MSE razonable

    def test_dct_other_channels_unchanged(self, sample_image):
        """Canales no utilizados permanecen intactos."""
        payload = "11001100" * 4
        result = encode_dct(sample_image, payload, channel=1, use_jnd=False)

        np.testing.assert_array_equal(
            result.encoded_image[:, :, 0], sample_image[:, :, 0]
        )
        np.testing.assert_array_equal(
            result.encoded_image[:, :, 2], sample_image[:, :, 2]
        )


# ═══════════════════════════════════════════════════════════════════
# Tests: Reed-Solomon ECC
# ═══════════════════════════════════════════════════════════════════

class TestECC:
    """Tests para Reed-Solomon Error Correction."""

    def test_encode_decode_no_errors(self):
        """ECC funciona sin errores."""
        data = b"Hello H-Bit Protocol"
        encoded = encode_ecc(data, nsym="standard")

        decoded = decode_ecc(encoded.data, encoded.parity, nsym="standard")
        assert decoded.is_valid
        assert decoded.data == data
        assert decoded.corrected_errors == 0

    def test_encode_decode_with_errors(self):
        """ECC corrige errores introducidos."""
        data = b"Test data for ECC"
        encoded = encode_ecc(data, nsym="standard")

        # Introducir 3 errores en los datos
        corrupted = bytearray(encoded.data)
        corrupted[0] ^= 0xFF
        corrupted[5] ^= 0xAA
        corrupted[10] ^= 0x55

        decoded = decode_ecc(bytes(corrupted), encoded.parity, nsym="standard")
        assert decoded.is_valid
        assert decoded.data == data
        assert decoded.corrected_errors > 0

    def test_too_many_errors_fails_gracefully(self):
        """Demasiados errores reportan fallo sin excepción."""
        data = b"Short"
        encoded = encode_ecc(data, nsym="light")

        # Corromper datos Y paridad para exceder la capacidad de corrección
        corrupted_data = bytearray(encoded.data)
        for i in range(len(corrupted_data)):
            corrupted_data[i] ^= 0xFF
        corrupted_parity = bytearray(encoded.parity)
        for i in range(len(corrupted_parity)):
            corrupted_parity[i] ^= 0xFF

        decoded = decode_ecc(bytes(corrupted_data), bytes(corrupted_parity), nsym="light")
        # Debe reportar fallo, no lanzar excepción
        assert not decoded.is_valid

    def test_ecc_presets(self):
        """Todos los presets producen resultados válidos."""
        data = b"Test " * 10
        for preset in ["light", "standard", "heavy", "forensic"]:
            result = encode_ecc(data, nsym=preset)
            assert len(result.parity) > 0

    def test_optimal_nsym_computation(self):
        """El cálculo de nsym óptimo es razonable."""
        nsym = compute_optimal_nsym(100, expected_error_rate=0.05)
        assert 10 <= nsym <= 100


# ═══════════════════════════════════════════════════════════════════
# Tests: Tiling
# ═══════════════════════════════════════════════════════════════════

class TestTiling:
    """Tests para el teselado y interleaving."""

    def test_tile_layout_computation(self):
        """El layout de tiles se calcula correctamente."""
        layout = compute_tile_layout(
            image_height=256, image_width=256,
            payload_bits=592, block_size=8,
        )
        assert layout.total_tiles > 0
        assert layout.redundancy_factor >= 1

    def test_interleave_deinterleave_roundtrip(self):
        """El interleaving es reversible."""
        payload = "10110011" * 10
        num_copies = 4
        depth = 4

        interleaved = generate_interleaved_sequence(payload, num_copies, depth)
        copies = deinterleave_sequence(interleaved, len(payload), num_copies, depth)

        assert len(copies) == num_copies
        for copy in copies:
            assert copy[:len(payload)] == payload

    def test_interleave_distributes_bits(self):
        """El interleaving mezcla bits de diferentes copias."""
        payload1 = "0000"
        interleaved = generate_interleaved_sequence(payload1, 2, 1)
        # Con depth=1, debe alternar: 00001111 → 01010101 (pero ambas copias son iguales)
        assert len(interleaved) == len(payload1) * 2


# ═══════════════════════════════════════════════════════════════════
# Tests: Anchor Grid
# ═══════════════════════════════════════════════════════════════════

class TestAnchorGrid:
    """Tests para la rejilla de anclaje."""

    def test_anchor_grid_positions(self):
        """Las posiciones de la rejilla son válidas."""
        grid = compute_anchor_grid(256, 256, grid_spacing=8)
        assert len(grid.grid_points) > 0
        for point in grid.grid_points:
            assert 0 <= point[0] < 256
            assert 0 <= point[1] < 256

    def test_inject_anchor_preserves_other_channels(self, sample_image):
        """La inyección de anchors no modifica otros canales."""
        result = inject_anchor_grid(sample_image, channel=2, grid_spacing=8)
        np.testing.assert_array_equal(result[:, :, 0], sample_image[:, :, 0])
        np.testing.assert_array_equal(result[:, :, 1], sample_image[:, :, 1])

    def test_detect_injected_anchors(self, sample_image):
        """Los anchors inyectados son detectables."""
        injected = inject_anchor_grid(
            sample_image, channel=2, grid_spacing=8, strength=25.0
        )
        detection = detect_anchor_grid(injected, channel=2, grid_spacing=8)
        # Al menos algunos anchors deben detectarse
        assert detection.detection_rate > 0.0


# ═══════════════════════════════════════════════════════════════════
# Tests: JND Mask
# ═══════════════════════════════════════════════════════════════════

class TestJNDMask:
    """Tests para la máscara JND."""

    def test_jnd_mask_shape(self, sample_image):
        """La máscara JND tiene las dimensiones correctas."""
        block_size = 8
        jnd = compute_jnd_mask(sample_image, channel=2, block_size=block_size)
        expected_rows = 256 // block_size
        expected_cols = 256 // block_size
        assert jnd.shape == (expected_rows, expected_cols, block_size * block_size)

    def test_jnd_values_positive(self, sample_image):
        """Todos los valores JND son positivos."""
        jnd = compute_jnd_mask(sample_image)
        assert np.all(jnd >= 0)

    def test_max_embedding_capacity(self, sample_image):
        """La capacidad de incrustación es razonable."""
        jnd = compute_jnd_mask(sample_image)
        capacity = compute_max_embedding_capacity(jnd)
        assert capacity > 0


# ═══════════════════════════════════════════════════════════════════
# Tests: Encoder Híbrido
# ═══════════════════════════════════════════════════════════════════

class TestHybridEncoder:
    """Tests para el encoder/decoder híbrido."""

    def test_hybrid_encode_uses_both_channels(self, sample_image):
        """El encoding híbrido modifica ambos canales."""
        payload = "10110011" * 8
        result = encode_hybrid(
            sample_image, payload,
            lsb_channel=2, dct_channel=1,
            dct_strength=30.0,
        )

        # Canal 2 (LSB) debe estar modificado
        diff_lsb = np.abs(
            result.encoded_image[:, :, 2].astype(np.int16)
            - sample_image[:, :, 2].astype(np.int16)
        )
        assert diff_lsb.sum() > 0

        # Canal 1 (DCT) debe estar modificado
        diff_dct = np.abs(
            result.encoded_image[:, :, 1].astype(np.int16)
            - sample_image[:, :, 1].astype(np.int16)
        )
        assert diff_dct.sum() > 0

        # Canal 0 no debe cambiar
        np.testing.assert_array_equal(
            result.encoded_image[:, :, 0], sample_image[:, :, 0]
        )

    def test_hybrid_total_bits(self, sample_image):
        """El total de bits es la suma de LSB + DCT."""
        payload = "10101010" * 4
        result = encode_hybrid(
            sample_image, payload,
            lsb_channel=2, dct_channel=1,
        )
        assert result.total_bits == (
            result.lsb_result.bits_embedded + result.dct_result.bits_embedded
        )
