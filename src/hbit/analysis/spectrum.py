"""
Verificador Espectral H-Bit — Verificación parcial con confianza granular.

Este es el módulo que implementa la tesis central de H-Bit:
"No necesitás verificación binaria. Necesitás un espectro."

Uso:
    from hbit.analysis.spectrum import SpectrumVerifier
    verifier = SpectrumVerifier()
    result = verifier.analyze("firma_parcial.jpg")
    print(f"Confianza: {result.confidence:.1%}")
"""

from __future__ import annotations

import struct
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

from hbit.core.signature import (
    HBitPayload,
    PayloadFlags,
    AUTHOR_HASH_LENGTH,
    CONTENT_HASH_LENGTH,
)
from hbit.core.sync import (
    SYNC_HEADER_BITS,
    SYNC_FOOTER_BITS,
    SYNC_SEQUENCE_LENGTH,
    find_payload_boundaries,
    find_sync_positions,
)
from hbit.formats.base import MediaRegistry, EmbeddingStrategy


# ═══════════════════════════════════════════════════════════════════
# Verdict levels
# ═══════════════════════════════════════════════════════════════════

class SpectrumVerdict:
    AUTHENTIC = "AUTHENTIC"
    LIKELY_AUTHENTIC = "LIKELY_AUTHENTIC"
    POSSIBLY_AUTHENTIC = "POSSIBLY_AUTHENTIC"
    UNCERTAIN = "UNCERTAIN"
    LIKELY_TAMPERED = "LIKELY_TAMPERED"
    NO_EVIDENCE = "NO_EVIDENCE"


# ═══════════════════════════════════════════════════════════════════
# Data classes
# ═══════════════════════════════════════════════════════════════════

@dataclass
class TileRecovery:
    index: int
    position_start: int
    position_end: int
    payload_length_bits: int
    raw_bits: str
    valid_payload: bool = False
    author_hash: Optional[str] = None
    content_hash: Optional[str] = None
    origin_type: Optional[str] = None
    ai_model_id: Optional[str] = None
    timestamp: float = 0.0
    version: int = 0
    ecc_corrections: int = 0
    ecc_failed: bool = False
    sync_header_corr: float = 0.0
    sync_footer_corr: float = 0.0
    error_message: str = ""


@dataclass
class SpectrumResult:
    confidence: float
    verdict: str
    tiles_total: int
    tiles_recovered: int
    payloads_valid: int
    author_consensus: float
    content_consensus: float
    origin_consensus: float
    ecc_total_corrections: int
    ecc_failures: int
    sync_quality: float
    payload_completeness: float
    author_hash: Optional[str]
    content_hash: Optional[str]
    origin_type: Optional[str]
    ai_model_id: Optional[str]
    tile_details: list = field(default_factory=list)
    media_category: str = ""
    format_name: str = ""
    total_bits_available: int = 0
    analysis_summary: str = ""

    @property
    def is_authentic(self) -> bool:
        return self.verdict in (SpectrumVerdict.AUTHENTIC, SpectrumVerdict.LIKELY_AUTHENTIC)

    @property
    def has_evidence(self) -> bool:
        return self.verdict != SpectrumVerdict.NO_EVIDENCE


# ═══════════════════════════════════════════════════════════════════
# SpectrumVerifier
# ═══════════════════════════════════════════════════════════════════

