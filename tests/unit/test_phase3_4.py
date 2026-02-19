"""
Tests unitarios para las Fases 3-4:
- Fase 3: Integración Phygital (C2PA, Oracle)
- Fase 4: Grado Forense (PRNU, Luminancia)

El blockchain registrar NO se testea aquí (requiere nodo RPC).
"""

import hashlib
import numpy as np
import pytest

from hbit.blockchain.c2pa import (
    create_hbit_c2pa_manifest,
    extract_hbit_from_c2pa,
    validate_c2pa_hbit_binding,
)
from hbit.blockchain.oracle import PhysicalPossessionOracle
from hbit.forensics.prnu import (
    extract_noise_residual,
    estimate_prnu,
    verify_prnu,
    generate_prnu_binding,
)
from hbit.forensics.luminance import (
    analyze_light_coherence,
    analyze_shadow_gradients,
)


@pytest.fixture
def sample_image():
    rng = np.random.default_rng(42)
    return rng.integers(0, 256, size=(256, 256, 3), dtype=np.uint8)


@pytest.fixture
def synthetic_lit_image():
    """Imagen sintética con iluminación lateral (gradiente horizontal)."""
    h, w = 256, 256
    img = np.zeros((h, w, 3), dtype=np.uint8)
    for x in range(w):
        brightness = int(50 + 150 * (x / w))
        img[:, x, :] = brightness
    return img


# ═══════════════════════════════════════════════════════════════════
# Tests: C2PA
# ═══════════════════════════════════════════════════════════════════

class TestC2PA:
    """Tests para la integración C2PA."""

    def test_create_manifest(self):
        """Crear un manifiesto C2PA con aserciones H-Bit."""
        result = create_hbit_c2pa_manifest(
            image_hash=b"\x01" * 32,
            author_hash=b"\x02" * 32,
            payload_hash=b"\x03" * 32,
            title="test-image.png",
        )
        assert result.manifest is not None
        assert len(result.manifest_hash) == 32
        assert len(result.manifest_json) > 0
        assert result.manifest.claim_generator == "H-Bit Protocol/0.1.0"

    def test_manifest_contains_hbit_assertion(self):
        """El manifiesto contiene la aserción hbit.signature."""
        result = create_hbit_c2pa_manifest(
            image_hash=b"\x01" * 32,
            author_hash=b"\x02" * 32,
            payload_hash=b"\x03" * 32,
        )
        hbit_data = extract_hbit_from_c2pa(result.manifest_json)
        assert hbit_data is not None
        assert hbit_data["protocol_version"] == 1
        assert hbit_data["algorithm"] == "Ed25519"

    def test_validate_binding(self):
        """La validación de vinculación C2PA-HBit funciona."""
        payload_hash = b"\x03" * 32
        result = create_hbit_c2pa_manifest(
            image_hash=b"\x01" * 32,
            author_hash=b"\x02" * 32,
            payload_hash=payload_hash,
        )
        assert validate_c2pa_hbit_binding(
            result.manifest_json, b"\x01" * 32, payload_hash
        )

    def test_validate_binding_fails_wrong_hash(self):
        """La validación falla con hash incorrecto."""
        result = create_hbit_c2pa_manifest(
            image_hash=b"\x01" * 32,
            author_hash=b"\x02" * 32,
            payload_hash=b"\x03" * 32,
        )
        assert not validate_c2pa_hbit_binding(
            result.manifest_json, b"\x01" * 32, b"\xFF" * 32
        )

    def test_extract_from_invalid_json(self):
        """Extracción de JSON inválido retorna None."""
        assert extract_hbit_from_c2pa("not valid json") is None
        assert extract_hbit_from_c2pa('{"assertions": []}') is None


# ═══════════════════════════════════════════════════════════════════
# Tests: Oracle
# ═══════════════════════════════════════════════════════════════════

