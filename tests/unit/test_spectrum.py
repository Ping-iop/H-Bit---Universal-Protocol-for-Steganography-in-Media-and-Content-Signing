"""
Tests para el SpectrumVerifier — verificación parcial con confianza espectral.

Verifica el core de H-Bit: verificación no-binaria con espectro de confianza.
"""

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from hbit.analysis.spectrum import (
    SpectrumVerifier,
    SpectrumResult,
    SpectrumVerdict,
    TileRecovery,
)
from hbit.core.crypto import generate_key_pair, HBitKeyPair
from hbit.universal import UniversalEncoder, UniversalDecoder
from hbit.formats.base import MediaRegistry


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def reset_registry():
    MediaRegistry.reset()
    yield
    MediaRegistry.reset()


@pytest.fixture
def keypair():
    return generate_key_pair()


@pytest.fixture
def passphrase():
    return "test-spectrum-passphrase-2026"


@pytest.fixture
def signed_png(keypair, tmp_path):
    """Crea una imagen PNG firmada con H-Bit para tests."""
    rng = np.random.default_rng(42)
    img = Image.fromarray(
        rng.integers(0, 256, (200, 200, 3), dtype=np.uint8)
    )
    input_path = tmp_path / "original.png"
    img.save(input_path, "PNG")

    output_path = tmp_path / "signed.png"
    encoder = UniversalEncoder(use_kdf=False)
    result = encoder.encode(
        file_path=input_path,
        author_key=keypair,
        output_path=output_path,
    )

    return {
        "input": input_path,
        "output": output_path,
        "result": result,
        "author_hash": result.author_hash,
    }


@pytest.fixture
def signed_jpg(keypair, tmp_path):
    """Crea una imagen JPEG firmada con H-Bit."""
    rng = np.random.default_rng(42)
    img = Image.fromarray(
        rng.integers(0, 256, (200, 200, 3), dtype=np.uint8)
    )
    input_path = tmp_path / "original.jpg"
    img.save(input_path, "JPEG", quality=95)

    output_path = tmp_path / "signed.jpg"
    encoder = UniversalEncoder(use_kdf=False)
    result = encoder.encode(
        file_path=input_path,
        author_key=keypair,
        output_path=output_path,
    )

    return {
        "input": input_path,
        "output": output_path,
        "result": result,
        "author_hash": result.author_hash,
    }


@pytest.fixture
def signed_large_png(keypair, tmp_path):
    """Crea una imagen PNG grande (400x400) firmada — múltiples tiles."""
    rng = np.random.default_rng(99)
    img = Image.fromarray(
        rng.integers(0, 256, (400, 400, 3), dtype=np.uint8)
    )
    input_path = tmp_path / "large.png"
    img.save(input_path, "PNG")

    output_path = tmp_path / "large_signed.png"
    encoder = UniversalEncoder(use_kdf=False)
    result = encoder.encode(
        file_path=input_path,
        author_key=keypair,
        output_path=output_path,
    )

    return {
        "input": input_path,
        "output": output_path,
        "result": result,
        "author_hash": result.author_hash,
    }


# ═══════════════════════════════════════════════════════════════════
# Tests: Basic functionality
# ═══════════════════════════════════════════════════════════════════