class SpectrumVerifier:
    """Verificador espectral H-Bit — confianza granular no-binaria."""

    def __init__(self, registry: Optional[MediaRegistry] = None):
        self._registry = registry or MediaRegistry.default()

    def analyze(self, file_path: str | Path) -> SpectrumResult:
        file_path = Path(file_path)
        handler = self._registry.get_handler(file_path)
        carrier = handler.load(file_path)

        if carrier.category.value == "image":
            result = self._analyze_image_file(file_path, handler, carrier)
        else:
            result = self._analyze_generic(file_path, handler, carrier)

        result.media_category = handler.category.value
        result.format_name = handler.name
        return result

    # ══════════════════════════════════════════════════════════════
    # Image analysis
    # ══════════════════════════════════════════════════════════════

    def _analyze_image_file(
        self, file_path: Path, handler, carrier
    ) -> SpectrumResult:
        """Análisis espectral para imágenes.

        Usa decode_lsb directamente (probado y funcionando) para
        obtener los payloads individuales. Luego analiza consenso,
        calidad de sync, y computa confianza espectral.
        """
        shape = carrier.metadata["shape"]
        image_data = np.frombuffer(
            carrier.raw_data, dtype=np.uint8
        ).reshape(shape).copy()
        fmt = carrier.metadata.get("format", "").upper()

        # Usar decode_lsb para extracción robusta
        from hbit.encoders.lsb import decode_lsb
        from hbit.core.sync import find_payload_boundaries

        # Detectar canal
        best_channel = 2
        best_found = 0
        best_raw_bits = ""
        best_payloads = []

        for ch in [2, 0, 1]:
            try:
                result = decode_lsb(image_data, channel=ch)
                if result.payloads_found > best_found:
                    best_found = result.payloads_found
                    best_channel = ch
                    best_raw_bits = result.raw_bits
            except Exception:
                continue

        if best_found == 0:
            if fmt in ("JPEG", "JPG", "WEBP"):
                return self._analyze_dct_fallback(image_data)
            return self._empty_result()

        # Extraer TODOS los payloads individuales (no solo el consenso)
        # usando la misma lógica que decode_lsb pero sin votación
        boundaries = find_payload_boundaries(best_raw_bits, threshold=0.85)

        # Mismo filtro que decode_lsb + validación de contenido
        all_payloads = []
        for start, end in boundaries:
            length = end - start
            if length % 8 == 0 and 700 <= length <= 1600:
                payload_bits = best_raw_bits[start:end]
                # Validar que deserializa correctamente
                try:
                    payload_bytes = SpectrumVerifier._bits_to_bytes(payload_bits)
                    HBitPayload.deserialize_core(payload_bytes)
                    all_payloads.append((start, end, payload_bits))
                except (ValueError, struct.error, IndexError, Exception):
                    continue

        if not all_payloads:
            return self._empty_result()

        # Agrupar por longitud y tomar la más frecuente (misma lógica)
        from collections import Counter
        length_counts = Counter(end - start for start, end, _ in all_payloads)
        sorted_by_len = sorted(length_counts.items(), key=lambda x: x[0])
        target_length = sorted_by_len[0][0]
        for length, count in sorted_by_len:
            if count >= 3:
                target_length = length
                break

        # Filtrar a longitud objetivo
        matching = [
            (s, e, p) for s, e, p in all_payloads
            if (e - s) == target_length
        ]
        matching.sort(key=lambda x: x[0])

        # Dededup
        deduped = []
        last_start = -target_length
        for s, e, p in matching:
            if s - last_start > target_length // 2:
                deduped.append((s, e, p))
                last_start = s

        # Construir tiles
        tile_details = []
        for idx, (start, end, payload_bits) in enumerate(deduped):
            # Sync quality
            h_corr = self._compute_sync_correlation(
                best_raw_bits, start - SYNC_SEQUENCE_LENGTH, True
            )
            f_corr = self._compute_sync_correlation(
                best_raw_bits, end, False
            )

            tile = TileRecovery(
                index=idx,
                position_start=start,
                position_end=end,
                payload_length_bits=end - start,
                raw_bits=payload_bits,
                sync_header_corr=h_corr,
                sync_footer_corr=f_corr,
            )

            # Deserializar
            try:
                payload_bytes = self._bits_to_bytes(payload_bits)
                payload = HBitPayload.deserialize_core(payload_bytes)
                tile.valid_payload = True
                tile.author_hash = payload.author_hash.hex()
                tile.content_hash = payload.content_hash.hex()
                tile.origin_type = payload.origin_type.name
                tile.ai_model_id = (
                    payload.ai_model_id.hex()
                    if payload.has_ai_model_id else None
                )
                tile.timestamp = payload.timestamp
                tile.version = payload.version
            except (ValueError, struct.error, IndexError, Exception) as e:
                tile.error_message = str(e)[:100]

            tile_details.append(tile)

        if not tile_details:
            return self._empty_result()

        return self._build_result(
            tile_details,
            total_bits_available=len(best_raw_bits),
            strategy="LSB",
            channel=best_channel,
        )

    def _detect_channel(self, image_data: np.ndarray) -> int:
        """Detecta el canal que contiene la firma."""
        from hbit.encoders.lsb import decode_lsb
        for ch in [2, 0, 1]:
            try:
                result = decode_lsb(image_data, channel=ch)
                if result.payloads_found > 0:
                    return ch
            except Exception:
                continue
        return 2

    def _analyze_dct_fallback(
        self, image_data: np.ndarray
    ) -> SpectrumResult:
        """Fallback DCT para JPEG."""
        try:
            from hbit.decoders.dct import decode_dct
            dct_result = decode_dct(
                image_data, channel=1, strength=35.0,
                expected_payload_length=None,
            )
            if dct_result.confidence < 0.3:
                return self._empty_result()
            # Para DCT, usamos la búsqueda tradicional de boundaries
            # ya que el stream no es continuo como LSB
            return self._analyze_bitstream_legacy(
                dct_result.payload_bits,
                total_bits_available=len(dct_result.payload_bits),
                strategy="DCT",
            )
        except Exception:
            return self._empty_result()

    # ══════════════════════════════════════════════════════════════
    # Generic format analysis
    # ══════════════════════════════════════════════════════════════

    def _analyze_generic(
        self, file_path: Path, handler, carrier
    ) -> SpectrumResult:
        extract = handler.extract(carrier)
        if extract.payloads_found == 0:
            return self._empty_result()
        return self._analyze_bitstream_legacy(
            extract.payload_bits,
            total_bits_available=len(extract.payload_bits),
            strategy=extract.strategy_used.name,
        )

    # ══════════════════════════════════════════════════════════════
    # Tile extraction: known length (robust, for LSB images)
    # ══════════════════════════════════════════════════════════════

    def _extract_tiles_by_length(
        self,
        bitstream: str,
        payload_content_bits: int,
        total_bits_available: int = 0,
        strategy: str = "LSB",
        channel: int = -1,
    ) -> SpectrumResult:
        """Extrae tiles usando longitud de payload conocida.

        En encoding uniforme, el payload se repite cada unit_length bits.
        Busca el primer header válido, determina la longitud real desde
        el payload deserializado, y extrae tiles secuencialmente.
        """
        if len(bitstream) < 200:
            return self._empty_result()

        # Buscar headers
        header_positions = find_sync_positions(
            bitstream, threshold=0.85, search_header=True
        )
        if not header_positions:
            header_positions = find_sync_positions(
                bitstream, threshold=0.70, search_header=True
            )
        if not header_positions:
            return self._empty_result()

        # Encontrar la PRIMERA posición que produce un payload deserializable
        # y MEDIR la longitud real del contenido serializado
        first_valid_hpos = None
        actual_content_bits = payload_content_bits  # fallback

        for hpos in header_positions:
            if hpos + 200 > len(bitstream):
                continue
            # Probar múltiples longitudes de contenido alrededor del estimado
            for content_len in range(
                max(650, payload_content_bits - 200),
                min(1600, payload_content_bits + 200),
                8,  # solo múltiplos de 8
            ):
                if hpos + SYNC_SEQUENCE_LENGTH + content_len > len(bitstream):
                    break
                content_start = hpos + SYNC_SEQUENCE_LENGTH
                content_end = content_start + content_len
                payload_bits = bitstream[content_start:content_end]
                try:
                    payload_bytes = self._bits_to_bytes(payload_bits)
                    HBitPayload.deserialize_core(payload_bytes)
                    first_valid_hpos = hpos
                    actual_content_bits = content_len
                    break
                except (ValueError, struct.error, IndexError, Exception):
                    continue
            if first_valid_hpos is not None:
                break

        if first_valid_hpos is None:
            return self._empty_result()

        # Usar la longitud real descubierta
        unit_length = 2 * SYNC_SEQUENCE_LENGTH + actual_content_bits

        # Extraer tiles secuencialmente
        tile_details = []
        idx = 0
        hpos = first_valid_hpos

        while hpos + unit_length <= len(bitstream):
            content_start = hpos + SYNC_SEQUENCE_LENGTH
            content_end = content_start + actual_content_bits
            payload_bits = bitstream[content_start:content_end]

            # Sync quality
            header_seg = bitstream[hpos:hpos + SYNC_SEQUENCE_LENGTH]
            footer_seg = bitstream[
                hpos + SYNC_SEQUENCE_LENGTH + actual_content_bits:
                hpos + unit_length
            ]
            h_corr = self._correlation(header_seg, SYNC_HEADER_BITS)
            f_corr = self._correlation(footer_seg, SYNC_FOOTER_BITS)

            tile = TileRecovery(
                index=idx,
                position_start=hpos,
                position_end=hpos + unit_length,
                payload_length_bits=actual_content_bits,
                raw_bits=payload_bits,
                sync_header_corr=h_corr,
                sync_footer_corr=f_corr,
            )

            # Deserializar
            try:
                payload_bytes = self._bits_to_bytes(payload_bits)
                payload = HBitPayload.deserialize_core(payload_bytes)
                tile.valid_payload = True
                tile.author_hash = payload.author_hash.hex()
                tile.content_hash = payload.content_hash.hex()
                tile.origin_type = payload.origin_type.name
                tile.ai_model_id = (
                    payload.ai_model_id.hex()
                    if payload.has_ai_model_id else None
                )
                tile.timestamp = payload.timestamp
                tile.version = payload.version
            except (ValueError, struct.error, IndexError, Exception) as e:
                tile.error_message = str(e)[:100]

            tile_details.append(tile)
            hpos += unit_length
            idx += 1

        if not tile_details:
            return self._empty_result()

        return self._build_result(
            tile_details,
            total_bits_available=total_bits_available,
            strategy=strategy,
            channel=channel,
        )

    # ══════════════════════════════════════════════════════════════
    # Tile extraction: legacy boundary search (for DCT, generic)
    # ══════════════════════════════════════════════════════════════

    def _analyze_bitstream_legacy(
        self,
        bitstream: str,
        total_bits_available: int = 0,
        strategy: str = "LSB",
        channel: int = -1,
    ) -> SpectrumResult:
        """Búsqueda tradicional de boundaries (header+footer).

        Útil para formatos donde el payload no se repite continuamente.
        """
        if len(bitstream) < 100:
            return self._empty_result()

        # Buscar boundaries con thresholds progresivos
        boundaries = None
        for threshold in [0.85, 0.75, 0.65]:
            boundaries = find_payload_boundaries(bitstream, threshold=threshold)
            if boundaries:
                break
        if not boundaries:
            return self._empty_result()

        # Filtrar por longitud razonable
        valid = [
            (s, e) for s, e in boundaries
            if 700 <= (e - s) <= 2500 and (e - s) % 8 == 0
        ]
        if not valid:
            return self._empty_result()

        # Agrupar por longitud más frecuente
        length_counts = Counter(e - s for s, e in valid)
        target_length = length_counts.most_common(1)[0][0]

        filtered = sorted(
            [(s, e) for s, e in valid if (e - s) == target_length],
            key=lambda x: x[0],
        )

        # Dededup
        deduped = []
        last_start = -target_length
        for s, e in filtered:
            if s - last_start > target_length // 2:
                deduped.append((s, e))
                last_start = s

        if not deduped:
            return self._empty_result()

        # Procesar tiles
        tile_details = []
        for idx, (start, end) in enumerate(deduped):
            payload_bits = bitstream[start:end]

            h_corr = self._compute_sync_correlation(
                bitstream, start - SYNC_SEQUENCE_LENGTH, True
            )
            f_corr = self._compute_sync_correlation(
                bitstream, end, False
            )

            tile = TileRecovery(
                index=idx,
                position_start=start,
                position_end=end,
                payload_length_bits=end - start,
                raw_bits=payload_bits,
                sync_header_corr=h_corr,
                sync_footer_corr=f_corr,
            )

            try:
                payload_bytes = self._bits_to_bytes(payload_bits)
                payload = HBitPayload.deserialize_core(payload_bytes)
                tile.valid_payload = True
                tile.author_hash = payload.author_hash.hex()
                tile.content_hash = payload.content_hash.hex()
                tile.origin_type = payload.origin_type.name
                tile.ai_model_id = (
                    payload.ai_model_id.hex()
                    if payload.has_ai_model_id else None
                )
                tile.timestamp = payload.timestamp
                tile.version = payload.version
            except (ValueError, struct.error, IndexError, Exception) as e:
                tile.error_message = str(e)[:100]

            tile_details.append(tile)

        return self._build_result(
            tile_details,
            total_bits_available=total_bits_available,
            strategy=strategy,
            channel=channel,
        )

    # ══════════════════════════════════════════════════════════════
    # Result building
    # ══════════════════════════════════════════════════════════════

    def _build_result(
        self,
        tile_details: list,
        total_bits_available: int = 0,
        strategy: str = "",
        channel: int = -1,
    ) -> SpectrumResult:
        """Construye SpectrumResult desde tiles analizados."""
        valid_tiles = [t for t in tile_details if t.valid_payload]

        if not valid_tiles:
            return SpectrumResult(
                confidence=0.0,
                verdict=SpectrumVerdict.NO_EVIDENCE,
                tiles_total=len(tile_details),
                tiles_recovered=len(tile_details),
                payloads_valid=0,
                author_consensus=0.0,
                content_consensus=0.0,
                origin_consensus=0.0,
                ecc_total_corrections=0,
                ecc_failures=0,
                sync_quality=0.0,
                payload_completeness=0.0,
                author_hash=None,
                content_hash=None,
                origin_type=None,
                ai_model_id=None,
                tile_details=tile_details,
                total_bits_available=total_bits_available,
                analysis_summary="No se encontraron payloads H-Bit válidos.",
            )

        # Consenso
        author_votes = Counter(t.author_hash for t in valid_tiles)
        content_votes = Counter(t.content_hash for t in valid_tiles)
        origin_votes = Counter(t.origin_type for t in valid_tiles)

        consensus_author = author_votes.most_common(1)[0][0]
        consensus_content = content_votes.most_common(1)[0][0]
        consensus_origin = origin_votes.most_common(1)[0][0]

        author_consensus = author_votes[consensus_author] / len(valid_tiles)
        content_consensus = content_votes[consensus_content] / len(valid_tiles)
        origin_consensus = origin_votes[consensus_origin] / len(valid_tiles)

        # ECC
        ecc_corrections = sum(t.ecc_corrections for t in valid_tiles)
        ecc_failures = sum(1 for t in valid_tiles if t.ecc_failed)

        # Sync quality
        sync_quality = float(np.clip(np.mean([
            (t.sync_header_corr + t.sync_footer_corr) / 2
            for t in tile_details
        ]), 0.0, 1.0)) if tile_details else 0.0

        # Payload completeness
        ideal_bits = 856  # core size in bits
        payload_completeness = min(
            1.0,
            max(t.payload_length_bits for t in valid_tiles) / ideal_bits,
        )

        # Confidence
        confidence = self._compute_confidence(
            tiles_recovered=len(tile_details),
            payloads_valid=len(valid_tiles),
            author_consensus=author_consensus,
            content_consensus=content_consensus,
            ecc_corrections=ecc_corrections,
            ecc_failures=ecc_failures,
            sync_quality=sync_quality,
            payload_completeness=payload_completeness,
        )

        verdict = self._verdict_from_confidence(confidence)

        # AI model ID consensus
        ai_votes = Counter(
            t.ai_model_id for t in valid_tiles if t.ai_model_id
        )
        ai_model = ai_votes.most_common(1)[0][0] if ai_votes else None

        # Summary
        summary = self._build_summary(
            confidence, verdict, len(tile_details),
            len(valid_tiles), author_consensus,
            ecc_corrections, sync_quality, strategy, channel,
        )

        return SpectrumResult(
            confidence=confidence,
            verdict=verdict,
            tiles_total=len(tile_details),
            tiles_recovered=len(tile_details),
            payloads_valid=len(valid_tiles),
            author_consensus=author_consensus,
            content_consensus=content_consensus,
            origin_consensus=origin_consensus,
            ecc_total_corrections=ecc_corrections,
            ecc_failures=ecc_failures,
            sync_quality=sync_quality,
            payload_completeness=payload_completeness,
            author_hash=consensus_author if author_consensus > 0.5 else None,
            content_hash=consensus_content if content_consensus > 0.5 else None,
            origin_type=consensus_origin if origin_consensus > 0.5 else None,
            ai_model_id=ai_model,
            tile_details=tile_details,
            total_bits_available=total_bits_available,
            analysis_summary=summary,
        )

    # ══════════════════════════════════════════════════════════════
    # Helpers
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def _bits_to_bytes(bit_string: str) -> bytes:
        n = (len(bit_string) // 8) * 8
        return bytes(int(bit_string[i:i + 8], 2) for i in range(0, n, 8))

    @staticmethod
    def _correlation(segment: str, pattern: str) -> float:
        """Correlación simple entre segmento y patrón."""
        if len(segment) < len(pattern):
            return 0.0
        seg = segment[:len(pattern)]
        matches = sum(1 for a, b in zip(seg, pattern) if a == b)
        return matches / len(pattern)

    @staticmethod
    def _compute_sync_correlation(
        bitstream: str, position: int, search_header: bool
    ) -> float:
        try:
            seg = bitstream[
                max(0, position):position + SYNC_SEQUENCE_LENGTH
            ]
            if len(seg) < SYNC_SEQUENCE_LENGTH:
                return 0.0
            pattern = SYNC_HEADER_BITS if search_header else SYNC_FOOTER_BITS
            matches = sum(1 for a, b in zip(seg, pattern) if a == b)
            return matches / len(pattern)
        except (IndexError, ValueError):
            return 0.0

    @staticmethod
    def _compute_confidence(
        tiles_recovered: int,
        payloads_valid: int,
        author_consensus: float,
        content_consensus: float,
        ecc_corrections: int,
        ecc_failures: int,
        sync_quality: float,
        payload_completeness: float,
    ) -> float:
        validity_rate = payloads_valid / max(tiles_recovered, 1)
        if ecc_failures > 0:
            ecc_health = max(0.0, 0.5 - 0.1 * ecc_failures)
        else:
            ecc_health = max(0.0, 1.0 - 0.02 * ecc_corrections)
        combined_consensus = (author_consensus + content_consensus) / 2

        confidence = (
            0.30 * validity_rate
            + 0.25 * combined_consensus
            + 0.20 * ecc_health
            + 0.15 * sync_quality
            + 0.10 * payload_completeness
        )
        return float(np.clip(confidence, 0.0, 1.0))

    @staticmethod
    def _verdict_from_confidence(confidence: float) -> str:
        if confidence >= 0.95:
            return SpectrumVerdict.AUTHENTIC
        elif confidence >= 0.75:
            return SpectrumVerdict.LIKELY_AUTHENTIC
        elif confidence >= 0.50:
            return SpectrumVerdict.POSSIBLY_AUTHENTIC
        elif confidence >= 0.25:
            return SpectrumVerdict.UNCERTAIN
        elif confidence > 0.0:
            return SpectrumVerdict.LIKELY_TAMPERED
        return SpectrumVerdict.NO_EVIDENCE

    @staticmethod
    def _build_summary(
        confidence: float,
        verdict: str,
        tiles_found: int,
        payloads_valid: int,
        author_consensus: float,
        ecc_corrections: int,
        sync_quality: float,
        strategy: str,
        channel: int = -1,
    ) -> str:
        labels = {
            SpectrumVerdict.AUTHENTIC: "AUTÉNTICO — Verificación completa",
            SpectrumVerdict.LIKELY_AUTHENTIC: "PROBABLEMENTE AUTÉNTICO — Alta confianza",
            SpectrumVerdict.POSSIBLY_AUTHENTIC: "POSIBLEMENTE AUTÉNTICO — Confianza moderada",
            SpectrumVerdict.UNCERTAIN: "INCIERTO — Evidencia insuficiente",
            SpectrumVerdict.LIKELY_TAMPERED: "PROBABLEMENTE MANIPULADO — Baja confianza",
            SpectrumVerdict.NO_EVIDENCE: "SIN EVIDENCIA — No se detectó firma H-Bit",
        }
        parts = [
            f"Veredicto: {labels.get(verdict, verdict)}",
            f"Confianza: {confidence:.1%}",
            f"Tiles: {payloads_valid}/{tiles_found} válidos",
            f"Consenso autor: {author_consensus:.1%}",
        ]
        if ecc_corrections > 0:
            parts.append(f"ECC: {ecc_corrections} correcciones")
        if channel >= 0:
            parts.append(f"Canal: {['R','G','B'][channel]}")
        if strategy:
            parts.append(f"Estrategia: {strategy}")
        return " | ".join(parts)

    @staticmethod
    def _empty_result() -> SpectrumResult:
        return SpectrumResult(
            confidence=0.0,
            verdict=SpectrumVerdict.NO_EVIDENCE,
            tiles_total=0,
            tiles_recovered=0,
            payloads_valid=0,
            author_consensus=0.0,
            content_consensus=0.0,
            origin_consensus=0.0,
            ecc_total_corrections=0,
            ecc_failures=0,
            sync_quality=0.0,
            payload_completeness=0.0,
            author_hash=None,
            content_hash=None,
            origin_type=None,
            ai_model_id=None,
            total_bits_available=0,
            analysis_summary="No se detectó firma H-Bit en el archivo.",
        )