class TestOracle:
    """Tests para el oráculo de posesión física."""

    def test_generate_challenge(self):
        """El challenge se genera correctamente."""
        oracle = PhysicalPossessionOracle()
        challenge = oracle.generate_challenge()
        assert len(challenge.challenge_id) > 0
        assert len(challenge.nonce) > 0
        assert challenge.expiry > 0

    def test_full_verification_flow(self):
        """Flujo completo: challenge → proof → verify."""
        oracle = PhysicalPossessionOracle()
        challenge = oracle.generate_challenge()

        # Simular captura
        capture_data = b"nueva captura del soporte fisico" * 10
        proof = oracle.create_proof(
            challenge.challenge_id,
            challenge.nonce,
            capture_data,
            metadata={"gps": (40.4, -3.7), "exif": True},
        )

        # Verificar (con un hash original diferente)
        original_hash = hashlib.sha256(b"imagen original").digest()
        result = oracle.verify_possession(proof, original_hash)
        assert result.is_valid
        assert result.confidence > 0.3

    def test_expired_challenge_fails(self):
        """Un challenge expirado es rechazado."""
        oracle = PhysicalPossessionOracle()
        challenge = oracle.generate_challenge(expiry_seconds=0)

        import time
        time.sleep(0.1)

        capture_data = b"captura" * 10
        proof = oracle.create_proof(
            challenge.challenge_id, challenge.nonce, capture_data,
        )
        result = oracle.verify_possession(proof, b"\x00" * 32)
        assert not result.is_valid
        assert "expirado" in result.reason.lower()

    def test_wrong_nonce_fails(self):
        """Un nonce incorrecto es rechazado."""
        oracle = PhysicalPossessionOracle()
        challenge = oracle.generate_challenge()

        proof = oracle.create_proof(
            challenge.challenge_id, "wrong_nonce", b"capture" * 10,
        )
        result = oracle.verify_possession(proof, b"\x00" * 32)
        assert not result.is_valid

    def test_replay_detection(self):
        """Detecta un replay (misma imagen enviada como captura)."""
        oracle = PhysicalPossessionOracle()
        challenge = oracle.generate_challenge()

        # Enviar la misma imagen como "nueva captura"
        original_data = b"datos de la imagen original"
        original_hash = hashlib.sha256(original_data).digest()
        proof = oracle.create_proof(
            challenge.challenge_id, challenge.nonce, original_data,
        )
        result = oracle.verify_possession(proof, original_hash)
        assert not result.is_valid
        assert "replay" in result.reason.lower()


# ═══════════════════════════════════════════════════════════════════
# Tests: PRNU
# ═══════════════════════════════════════════════════════════════════

class TestPRNU:
    """Tests para el análisis PRNU."""

    def test_noise_residual_shape(self, sample_image):
        """El residual tiene las mismas dimensiones."""
        residual = extract_noise_residual(sample_image)
        assert residual.shape == sample_image.shape

    def test_estimate_prnu_from_references(self):
        """Se puede estimar PRNU desde imágenes de referencia."""
        # Usar imagen con gradiente determinista (no aleatoria)
        h, w = 128, 128
        base = np.zeros((h, w, 3), dtype=np.uint8)
        for y in range(h):
            for x in range(w):
                base[y, x] = [128 + x // 4, 100 + y // 4, 80]

        # Añadir un patrón de ruido fijo (simular PRNU)
        rng = np.random.default_rng(123)
        prnu_pattern = rng.normal(0, 0.01, base.shape)

        refs = []
        for _ in range(5):
            noisy = np.clip(
                base.astype(np.float64) * (1 + prnu_pattern)
                + rng.normal(0, 2, base.shape),
                0, 255
            ).astype(np.uint8)
            refs.append(noisy)

        fingerprint = estimate_prnu(refs, device_id="test-sensor")
        assert fingerprint.pattern.shape == base.shape
        assert fingerprint.num_reference_images == 5
        assert fingerprint.device_id == "test-sensor"

    def test_prnu_binding_length(self, sample_image):
        """El binding PRNU tiene 32 bytes (SHA-256)."""
        fingerprint = estimate_prnu([sample_image], device_id="test")
        binding = generate_prnu_binding(fingerprint)
        assert len(binding) == 32

    def test_verify_prnu_returns_result(self, sample_image):
        """La verificación PRNU retorna un resultado válido."""
        fingerprint = estimate_prnu([sample_image], device_id="test")
        result = verify_prnu(sample_image, fingerprint)
        assert isinstance(result.correlation, float)
        assert isinstance(result.is_match, bool)


# ═══════════════════════════════════════════════════════════════════
# Tests: Luminancia
# ═══════════════════════════════════════════════════════════════════

class TestLuminance:
    """Tests para la auditoría de coherencia lumínica."""

    def test_consistent_lighting(self, synthetic_lit_image):
        """Una imagen con iluminación uniforme lateral es consistente."""
        result = analyze_light_coherence(synthetic_lit_image, grid_size=4)
        assert result.consistency_score > 0.3  # Gradiente consistente

    def test_shadow_analysis(self, sample_image):
        """El análisis de sombras retorna métricas válidas."""
        result = analyze_shadow_gradients(sample_image)
        assert 0.0 <= result["shadow_coverage"] <= 1.0
        assert 0.0 <= result["shadow_softness"] <= 1.0
        assert isinstance(result["is_natural"], bool)

    def test_regional_directions_shape(self, synthetic_lit_image):
        """Las direcciones regionales tienen la forma correcta."""
        result = analyze_light_coherence(synthetic_lit_image, grid_size=4)
        assert result.regional_directions.shape == (4, 4)

    def test_random_image_light_analysis(self, sample_image):
        """Una imagen aleatoria no debe crashear el análisis."""
        # Las imágenes aleatorias no tienen iluminación coherente,
        # solo verificamos que no crashea y retorna valores válidos.
        result = analyze_light_coherence(sample_image, grid_size=4)
        assert isinstance(result.is_consistent, bool)
        assert 0.0 <= result.consistency_score <= 1.0
        assert result.regional_directions.shape == (4, 4)