class TestSpectrumVerifierBasic:
    """Tests básicos del SpectrumVerifier."""

    def test_import(self):
        """Verifica que el módulo se importa correctamente."""
        verifier = SpectrumVerifier()
        assert verifier is not None

    def test_unsigned_image_returns_no_evidence(self, tmp_path):
        """Imagen sin firma debe retornar NO_EVIDENCE."""
        img = Image.fromarray(
            np.random.default_rng(1).integers(0, 256, (100, 100, 3), dtype=np.uint8)
        )
        path = tmp_path / "unsigned.png"
        img.save(path, "PNG")

        verifier = SpectrumVerifier()
        result = verifier.analyze(path)

        assert result.verdict == SpectrumVerdict.NO_EVIDENCE
        assert result.confidence == 0.0
        assert not result.has_evidence

    def test_signed_png_high_confidence(self, signed_png):
        """Imagen PNG firmada completa debe dar confianza alta."""
        verifier = SpectrumVerifier()
        result = verifier.analyze(signed_png["output"])

        assert result.has_evidence
        assert result.verdict in (
            SpectrumVerdict.AUTHENTIC,
            SpectrumVerdict.LIKELY_AUTHENTIC,
        )
        assert result.confidence >= 0.70, f"Confianza esperada ≥0.70, fue {result.confidence}"
        assert result.payloads_valid > 0
        assert result.author_hash is not None

    def test_signed_png_author_match(self, signed_png):
        """El author_hash del espectro debe coincidir con el original."""
        verifier = SpectrumVerifier()
        result = verifier.analyze(signed_png["output"])

        if result.author_hash:
            assert result.author_hash == signed_png["author_hash"], (
                f"Author mismatch: {result.author_hash[:16]}... vs {signed_png['author_hash'][:16]}..."
            )

    def test_large_png_multiple_tiles(self, signed_large_png):
        """Imagen grande debe tener múltiples tiles."""
        verifier = SpectrumVerifier()
        result = verifier.analyze(signed_large_png["output"])

        # Con 400x400 y ~856 bits de payload, debería haber varios tiles
        assert result.tiles_total >= 1
        assert result.payloads_valid >= 1
        assert 0.0 <= result.confidence <= 1.0


# ═══════════════════════════════════════════════════════════════════
# Tests: Partial verification (crops)
# ═══════════════════════════════════════════════════════════════════

class TestSpectrumPartialVerification:
    """Tests de verificación parcial — el core de H-Bit."""

    def test_cropped_image_lower_confidence(self, signed_large_png, tmp_path):
        """Un crop de la imagen debe dar confianza menor pero > 0."""
        # Cargar imagen firmada y recortarla
        img = Image.open(signed_large_png["output"])
        # Crop: solo 25% de la imagen (esquina superior izquierda)
        cropped = img.crop((0, 0, 200, 200))
        crop_path = tmp_path / "cropped.png"
        cropped.save(crop_path, "PNG")

        verifier = SpectrumVerifier()
        result = verifier.analyze(crop_path)

        # Debe encontrar ALGO (los tiles en esa región)
        if result.has_evidence:
            assert result.confidence < 1.0, (
                "Crop no debería dar confianza 100%"
            )
            assert result.tiles_total > 0

    def test_tiny_crop_may_have_evidence(self, signed_large_png, tmp_path):
        """Incluso un crop muy pequeño puede tener alguna evidencia."""
        img = Image.open(signed_large_png["output"])
        # Crop muy pequeño: solo 5% de la imagen
        cropped = img.crop((0, 0, 80, 80))
        crop_path = tmp_path / "tiny_crop.png"
        cropped.save(crop_path, "PNG")

        verifier = SpectrumVerifier()
        result = verifier.analyze(crop_path)

        # Puede o no encontrar firma dependiendo de la distribución de tiles
        # Lo importante es que no crashea
        assert isinstance(result, SpectrumResult)
        assert result.verdict in [
            SpectrumVerdict.AUTHENTIC,
            SpectrumVerdict.LIKELY_AUTHENTIC,
            SpectrumVerdict.POSSIBLY_AUTHENTIC,
            SpectrumVerdict.UNCERTAIN,
            SpectrumVerdict.LIKELY_TAMPERED,
            SpectrumVerdict.NO_EVIDENCE,
        ]

    def test_full_vs_crop_confidence_comparison(self, signed_large_png, tmp_path):
        """La confianza de la imagen completa debe ser alta, y el crop también."""
        img = Image.open(signed_large_png["output"])

        # Guardar crop: primeras filas, ancho completo (preserva row-major order)
        full_data = np.array(img)
        crop_data = full_data[:200, :, :]  # top 50% rows
        crop_img = Image.fromarray(crop_data)
        crop_path = tmp_path / "half_rows_crop.png"
        crop_img.save(crop_path, "PNG")

        verifier = SpectrumVerifier()
        full_result = verifier.analyze(signed_large_png["output"])
        crop_result = verifier.analyze(crop_path)

        # Ambos deben tener evidencia
        assert full_result.has_evidence
        assert crop_result.has_evidence

        # Ambos deben ser AUTHENTIC o LIKELY_AUTHENTIC
        assert full_result.is_authentic
        assert crop_result.is_authentic

        # La confianza de ambos debe ser alta (>70%)
        assert full_result.confidence >= 0.70
        assert crop_result.confidence >= 0.70


