"""
Tests de fuzzing para el protocolo H-Bit.

Usa Hypothesis para generar entradas aleatorias y verificar que
el parser/deserializer no crashea ante datos malformados.

Requiere: pip install hypothesis
"""

import struct

import numpy as np
import pytest

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from hbit.core.signature import (
    HBitPayload,
    PayloadFlags,
    PROTOCOL_VERSION,
)
from hbit.core.sync import find_payload_boundaries


# ═══════════════════════════════════════════════════════════════════
# Fuzz: Payload Deserialization
# ═══════════════════════════════════════════════════════════════════

class TestFuzzDeserialization:
    """Fuzzing del deserializer de payloads."""

    @given(data=st.binary(min_size=0, max_size=500))
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_deserialize_core_arbitrary_bytes(self, data):
        """deserialize_core no debe crashear con bytes arbitrarios."""
        try:
            HBitPayload.deserialize_core(data)
        except (ValueError, struct.error, IndexError):
            pass  # Errores controlados son aceptables

    @given(data=st.binary(min_size=0, max_size=500))
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_decrypt_payload_arbitrary_bytes(self, data):
        """decrypt_payload no debe crashear con bytes y passphrase arbitrary."""
        try:
            HBitPayload.decrypt_payload(data, "fuzz-passphrase")
        except (ValueError, struct.error, IndexError, Exception):
            pass  # Cualquier excepción controlada es aceptable

    @given(
        version=st.integers(min_value=0, max_value=255),
        flags=st.integers(min_value=0, max_value=255),
        rest=st.binary(min_size=0, max_size=200),
    )
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_deserialize_with_valid_header(self, version, flags, rest):
        """Header válido + body arbitrario no debe crashear."""
        header = struct.pack("!BB", version, flags)
        data = header + rest
        try:
            HBitPayload.deserialize_core(data)
        except (ValueError, struct.error, IndexError):
            pass

    @given(data=st.binary(min_size=74, max_size=300))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_deserialize_minimum_size(self, data):
        """Datos >= 74 bytes (core min size) con header correcto."""
        # Forzar header válido
        data = struct.pack("!BB", PROTOCOL_VERSION, int(PayloadFlags.HAS_CONTENT_HASH)) + data[2:]
        try:
            payload = HBitPayload.deserialize_core(data)
            # Si deserializa OK, verificar que los campos tienen tamaño correcto
            assert len(payload.author_hash) == 32
            assert len(payload.content_hash) == 32
        except (ValueError, struct.error, IndexError):
            pass


# ═══════════════════════════════════════════════════════════════════
# Fuzz: Sync Detection
# ═══════════════════════════════════════════════════════════════════

class TestFuzzSync:
    """Fuzzing del detector de sincronización."""

    @given(data=st.binary(min_size=0, max_size=2000))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_sync_detect_arbitrary(self, data):
        """find_payload_boundaries no debe crashear con datos arbitrarios."""
        bit_str = "".join(format(b, "08b") for b in data)
        try:
            find_payload_boundaries(bit_str)
        except (ValueError, IndexError, Exception):
            pass


# ═══════════════════════════════════════════════════════════════════
# Fuzz: Roundtrip
# ═══════════════════════════════════════════════════════════════════

class TestFuzzRoundtrip:
    """Fuzzing de propiedades de roundtrip."""

    @given(
        author=st.binary(min_size=32, max_size=32),
        content=st.binary(min_size=32, max_size=32),
        timestamp=st.floats(min_value=0, max_value=2e10, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_serialize_deserialize_roundtrip(self, author, content, timestamp):
        """serialize_core → deserialize_core debe preservar datos."""
        payload = HBitPayload(
            version=PROTOCOL_VERSION,
            flags=PayloadFlags.HAS_CONTENT_HASH | PayloadFlags.HAS_TIMESTAMP,
            author_hash=author,
        )
        payload.content_hash = content
        payload.timestamp = timestamp

        serialized = payload.serialize_core()
        recovered = HBitPayload.deserialize_core(serialized)

        assert recovered.author_hash == author
        assert recovered.content_hash == content
        assert abs(recovered.timestamp - timestamp) < 1e-6

