"""
Handler de audio para H-Bit.

Incrusta bits H-Bit en muestras de audio PCM sin pérdida.

Estrategia principal: LSB en muestras de 16/24 bits (WAV, FLAC).
Para audio comprimido (MP3, OGG), solo se pueden leer metadatos;
la incrustación LSB no sobrevive la compresión con pérdida.

La capacidad es proporcional a: sample_rate × duration × channels.
Un audio WAV de 1 min a 44.1 kHz stereo ofrece ~5.3M bits de capacidad.
"""

from __future__ import annotations

import io
import struct
import wave
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


class AudioHandler(MediaHandler):
    """Handler para formatos de audio sin pérdida (WAV, FLAC).

    Incrusta bits en el LSB de las muestras de audio PCM.
    La alteración es imperceptible: cambiar el LSB de una muestra
    de 16 bits produce un error de ±1/65536, inaudible.

    Formatos soportados:
    - WAV: lectura/escritura completa
    - FLAC: lectura/escritura (requiere soundfile)
    - MP3/OGG: solo extracción de metadatos (no embedding)
    """

    @property
    def category(self) -> MediaCategory:
        return MediaCategory.AUDIO

    @property
    def supported_extensions(self) -> list[str]:
        return ["wav", "flac", "aiff"]

    def load(self, path: Path) -> CarrierData:
        """Carga un archivo de audio y extrae las muestras PCM.

        Args:
            path: Ruta al archivo de audio.

        Returns:
            CarrierData con las muestras PCM como raw_data.
        """
        ext = path.suffix.lower().lstrip(".")

        if ext == "wav":
            return self._load_wav(path)
        elif ext in ("flac", "aiff"):
            return self._load_soundfile(path)
        else:
            raise ValueError(f"Formato de audio no soportado: {ext}")

    def save(self, data: bytes, path: Path, carrier: CarrierData) -> Path:
        """Guarda las muestras PCM modificadas al formato de audio.

        Args:
            data: Muestras PCM modificadas.
            path: Ruta de salida.
            carrier: CarrierData original.

        Returns:
            Path del archivo guardado.
        """
        ext = path.suffix.lower().lstrip(".")
        path.parent.mkdir(parents=True, exist_ok=True)

        if ext == "wav":
            self._save_wav(data, path, carrier)
        elif ext in ("flac", "aiff"):
            self._save_soundfile(data, path, carrier)
        else:
            # Fallback a WAV
            self._save_wav(data, path.with_suffix(".wav"), carrier)
            path = path.with_suffix(".wav")

        return path

    def embed(self, carrier: CarrierData, payload_bits: str) -> EmbedResult:
        """Incrusta bits en el LSB de las muestras PCM.

        Args:
            carrier: Datos de audio cargados.
            payload_bits: Bits a incrustar.

        Returns:
            EmbedResult con el audio modificado.
        """
        sample_width = carrier.metadata["sample_width"]
        samples = bytearray(carrier.raw_data)
        num_samples = len(samples) // sample_width

        if len(payload_bits) > num_samples:
            raise ValueError(
                f"Payload ({len(payload_bits)} bits) excede capacidad "
                f"del audio ({num_samples} muestras)"
            )

        bits_embedded = 0

        if sample_width == 2:  # 16-bit PCM
            for i, bit in enumerate(payload_bits):
                offset = i * 2
                # Little-endian int16
                sample = struct.unpack_from("<h", samples, offset)[0]
                # Modificar LSB
                if bit == "1":
                    sample = sample | 1
                else:
                    sample = sample & ~1
                struct.pack_into("<h", samples, offset, sample)
                bits_embedded += 1

        elif sample_width == 3:  # 24-bit PCM
            for i, bit in enumerate(payload_bits):
                offset = i * 3
                # 24-bit little-endian
                b0 = samples[offset]
                if bit == "1":
                    b0 = b0 | 1
                else:
                    b0 = b0 & ~1
                samples[offset] = b0
                bits_embedded += 1

        else:  # 8-bit u otro
            for i, bit in enumerate(payload_bits):
                if bit == "1":
                    samples[i] = samples[i] | 1
                else:
                    samples[i] = samples[i] & ~1
                bits_embedded += 1

        return EmbedResult(
            output_data=bytes(samples),
            bits_embedded=bits_embedded,
            capacity_used=bits_embedded / num_samples if num_samples > 0 else 0,
            strategy_used=EmbeddingStrategy.LSB,
        )

    def extract(
        self,
        carrier: CarrierData,
        expected_length: Optional[int] = None,
    ) -> ExtractResult:
        """Extrae bits del LSB de las muestras PCM.

        Args:
            carrier: Datos de audio cargados.
            expected_length: Número de bits a extraer.

        Returns:
            ExtractResult con los bits extraídos.
        """
        sample_width = carrier.metadata["sample_width"]
        samples = carrier.raw_data
        num_samples = len(samples) // sample_width

        max_bits = expected_length or num_samples
        max_bits = min(max_bits, num_samples)

        bits = []

        if sample_width == 2:
            for i in range(max_bits):
                offset = i * 2
                sample = struct.unpack_from("<h", samples, offset)[0]
                bits.append(str(sample & 1))
        elif sample_width == 3:
            for i in range(max_bits):
                offset = i * 3
                bits.append(str(samples[offset] & 1))
        else:
            for i in range(max_bits):
                bits.append(str(samples[i] & 1))

        return ExtractResult(
            payload_bits="".join(bits),
            confidence=0.9,  # LSB en audio sin pérdida es muy confiable
            strategy_used=EmbeddingStrategy.LSB,
            payloads_found=1 if bits else 0,
        )

    def _load_wav(self, path: Path) -> CarrierData:
        """Carga un archivo WAV."""
        with wave.open(str(path), "rb") as wf:
            n_channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            framerate = wf.getframerate()
            n_frames = wf.getnframes()
            raw_data = wf.readframes(n_frames)

        num_samples = n_frames * n_channels

        return CarrierData(
            raw_data=raw_data,
            metadata={
                "channels": n_channels,
                "sample_width": sample_width,
                "framerate": framerate,
                "n_frames": n_frames,
                "format": "WAV",
            },
            capacity_bits=num_samples,
            strategy=EmbeddingStrategy.LSB,
            category=MediaCategory.AUDIO,
            original_path=path,
        )

    def _save_wav(self, data: bytes, path: Path, carrier: CarrierData) -> None:
        """Guarda muestras PCM como WAV."""
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(carrier.metadata["channels"])
            wf.setsampwidth(carrier.metadata["sample_width"])
            wf.setframerate(carrier.metadata["framerate"])
            wf.writeframes(data)

    def _load_soundfile(self, path: Path) -> CarrierData:
        """Carga audio con soundfile (FLAC, AIFF)."""
        try:
            import soundfile as sf
        except ImportError:
            raise ImportError(
                "soundfile es necesario para FLAC/AIFF. "
                "Instalar con: pip install soundfile"
            )

        data, samplerate = sf.read(str(path), dtype="int16")
        raw_bytes = data.tobytes()

        if data.ndim == 1:
            n_channels = 1
            n_frames = len(data)
        else:
            n_channels = data.shape[1]
            n_frames = data.shape[0]

        return CarrierData(
            raw_data=raw_bytes,
            metadata={
                "channels": n_channels,
                "sample_width": 2,  # int16
                "framerate": samplerate,
                "n_frames": n_frames,
                "format": path.suffix.upper().lstrip("."),
            },
            capacity_bits=n_frames * n_channels,
            strategy=EmbeddingStrategy.LSB,
            category=MediaCategory.AUDIO,
            original_path=path,
        )

    def _save_soundfile(self, data: bytes, path: Path, carrier: CarrierData) -> None:
        """Guarda audio con soundfile (FLAC, AIFF)."""
        try:
            import soundfile as sf
            import numpy as np
        except ImportError:
            raise ImportError("soundfile es necesario para FLAC/AIFF.")

        n_channels = carrier.metadata["channels"]
        samples = np.frombuffer(data, dtype=np.int16)

        if n_channels > 1:
            samples = samples.reshape(-1, n_channels)

        sf.write(
            str(path),
            samples,
            samplerate=carrier.metadata["framerate"],
        )