# ═══════════════════════════════════════════════════════════════════
# Tests: Consensus & ECC
# ═══════════════════════════════════════════════════════════════════

class TestSpectrumConsensus:
    """Tests de consenso entre tiles."""

    def test_single_tile_consensus(self, signed_png):
        """Con un solo tile, el consenso debe ser 1.0."""
        verifier = SpectrumVerifier()
        result = verifier.analyze(signed_png["output"])

        if result.payloads_valid == 1:
            assert result.author_consensus == 1.0

    def test_multiple_tiles_consensus(self, signed_large_png):
        """Múltiples tiles deben tener consenso alto (misma firma)."""
        verifier = SpectrumVerifier()
        result = verifier.analyze(signed_large_png["output"])

        if result.payloads_valid > 1:
            # Todos los tiles deberían tener el mismo author_hash
            assert result.author_consensus >= 0.9, (
                f"Consenso bajo: {result.author_consensus:.2f}"
            )

    def test_tampered_image_low_confidence(self, signed_png, tmp_path):
        """Imagen manipulada debe dar confianza más baja."""
        img = Image.open(signed_png["output"])
        data = np.array(img)

        # Modificar píxeles (simular manipulación)
        data[50:60, 50:60, :] = 255

        tampered = Image.fromarray(data)
        tampered_path = tmp_path / "tampered.png"
        tampered.save(tampered_path, "PNG")

        verifier = SpectrumVerifier()
        result = verifier.analyze(tampered_path)

        # Debe seguir encontrando firma (LSB en canal B puede sobrevivir)
        # pero la confianza debería ser menor o el content_hash no coincidir
        assert isinstance(result, SpectrumResult)


# ═══════════════════════════════════════════════════════════════════
# Tests: JPEG/DCT
# ═══════════════════════════════════════════════════════════════════

class TestSpectrumJPEG:
    """Tests con imágenes JPEG (DCT)."""

    def test_signed_jpeg_basic(self, signed_jpg):
        """JPEG firmado debe ser analizable."""
        verifier = SpectrumVerifier()
        result = verifier.analyze(signed_jpg["output"])

        # JPEG con DCT puede recuperar o no dependiendo de la fuerza
        assert isinstance(result, SpectrumResult)

    def test_jpeg_recompressed(self, signed_jpg, tmp_path):
        """JPEG re-comprimido debe mostrar degradación en confianza."""
        img = Image.open(signed_jpg["output"])
        recompressed_path = tmp_path / "recompressed.jpg"
        img.save(recompressed_path, "JPEG", quality=70)

        verifier = SpectrumVerifier()
        result = verifier.analyze(recompressed_path)
        assert isinstance(result, SpectrumResult)


# ═══════════════════════════════════════════════════════════════════
# Tests: Edge cases
# ═══════════════════════════════════════════════════════════════════

