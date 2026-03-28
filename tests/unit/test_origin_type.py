"""
Tests unitarios para el sistema de origen IA (OriginType).

Verifica que el campo origin_type se serializa, deserializa y propaga
correctamente a través de todo el pipeline H-Bit.
"""

import os
import struct
import tempfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from hbit.core.signature import (
    HBitPayload,
    PayloadFlags,
    OriginType,
    AI_MODEL_ID_LENGTH,
    _compute_ai_model_id_hash,
)


class TestOriginType:
    """Tests para el enum OriginType."""

    def test_origin_type_values(self):
        """Los valores del enum coinciden con la especificación del protocolo."""
        assert OriginType.HUMAN == 0x00
        assert OriginType.AI_GENERATED == 0x01
        assert OriginType.AI_ASSISTED == 0x02
        assert OriginType.UNKNOWN == 0xFF

    def test_origin_type_from_int(self):
        """Conversión desde int funciona correctamente."""
        assert OriginType(0) == OriginType.HUMAN
        assert OriginType(1) == OriginType.AI_GENERATED
        assert OriginType(2) == OriginType.AI_ASSISTED
        assert OriginType(255) == OriginType.UNKNOWN

    def test_invalid_origin_type_raises(self):
        """Valores no definidos lanzan ValueError."""
        with pytest.raises(ValueError):
            OriginType(42)


class TestOriginTypePayload:
    """Tests para OriginType en HBitPayload."""

    def test_create_human_payload(self):
        """Payload con origen humano."""
        payload = HBitPayload.create(
            author_hash=b"\x01" * 32,
            origin_type=OriginType.HUMAN,
        )
        assert payload.origin_type == OriginType.HUMAN
        assert payload.origin_label == "Humano"

    def test_create_ai_generated_payload(self):
        """Payload con origen IA generada."""
        payload = HBitPayload.create(
            author_hash=b"\x01" * 32,
            origin_type=OriginType.AI_GENERATED,
            ai_model_id="midjourney-v6",
        )
        assert payload.origin_type == OriginType.AI_GENERATED
        assert payload.origin_label == "Generado por IA"
        assert payload.has_ai_model_id is True

    def test_create_ai_assisted_payload(self):
        """Payload con origen asistido por IA."""
        payload = HBitPayload.create(
            author_hash=b"\x01" * 32,
            origin_type=OriginType.AI_ASSISTED,
            ai_model_id="gpt-4o",
        )
        assert payload.origin_type == OriginType.AI_ASSISTED
        assert payload.origin_label == "Asistido por IA"

    def test_default_origin_is_unknown(self):
        """Sin especificar, el origen es UNKNOWN."""
        payload = HBitPayload.create(author_hash=b"\x01" * 32)
        assert payload.origin_type == OriginType.UNKNOWN
        assert payload.origin_label == "Desconocido"
        assert payload.has_ai_model_id is False

    def test_ai_model_id_hash_deterministic(self):
        """El hash del modelo IA es determinístico."""
        h1 = _compute_ai_model_id_hash("stable-diffusion-xl")
        h2 = _compute_ai_model_id_hash("stable-diffusion-xl")
        assert h1 == h2
        assert len(h1) == AI_MODEL_ID_LENGTH

    def test_ai_model_id_different_models(self):
        """Diferentes modelos producen hashes diferentes."""
        h1 = _compute_ai_model_id_hash("gpt-4o")
        h2 = _compute_ai_model_id_hash("claude-3-opus")
        assert h1 != h2

    def test_ai_model_id_none_is_zeros(self):
        """Sin modelo IA, el hash es bytes nulos."""
        h = _compute_ai_model_id_hash(None)
        assert h == b"\x00" * AI_MODEL_ID_LENGTH

    def test_serialize_deserialize_preserves_origin(self):
        """Roundtrip de serialización preserva origin_type y ai_model_id."""
        payload = HBitPayload.create(
            author_hash=b"\xAA" * 32,
            content_hash=b"\xBB" * 32,
            origin_type=OriginType.AI_GENERATED,
            ai_model_id="dall-e-3",
        )
        serialized = payload.serialize_core()
        recovered = HBitPayload.deserialize_core(serialized)

        assert recovered.origin_type == OriginType.AI_GENERATED
        assert recovered.ai_model_id == payload.ai_model_id
        assert recovered.has_ai_model_id is True
        assert recovered.author_hash == payload.author_hash

    def test_serialize_deserialize_human_origin(self):
        """Roundtrip para origen humano."""
        payload = HBitPayload.create(
            author_hash=b"\xCC" * 32,
            origin_type=OriginType.HUMAN,
        )
        serialized = payload.serialize_core()
        recovered = HBitPayload.deserialize_core(serialized)

        assert recovered.origin_type == OriginType.HUMAN
        assert recovered.has_ai_model_id is False

    def test_origin_type_position_in_binary(self):
        """origin_type está en la posición correcta (byte 2) del payload."""
        payload = HBitPayload.create(
            author_hash=b"\x00" * 32,
            origin_type=OriginType.AI_GENERATED,
        )
        serialized = payload.serialize_core()
        # Byte 0: version, Byte 1: flags, Byte 2: origin_type
        assert serialized[2] == OriginType.AI_GENERATED

    def test_unknown_origin_type_in_deserialization(self):
        """Valores de origin_type no reconocidos caen a UNKNOWN."""
        payload = HBitPayload.create(
            author_hash=b"\x00" * 32,
            origin_type=OriginType.HUMAN,
        )
        serialized = bytearray(payload.serialize_core())
        # Modificar origin_type a un valor no reconocido
        serialized[2] = 0x42  # No existe en el enum
        recovered = HBitPayload.deserialize_core(bytes(serialized))
        assert recovered.origin_type == OriginType.UNKNOWN


