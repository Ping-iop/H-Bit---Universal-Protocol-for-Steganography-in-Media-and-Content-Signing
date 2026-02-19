"""
Handler de video para H-Bit.

Incrusta bits H-Bit en los keyframes (I-frames) del video.

Estrategia: LSB en los canales RGB de frames seleccionados.
Cada keyframe se trata como una imagen independiente, aplicando
la misma técnica LSB del ImageHandler pero distribuida
temporalmente.

Dependencia: OpenCV (cv2) para lectura/escritura de video.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Optional

from hbit.formats.base import (
    MediaHandler,
    CarrierData,
    EmbedResult,
    ExtractResult,
    EmbeddingStrategy,
    MediaCategory,
)


class VideoHandler(MediaHandler):
    """Handler para formatos de video (MP4, AVI, MOV, MKV).

    Incrusta bits en los keyframes del video usando LSB.
    Los keyframes se seleccionan uniformemente a lo largo
    del video para maximizar la resiliencia ante recorte temporal.

    Nota: La escritura de video requiere re-codificación, lo que
    puede introducir pérdidas. Se recomienda usar codecs sin
    pérdida (FFV1, Huffyuv) para máxima fidelidad.
    """

    @property
    def category(self) -> MediaCategory:
        return MediaCategory.VIDEO

    @property
    def supported_extensions(self) -> list[str]:
        return ["mp4", "avi", "mov", "mkv", "webm"]

    def load(self, path: Path) -> CarrierData:
        """Carga un video y extrae keyframes como carrier data.

        Args:
            path: Ruta al archivo de video.

        Returns:
            CarrierData con los keyframes concatenados.
        """
        try:
            import cv2
        except ImportError:
            raise ImportError(
                "OpenCV (cv2) es necesario para procesar video. "
                "Instalar con: pip install opencv-python"
            )

        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            raise ValueError(f"No se pudo abrir el video: {path}")

        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))

        # Extraer keyframes (1 cada N frames, máx 30)
        keyframe_interval = max(1, total_frames // 30)
        keyframes = []
        frame_indices = []

        for i in range(0, total_frames, keyframe_interval):
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ret, frame = cap.read()
            if ret:
                # BGR → RGB
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                keyframes.append(frame_rgb.tobytes())
                frame_indices.append(i)

            if len(keyframes) >= 30:
                break

        cap.release()

        # Concatenar keyframes
        raw_data = b"".join(keyframes)
        pixels_per_frame = height * width
        capacity = pixels_per_frame * len(keyframes)

        return CarrierData(
            raw_data=raw_data,
            metadata={
                "width": width,
                "height": height,
                "fps": fps,
                "total_frames": total_frames,
                "fourcc": fourcc,
                "keyframe_count": len(keyframes),
                "keyframe_indices": frame_indices,
                "frame_shape": (height, width, 3),
                "bytes_per_frame": height * width * 3,
                "format": path.suffix.upper().lstrip("."),
            },
            capacity_bits=capacity,
            strategy=EmbeddingStrategy.LSB,
            category=MediaCategory.VIDEO,
            original_path=path,
            format_info={"fourcc": fourcc},
        )

    def save(self, data: bytes, path: Path, carrier: CarrierData) -> Path:
        """Re-ensambla el video con keyframes modificados.

        Args:
            data: Keyframes modificados concatenados.
            path: Ruta de salida.
            carrier: CarrierData original.

        Returns:
            Path del archivo guardado.
        """
        try:
            import cv2
            import numpy as np
        except ImportError:
            raise ImportError("OpenCV (cv2) es necesario para procesar video.")

        path.parent.mkdir(parents=True, exist_ok=True)

        width = carrier.metadata["width"]
        height = carrier.metadata["height"]
        fps = carrier.metadata["fps"]
        frame_shape = carrier.metadata["frame_shape"]
        bytes_per_frame = carrier.metadata["bytes_per_frame"]
        keyframe_indices = carrier.metadata["keyframe_indices"]

        # Decodificar keyframes modificados
        modified_frames = {}
        for i in range(len(keyframe_indices)):
            offset = i * bytes_per_frame
            frame_bytes = data[offset:offset + bytes_per_frame]
            if len(frame_bytes) == bytes_per_frame:
                frame = np.frombuffer(frame_bytes, dtype=np.uint8).reshape(frame_shape)
                modified_frames[keyframe_indices[i]] = frame

        # Re-ensamblar video
        source_path = carrier.original_path
        cap = cv2.VideoCapture(str(source_path))

        # Usar codec sin pérdida para máxima fidelidad
        ext = path.suffix.lower()
        if ext == ".avi":
            fourcc = cv2.VideoWriter_fourcc(*"FFV1")
        else:
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")

        out = cv2.VideoWriter(str(path), fourcc, fps, (width, height))

        frame_idx = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx in modified_frames:
                # Usar frame modificado (RGB → BGR)
                modified = cv2.cvtColor(
                    modified_frames[frame_idx], cv2.COLOR_RGB2BGR
                )
                out.write(modified)
            else:
                out.write(frame)

            frame_idx += 1

        cap.release()
        out.release()

        return path

    def embed(self, carrier: CarrierData, payload_bits: str) -> EmbedResult:
        """Incrusta bits en CADA keyframe del video via LSB (multi-keyframe).

        Cada keyframe recibe una copia completa del payload para
        maximizar la resiliencia. Si el payload se pierde en algunos
        keyframes (por re-encoding o recorte temporal), la mayoría
        de las copias siguen intactas.

        Los bits se incrustan en el canal azul (offset +2 de cada triple RGB)
        para máxima imperceptibilidad.

        Args:
            carrier: Datos del video cargados.
            payload_bits: Bits a incrustar.

        Returns:
            EmbedResult con los keyframes modificados.
        """
        bytes_per_frame = carrier.metadata["bytes_per_frame"]
        keyframe_count = carrier.metadata["keyframe_count"]
        width = carrier.metadata["width"]
        height = carrier.metadata["height"]

        pixels_per_frame = width * height
        payload_len = len(payload_bits)

        if payload_len > pixels_per_frame:
            raise ValueError(
                f"Payload ({payload_len} bits) excede capacidad "
                f"de un keyframe ({pixels_per_frame} píxeles)"
            )

        samples = bytearray(carrier.raw_data)
        total_bits_embedded = 0

        # Incrustar una copia completa del payload en CADA keyframe
        for kf_idx in range(keyframe_count):
            frame_offset = kf_idx * bytes_per_frame

            # Incrustar en el canal azul (byte offset +2 de cada pixel RGB)
            for bit_idx, bit in enumerate(payload_bits):
                if bit_idx >= pixels_per_frame:
                    break

                # Posición del canal azul del pixel bit_idx en este frame
                pixel_byte = frame_offset + (bit_idx * 3) + 2
                if pixel_byte >= len(samples):
                    break

                if bit == "1":
                    samples[pixel_byte] = samples[pixel_byte] | 1
                else:
                    samples[pixel_byte] = samples[pixel_byte] & ~1

                total_bits_embedded += 1

        total_capacity = pixels_per_frame * keyframe_count
        return EmbedResult(
            output_data=bytes(samples),
            bits_embedded=total_bits_embedded,
            capacity_used=total_bits_embedded / total_capacity if total_capacity > 0 else 0,
            strategy_used=EmbeddingStrategy.LSB,
        )

    def extract(
        self,
        carrier: CarrierData,
        expected_length: Optional[int] = None,
    ) -> ExtractResult:
        """Extrae bits de CADA keyframe y reconstruye por mayoría.

        Cada keyframe contiene una copia independiente del payload.
        Se extraen todas las copias y se reconstruye el payload
        original usando votación por mayoría (majority vote) bit a bit.

        Args:
            carrier: Datos del video cargados.
            expected_length: Número de bits a extraer por copia.

        Returns:
            ExtractResult con los bits reconstruidos.
        """
        samples = carrier.raw_data
        bytes_per_frame = carrier.metadata["bytes_per_frame"]
        keyframe_count = carrier.metadata["keyframe_count"]
        width = carrier.metadata["width"]
        height = carrier.metadata["height"]
        pixels_per_frame = width * height

        # Determinar longitud de extracción
        extract_len = expected_length or pixels_per_frame
        extract_len = min(extract_len, pixels_per_frame)

        # Extraer una copia del payload desde cada keyframe
        copies: list[str] = []
        for kf_idx in range(keyframe_count):
            frame_offset = kf_idx * bytes_per_frame
            frame_bits = []

            for bit_idx in range(extract_len):
                pixel_byte = frame_offset + (bit_idx * 3) + 2
                if pixel_byte >= len(samples):
                    break
                frame_bits.append(str(samples[pixel_byte] & 1))

            if len(frame_bits) == extract_len:
                copies.append("".join(frame_bits))

        if not copies:
            return ExtractResult(
                payload_bits="",
                confidence=0.0,
                strategy_used=EmbeddingStrategy.LSB,
                payloads_found=0,
            )

        # Majority vote across all copies
        if len(copies) == 1:
            result_bits = copies[0]
            confidence = 0.6
        else:
            result_bits, confidence = self._majority_vote(copies)

        return ExtractResult(
            payload_bits=result_bits,
            confidence=confidence,
            strategy_used=EmbeddingStrategy.LSB,
            payloads_found=len(copies),
        )

    @staticmethod
    def _majority_vote(copies: list[str]) -> tuple[str, float]:
        """Reconstruye payload por votación por mayoría bit a bit.

        Para cada posición de bit, cuenta los votos '1' vs '0' de
        todas las copias y elige el mayoritario.

        Returns:
            Tupla (bits reconstruidos, confianza promedio).
        """
        if not copies:
            return "", 0.0

        length = len(copies[0])
        num_copies = len(copies)
        result = []
        confidence_sum = 0.0

        for pos in range(length):
            ones = sum(1 for c in copies if c[pos] == "1")
            zeros = num_copies - ones

            if ones >= zeros:
                result.append("1")
                confidence_sum += ones / num_copies
            else:
                result.append("0")
                confidence_sum += zeros / num_copies

        avg_confidence = confidence_sum / length if length > 0 else 0.0
        return "".join(result), avg_confidence