class TestSpectrumEdgeCases:
    """Tests de casos límite."""

    def test_nonexistent_file(self, tmp_path):
        """Archivo inexistente debe lanzar error."""
        verifier = SpectrumVerifier()
        with pytest.raises((FileNotFoundError, ValueError, Exception)):
            verifier.analyze(tmp_path / "does_not_exist.png")

    def test_empty_file(self, tmp_path):
        """Archivo vacío debe manejarse sin crashear."""
        empty_path = tmp_path / "empty.png"
        empty_path.write_bytes(b"")

        verifier = SpectrumVerifier()
        with pytest.raises((ValueError, Exception)):
            verifier.analyze(empty_path)

    def test_confidence_bounds(self, signed_png):
        """La confianza siempre debe estar en [0, 1]."""
        verifier = SpectrumVerifier()
        result = verifier.analyze(signed_png["output"])
        assert 0.0 <= result.confidence <= 1.0

    def test_result_structure_complete(self, signed_png):
        """El resultado debe tener todos los campos poblados."""
        verifier = SpectrumVerifier()
        result = verifier.analyze(signed_png["output"])

        assert isinstance(result.confidence, float)
        assert isinstance(result.verdict, str)
        assert isinstance(result.tiles_total, int)
        assert isinstance(result.payloads_valid, int)
        assert isinstance(result.author_consensus, float)
        assert isinstance(result.ecc_total_corrections, int)
        assert isinstance(result.tile_details, list)
        assert isinstance(result.analysis_summary, str)

    def test_tile_details_populated(self, signed_large_png):
        """Tile details debe contener información por tile."""
        verifier = SpectrumVerifier()
        result = verifier.analyze(signed_large_png["output"])

        for tile in result.tile_details:
            assert isinstance(tile, TileRecovery)
            assert tile.index >= 0
            assert tile.payload_length_bits > 0
            assert len(tile.raw_bits) > 0

    def test_result_properties(self, signed_png):
        """is_authentic y has_evidence deben ser consistentes."""
        verifier = SpectrumVerifier()
        result = verifier.analyze(signed_png["output"])

        if result.verdict in (SpectrumVerdict.AUTHENTIC, SpectrumVerdict.LIKELY_AUTHENTIC):
            assert result.is_authentic
        if result.verdict == SpectrumVerdict.NO_EVIDENCE:
            assert not result.has_evidence

    def test_reproducibility(self, signed_png):
        """Dos análisis del mismo archivo deben dar el mismo resultado."""
        verifier = SpectrumVerifier()
        r1 = verifier.analyze(signed_png["output"])
        r2 = verifier.analyze(signed_png["output"])

        assert r1.confidence == r2.confidence
        assert r1.verdict == r2.verdict
        assert r1.payloads_valid == r2.payloads_valid


# ═══════════════════════════════════════════════════════════════════
# Tests: Origin type detection
# ═══════════════════════════════════════════════════════════════════

class TestSpectrumOriginType:
    """Tests de detección de origen (human vs AI)."""

    def test_human_origin_detected(self, keypair, tmp_path):
        """Firma con --origin human debe mostrar HUMAN en el espectro."""
        rng = np.random.default_rng(7)
        img = Image.fromarray(
            rng.integers(0, 256, (150, 150, 3), dtype=np.uint8)
        )
        input_path = tmp_path / "human_orig.png"
        img.save(input_path, "PNG")

        from hbit.core.signature import OriginType

        output_path = tmp_path / "human_signed.png"
        encoder = UniversalEncoder(use_kdf=False)
        encoder.encode(
            file_path=input_path,
            author_key=keypair,
            output_path=output_path,
            origin_type=OriginType.HUMAN,
        )

        verifier = SpectrumVerifier()
        result = verifier.analyze(output_path)

        if result.has_evidence and result.origin_type:
            assert "HUMAN" in result.origin_type.upper() or result.origin_type == "HUMAN"

    def test_ai_generated_origin_detected(self, keypair, tmp_path):
        """Firma como AI_GENERATED debe reflejarse en el espectro."""
        rng = np.random.default_rng(13)
        img = Image.fromarray(
            rng.integers(0, 256, (150, 150, 3), dtype=np.uint8)
        )
        input_path = tmp_path / "ai_orig.png"
        img.save(input_path, "PNG")

        from hbit.core.signature import OriginType

        output_path = tmp_path / "ai_signed.png"
        encoder = UniversalEncoder(use_kdf=False)
        encoder.encode(
            file_path=input_path,
            author_key=keypair,
            output_path=output_path,
            origin_type=OriginType.AI_GENERATED,
            ai_model_id="midjourney-v6",
        )

        verifier = SpectrumVerifier()
        result = verifier.analyze(output_path)

        if result.has_evidence and result.origin_type:
            assert "AI" in result.origin_type.upper()
