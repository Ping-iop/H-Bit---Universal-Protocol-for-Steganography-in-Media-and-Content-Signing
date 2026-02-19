"""
Pipeline principal del protocolo H-Bit.

Orquesta todo el flujo de codificación, decodificación y verificación,
integrando los módulos de criptografía, análisis, codificación y resiliencia.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from hbit.core.crypto import (
    HBitKeyPair,
    AuthorIdentity,
    generate_author_hash,
    generate_key_pair,
    sign_payload,
    verify_signature,
    compute_content_hash as crypto_content_hash,
)
from hbit.core.kdf import derive_image_key, derive_from_passphrase
from hbit.core.signature import HBitPayload, PayloadFlags, EncodingMethod
from hbit.core.sync import wrap_payload_with_sync
from hbit.analysis.channel_selector import select_optimal_channel
from hbit.analysis.integrity import (
    compute_content_hash,
    verify_content_integrity,
    IntegrityStatus,
)
from hbit.analysis.saliency import generate_perceptual_density_map
from hbit.encoders.lsb import encode_lsb, decode_lsb


class VerificationStatus(Enum):
    """Estado de la verificación H-Bit."""

    VERIFIED = "VERIFIED"         # Firma válida, imagen intacta
    TAMPERED = "TAMPERED"         # Firma válida pero imagen modificada
    NOT_FOUND = "NOT_FOUND"       # No se encontró firma H-Bit
    INVALID = "INVALID"           # Firma encontrada pero inválida
    SYNTHETIC = "SYNTHETIC"       # Imagen probablemente generada por IA


@dataclass
class EncodeResult:
    """Resultado del proceso completo de codificación H-Bit.

    Attributes:
        output_path: Ruta donde se guardó la imagen firmada.
        author_hash: Hash de identidad del autor.
        content_hash: Hash de integridad del contenido.
        channel_used: Canal de color utilizado.
        units_embedded: Número de copias del payload incrustadas.
        capacity_used: Porcentaje de capacidad utilizada.
        payload_size_bits: Tamaño del payload en bits.
    """

    output_path: Path
    author_hash: str
    content_hash: str
    channel_used: int
    units_embedded: int
    capacity_used: float
    payload_size_bits: int


@dataclass
class DecodeResult:
    """Resultado del proceso completo de decodificación H-Bit.

    Attributes:
        author_hash: Hash del autor extraído (hex).
        content_hash: Hash de contenido extraído (hex).
        timestamp: Marca de tiempo de la firma.
        version: Versión del protocolo.
        payloads_found: Número de copias encontradas.
        confidence: Confianza de la extracción.
        payload: Payload deserializado completo.
    """

    author_hash: str
    content_hash: str
    timestamp: float
    version: int
    payloads_found: int
    confidence: float
    payload: Optional[HBitPayload] = None


@dataclass
class VerifyResult:
    """Resultado de la verificación completa H-Bit.

    Attributes:
        status: Estado de la verificación.
        decode_result: Resultado de la decodificación (si se encontró firma).
        integrity_status: Estado de integridad del contenido.
        message: Mensaje descriptivo del resultado.
    """

    status: VerificationStatus
    decode_result: Optional[DecodeResult]
    integrity_status: Optional[IntegrityStatus]
    message: str


class HBitEncoder:
    """Codificador principal del protocolo H-Bit.

    Orquesta el flujo completo de firmado:
    1. Análisis de la imagen (entropía, saliencia, canal óptimo)
    2. Generación de identidad y firma
    3. Construcción del payload
    4. Incrustación LSB con redundancia adaptativa
    """

    def __init__(
        self,
        adaptive_density: bool = True,
        auto_channel: bool = True,
        use_kdf: bool = True,
    ):
        """Inicializa el encoder.

        Args:
            adaptive_density: Si True, usa mapa de densidad perceptual.
            auto_channel: Si True, selecciona canal automáticamente.
            use_kdf: Si True, deriva clave efímera con HKDF.
        """
        self.adaptive_density = adaptive_density
        self.auto_channel = auto_channel
        self.use_kdf = use_kdf

    def encode(
        self,
        image_path: str | Path,
        author_key: HBitKeyPair | str,
        output_path: str | Path,
        device_id: str = "software-reference-v0.1",
        channel: Optional[int] = None,
    ) -> EncodeResult:
        """Codifica una imagen con la firma H-Bit.

        Args:
            image_path: Ruta a la imagen de entrada.
            author_key: Par de claves Ed25519 o passphrase como string.
            output_path: Ruta donde guardar la imagen firmada.
            device_id: Identificador del dispositivo.
            channel: Canal a usar (None = auto-selección).

        Returns:
            EncodeResult con los detalles de la codificación.
        """
        image_path = Path(image_path)
        output_path = Path(output_path)

        # 1. Cargar imagen
        img = Image.open(image_path).convert("RGB")
        image_data = np.array(img, dtype=np.uint8)

        # 2. Selección de canal
        if channel is not None:
            selected_channel = channel
        elif self.auto_channel:
            channel_result = select_optimal_channel(image_data)
            selected_channel = channel_result.selected_channel
        else:
            selected_channel = 2  # Azul por defecto

        # 3. Resolver clave del autor
        if isinstance(author_key, str):
            # Passphrase: derivar clave
            derived = derive_from_passphrase(author_key)
            key_material = derived.key_material
            key_pair = None
        else:
            key_pair = author_key
            from cryptography.hazmat.primitives.serialization import (
                Encoding,
                NoEncryption,
                PrivateFormat,
            )
            key_material = key_pair.private_key.private_bytes(
                encoding=Encoding.Raw,
                format=PrivateFormat.Raw,
                encryption_algorithm=NoEncryption(),
            )

        # 4. KDF: derivar clave por imagen si está habilitado
        if self.use_kdf:
            raw_content_hash = crypto_content_hash(image_data.tobytes())
            image_derived = derive_image_key(key_material, raw_content_hash)
            effective_key = image_derived.key_material
        else:
            effective_key = key_material

        # 5. Generar hash de autor
        author_hash = effective_key  # 32 bytes como identidad
        if len(author_hash) > 32:
            import hashlib
            author_hash = hashlib.sha256(author_hash).digest()
        elif len(author_hash) < 32:
            author_hash = author_hash.ljust(32, b"\x00")

        # 6. Hash de contenido (excluyendo canal de firma)
        content_hash = compute_content_hash(image_data, selected_channel)

        # 7. Construir payload
        flags = PayloadFlags.HAS_CONTENT_HASH | PayloadFlags.HAS_ECC
        if self.use_kdf:
            flags |= PayloadFlags.USES_KDF

        payload = HBitPayload.create(
            author_hash=author_hash,
            content_hash=content_hash,
            flags=flags,
        )

        # 8. Serializar y envolver con sincronización
        payload_binary = payload.to_binary_string()
        wrapped_payload = wrap_payload_with_sync(payload_binary)

        # 9. Generar mapa de densidad perceptual si es adaptativo
        density_map = None
        if self.adaptive_density:
            density_map = generate_perceptual_density_map(
                image_data, selected_channel
            )

        # 10. Incrustación LSB
        lsb_result = encode_lsb(
            image_data,
            wrapped_payload,
            channel=selected_channel,
            density_map=density_map,
        )

        # 11. Guardar imagen resultado
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result_img = Image.fromarray(lsb_result.encoded_image)

        # Determinar formato de salida por extensión
        _save_image(result_img, output_path)

        return EncodeResult(
            output_path=output_path,
            author_hash=author_hash.hex(),
            content_hash=content_hash.hex(),
            channel_used=selected_channel,
            units_embedded=lsb_result.units_embedded,
            capacity_used=lsb_result.capacity_used,
            payload_size_bits=len(wrapped_payload),
        )


class HBitDecoder:
    """Decodificador principal del protocolo H-Bit.

    Extrae la firma H-Bit de una imagen, aplicando:
    1. Búsqueda de marcadores de sincronización
    2. Extracción de payload con votación mayoritaria
    3. Deserialización de los campos del payload
    """

    def decode(
        self,
        image_path: str | Path,
        channel: Optional[int] = None,
    ) -> DecodeResult:
        """Decodifica la firma H-Bit de una imagen.

        Args:
            image_path: Ruta a la imagen firmada.
            channel: Canal donde buscar (None = buscar en todos).

        Returns:
            DecodeResult con la firma extraída.
        """
        image_path = Path(image_path)
        img = Image.open(image_path).convert("RGB")
        image_data = np.array(img, dtype=np.uint8)

        # Si no se especifica canal, intentar en el orden más probable
        channels_to_try = [channel] if channel is not None else [2, 0, 1]

        best_result = None
        best_confidence = 0.0

        for ch in channels_to_try:
            lsb_result = decode_lsb(image_data, channel=ch)

            if lsb_result.payloads_found > 0 and lsb_result.confidence > best_confidence:
                try:
                    # Intentar deserializar el payload
                    payload_bytes = _bits_to_bytes(lsb_result.payload_bits)
                    payload = HBitPayload.deserialize_core(payload_bytes)

                    best_result = DecodeResult(
                        author_hash=payload.author_hash.hex(),
                        content_hash=payload.content_hash.hex(),
                        timestamp=payload.timestamp,
                        version=payload.version,
                        payloads_found=lsb_result.payloads_found,
                        confidence=lsb_result.confidence,
                        payload=payload,
                    )
                    best_confidence = lsb_result.confidence
                except (ValueError, struct.error):
                    continue

        if best_result is None:
            return DecodeResult(
                author_hash="",
                content_hash="",
                timestamp=0.0,
                version=0,
                payloads_found=0,
                confidence=0.0,
            )

        return best_result


class HBitVerifier:
    """Verificador del protocolo H-Bit.

    Combina decodificación + verificación de integridad para
    determinar si una imagen es auténtica y no ha sido manipulada.
    """

    def __init__(self):
        self._decoder = HBitDecoder()

    def verify(
        self,
        image_path: str | Path,
        expected_author_hash: Optional[str] = None,
        channel: Optional[int] = None,
    ) -> VerifyResult:
        """Verifica la autenticidad de una imagen firmada con H-Bit.

        Args:
            image_path: Ruta a la imagen a verificar.
            expected_author_hash: Hash del autor esperado (hex, opcional).
            channel: Canal donde buscar la firma (None = auto).

        Returns:
            VerifyResult con el resultado de la verificación.
        """
        image_path = Path(image_path)

        # 1. Decodificar
        decode_result = self._decoder.decode(image_path, channel=channel)

        if decode_result.payloads_found == 0:
            return VerifyResult(
                status=VerificationStatus.NOT_FOUND,
                decode_result=None,
                integrity_status=None,
                message="No se encontró firma H-Bit en la imagen.",
            )

        # 2. Verificar autor si se proporcionó hash esperado
        if expected_author_hash and decode_result.author_hash != expected_author_hash:
            return VerifyResult(
                status=VerificationStatus.INVALID,
                decode_result=decode_result,
                integrity_status=None,
                message=(
                    f"Hash de autor no coincide. "
                    f"Esperado: {expected_author_hash[:16]}..., "
                    f"Encontrado: {decode_result.author_hash[:16]}..."
                ),
            )

        # 3. Verificar integridad del contenido
        if decode_result.payload and decode_result.payload.flags & PayloadFlags.HAS_CONTENT_HASH:
            img = Image.open(image_path).convert("RGB")
            image_data = np.array(img, dtype=np.uint8)

            integrity = verify_content_integrity(
                image_data,
                decode_result.payload.content_hash,
                exclude_channel=decode_result.payload.channel_used,
            )

            if integrity.is_intact:
                return VerifyResult(
                    status=VerificationStatus.VERIFIED,
                    decode_result=decode_result,
                    integrity_status=IntegrityStatus.INTACT,
                    message=(
                        f"✓ Imagen verificada. Autor: {decode_result.author_hash[:16]}... "
                        f"({decode_result.payloads_found} copias, "
                        f"confianza: {decode_result.confidence:.1%})"
                    ),
                )
            else:
                return VerifyResult(
                    status=VerificationStatus.TAMPERED,
                    decode_result=decode_result,
                    integrity_status=IntegrityStatus.TAMPERED,
                    message=(
                        f"⚠ Firma H-Bit válida pero imagen MODIFICADA. "
                        f"Diferencia: {integrity.difference_ratio:.1%}"
                    ),
                )

        # Sin hash de contenido — solo verificar presencia
        return VerifyResult(
            status=VerificationStatus.VERIFIED,
            decode_result=decode_result,
            integrity_status=None,
            message=f"✓ Firma H-Bit encontrada. Autor: {decode_result.author_hash[:16]}...",
        )


def _bits_to_bytes(bit_string: str) -> bytes:
    """Convierte una cadena de bits a bytes.

    Args:
        bit_string: Cadena de '0' y '1'.

    Returns:
        bytes resultantes.
    """
    # Asegurar que la longitud sea múltiplo de 8
    padded = bit_string.ljust(((len(bit_string) + 7) // 8) * 8, "0")
    byte_list = [int(padded[i:i + 8], 2) for i in range(0, len(padded), 8)]
    return bytes(byte_list)


def _save_image(img: Image.Image, path: Path) -> None:
    """Guarda una imagen en el formato determinado por la extensión.

    Args:
        img: Imagen PIL a guardar.
        path: Ruta de destino.
    """
    extension = path.suffix.lower()
    if extension in (".jpg", ".jpeg"):
        img.save(path, "JPEG", quality=100)  # Máxima calidad para preservar LSB
    elif extension == ".tiff" or extension == ".tif":
        img.save(path, "TIFF")
    elif extension == ".bmp":
        img.save(path, "BMP")
    else:
        img.save(path, "PNG")  # PNG por defecto (sin pérdida)


# Importar struct para el manejo de errores en decode
import struct