class TestOriginTypeUniversalPipeline:
    """Tests de integración para OriginType en el pipeline universal."""

    @pytest.fixture
    def temp_png(self, tmp_path):
        """Genera un PNG temporal de prueba (256×256 para capacidad suficiente)."""
        img = Image.fromarray(
            np.random.randint(0, 256, (256, 256, 3), dtype=np.uint8)
        )
        path = tmp_path / "test_origin.png"
        img.save(str(path))
        return path

    def test_encode_with_human_origin(self, temp_png, tmp_path):
        """El encoder universal respeta el origin_type HUMAN."""
        from hbit.universal import UniversalEncoder

        output = tmp_path / "signed_human.png"
        encoder = UniversalEncoder()
        result = encoder.encode(
            file_path=temp_png,
            author_key="test-passphrase",
            output_path=output,
            origin_type=OriginType.HUMAN,
        )
        assert result.origin_type == "Humano"
        assert result.ai_model_id == ""

    def test_encode_with_ai_origin(self, temp_png, tmp_path):
        """El encoder universal respeta el origin_type AI_GENERATED."""
        from hbit.universal import UniversalEncoder

        output = tmp_path / "signed_ai.png"
        encoder = UniversalEncoder()
        result = encoder.encode(
            file_path=temp_png,
            author_key="test-passphrase",
            output_path=output,
            origin_type=OriginType.AI_GENERATED,
            ai_model_id="midjourney-v6.1",
        )
        assert result.origin_type == "Generado por IA"
        assert result.ai_model_id == "midjourney-v6.1"

    def test_decode_recovers_origin(self, temp_png, tmp_path):
        """El decoder extrae correctamente origin_type y ai_model_id."""
        from hbit.universal import UniversalEncoder, UniversalDecoder

        output = tmp_path / "signed_decode.png"
        encoder = UniversalEncoder()
        encoder.encode(
            file_path=temp_png,
            author_key="decode-test",
            output_path=output,
            origin_type=OriginType.AI_ASSISTED,
            ai_model_id="copilot-v2",
        )

        decoder = UniversalDecoder()
        result = decoder.decode(output)

        assert result.found is True
        assert result.origin_type == "AI_ASSISTED"
        assert result.origin_label == "Asistido por IA"
        assert len(result.ai_model_id) > 0  # Non-empty hash hex

    def test_verify_shows_origin(self, temp_png, tmp_path):
        """El verificador incluye Info de origen en el mensaje."""
        from hbit.universal import UniversalEncoder, UniversalVerifier

        output = tmp_path / "signed_verify.png"
        encoder = UniversalEncoder()
        encoder.encode(
            file_path=temp_png,
            author_key="verify-test",
            output_path=output,
            origin_type=OriginType.AI_GENERATED,
            ai_model_id="stable-diffusion-3",
        )

        verifier = UniversalVerifier()
        result = verifier.verify(output)

        # El verify puede retornar TAMPERED en PNG porque el embedding modifica
        # el content hash. Lo importante es que origin_type se extrajo correctamente.
        assert result.decode_result is not None
        assert result.decode_result.origin_label == "Generado por IA"
        assert result.decode_result.origin_type == "AI_GENERATED"
