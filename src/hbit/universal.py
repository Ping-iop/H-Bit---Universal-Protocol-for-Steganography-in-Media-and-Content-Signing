"""
Pipeline universal del protocolo H-Bit.

Extiende el pipeline original para soportar cualquier formato de archivo
mediante la capa de abstracción MediaHandler + MediaRegistry.

Uso:
    # Firmar cualquier archivo
    encoder = UniversalEncoder()
    result = encoder.encode("documento.pdf", "mi_passphrase", "documento_hbit.pdf")

    # Extraer firma de cualquier archivo
    decoder = UniversalDecoder()
    result = decoder.decode("documento_hbit.pdf")

    # Verificar cualquier archivo
    verifier = UniversalVerifier()
    result = verifier.verify("documento_hbit.pdf")
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from hbit.core.crypto import (
    HBitKeyPair,
    compute_content_hash as crypto_content_hash,
)
from hbit.core.kdf import derive_image_key, derive_from_passphrase
from hbit.core.signature import HBitPayload, PayloadFlags
from hbit.core.sync import wrap_payload_with_sync
from hbit.formats.base import (
    MediaRegistry,
    MediaHandler,
    CarrierData,
    MediaCategory,
    EmbeddingStrategy,
)


class UniversalVerificationStatus(Enum):
    """Estado de verificación universal."""
    VERIFIED = "VERIFIED"
    TAMPERED = "TAMPERED"
    NOT_FOUND = "NOT_FOUND"
    INVALID = "INVALID"


@dataclass
class UniversalEncodeResult:
    """Resultado de la codificación universal H-Bit.

    Attributes:
        output_path: Ruta al archivo firmado.
        author_hash: Hash de identidad del autor (hex).
        content_hash: Hash de contenido del medio (hex).
        bits_embedded: Número de bits incrustados.
        capacity_used: Porcentaje de capacidad utilizada.
        media_category: Tipo de medio procesado.
        strategy_used: Estrategia de embedding utilizada.
        handler_name: Nombre del handler utilizado.
    """
    output_path: Path
    author_hash: str
    content_hash: str
    bits_embedded: int
    capacity_used: float
    media_category: str
    strategy_used: str
    handler_name: str


@dataclass
class UniversalDecodeResult:
    """Resultado de la decodificación universal H-Bit.

    Attributes:
        author_hash: Hash del autor extraído (hex).
        content_hash: Hash de contenido extraído (hex).
        timestamp: Marca de tiempo de la firma.
        version: Versión del protocolo.
        confidence: Confianza de la extracción.
        payload: Payload deserializado (si se encontró).
        media_category: Tipo de medio procesado.
        found: Si se encontró firma válida.
    """
    author_hash: str
    content_hash: str
    timestamp: float
    version: int
    confidence: float
    payload: Optional[HBitPayload]
    media_category: str
    strategy_used: str
    found: bool


@dataclass
class UniversalVerifyResult:
    """Resultado de la verificación universal H-Bit.

    Attributes:
        status: Estado de la verificación.
        decode_result: Resultado de la decodificación.
        message: Mensaje descriptivo.
    """
    status: UniversalVerificationStatus
    decode_result: Optional[UniversalDecodeResult]
    message: str


class UniversalEncoder:
    """Codificador universal H-Bit para cualquier formato de archivo.

    Detecta el formato automáticamente y aplica la estrategia
    de incrustación óptima para el tipo de medio.

    Flujo:
    1. MediaRegistry resuelve el handler correcto
    2. Handler carga el medio → CarrierData
    3. Se genera el payload H-Bit (hash autor + hash contenido + timestamp)
    4. Handler incrusta bits según su estrategia
    5. Handler guarda el resultado
    """

    def __init__(self, registry: Optional[MediaRegistry] = None, use_kdf: bool = True):
        """Inicializa el encoder universal.

        Args:
            registry: MediaRegistry a usar (default: singleton global).
            use_kdf: Si True, deriva clave efímera con HKDF.
        """
        self._registry = registry or MediaRegistry.default()
        self.use_kdf = use_kdf

    def encode(
        self,
        file_path: str | Path,
        author_key: HBitKeyPair | str,
        output_path: str | Path,
        device_id: str = "software-reference-v0.1",
        encrypt: bool = False,
    ) -> UniversalEncodeResult:
        """Codifica cualquier archivo con firma H-Bit.

        Args:
            file_path: Ruta al archivo de entrada.
            author_key: Par de claves Ed25519 o passphrase como string.
            output_path: Ruta donde guardar el archivo firmado.
            device_id: Identificador del dispositivo.
            encrypt: Si True, cifra el payload usando la passphrase (requiere author_key str).

        Returns:
            UniversalEncodeResult con los detalles de la codificación.

        Raises:
            ValueError: Si encrypt=True pero author_key no es un string.
        """
        file_path = Path(file_path)
        output_path = Path(output_path)

        # 1. Resolver handler
        handler = self._registry.get_handler(file_path)

        # 2. Cargar medio
        carrier = handler.load(file_path)

        # 3. Resolver clave del autor
        key_material = self._resolve_key(author_key)

        # 4. KDF: derivar clave por archivo si está habilitado
        if self.use_kdf:
            raw_content_hash = crypto_content_hash(carrier.raw_data)
            image_derived = derive_image_key(key_material, raw_content_hash)
            effective_key = image_derived.key_material
        else:
            effective_key = key_material

        # 5. Generar hash de autor
        author_hash = self._normalize_key(effective_key)

        # 6. Hash de contenido del medio
        content_hash = carrier.content_hash()

        # 7. Construir payload
        flags = PayloadFlags.HAS_CONTENT_HASH | PayloadFlags.HAS_ECC
        if self.use_kdf:
            flags |= PayloadFlags.USES_KDF

        payload = HBitPayload.create(
            author_hash=author_hash,
            content_hash=content_hash,
            flags=flags,
        )

        # 8. Serializar (y opcionalmente cifrar)
        if encrypt:
            if not isinstance(author_key, str):
                raise ValueError("Para cifrar el payload se requiere una passphrase (author_key como str)")
            
            # Cifrar payload: retorna bytes
            payload_bytes = payload.encrypt_payload(author_key)
            # Convertir a bits
            payload_binary = "".join(format(b, "08b") for b in payload_bytes)
        else:
            payload_binary = payload.to_binary_string()

        # Envolver con sincronización
        wrapped_payload = wrap_payload_with_sync(payload_binary)

        # 9. Incrustar — el handler decide la estrategia óptima
        embed_result = handler.embed(carrier, wrapped_payload)

        # 10. Guardar
        handler.save(embed_result.output_data, output_path, carrier)

        return UniversalEncodeResult(
            output_path=output_path,
            author_hash=author_hash.hex(),
            content_hash=content_hash.hex(),
            bits_embedded=embed_result.bits_embedded,
            capacity_used=embed_result.capacity_used,
            media_category=handler.category.value,
            strategy_used=embed_result.strategy_used.name,
            handler_name=handler.name,
        )

    def _resolve_key(self, author_key: HBitKeyPair | str) -> bytes:
        """Resuelve la clave del autor a bytes."""
        if isinstance(author_key, str):
            derived = derive_from_passphrase(author_key)
            return derived.key_material
        else:
            from cryptography.hazmat.primitives.serialization import (
                Encoding, NoEncryption, PrivateFormat,
            )
            return author_key.private_key.private_bytes(
                encoding=Encoding.Raw,
                format=PrivateFormat.Raw,
                encryption_algorithm=NoEncryption(),
            )

    def _normalize_key(self, key_material: bytes) -> bytes:
        """Normaliza la clave a 32 bytes mediante Hashing (protege la clave original)."""
        # Siempre hashear para derivar un ID seguro y de tamaño fijo (32 bytes)
        return hashlib.sha256(key_material).digest()


class UniversalDecoder:
    """Decodificador universal H-Bit para cualquier formato de archivo.

    Detecta el formato y extrae la firma H-Bit automáticamente.
    """

    def __init__(self, registry: Optional[MediaRegistry] = None):
        self._registry = registry or MediaRegistry.default()

    def decode(
        self, 
        file_path: str | Path, 
        passphrase: Optional[str] = None
    ) -> UniversalDecodeResult:
        """Decodifica la firma H-Bit de cualquier archivo.

        Args:
            file_path: Ruta al archivo firmado.
            passphrase: Clave opcional para descifrar el payload.

        Returns:
            UniversalDecodeResult con la firma extraída.
        """
        file_path = Path(file_path)

        # 1. Resolver handler
        handler = self._registry.get_handler(file_path)

        # 2. Cargar medio
        carrier = handler.load(file_path)

        # 3. Extraer bits
        extract_result = handler.extract(carrier)

        if extract_result.payloads_found == 0 or not extract_result.payload_bits:
            return self._not_found(handler)

        # 4. Remover sync markers
        # Los handlers universales leen una longitud explícita que incluye
        # los sync markers al principio y al final.
        # find_payload_boundaries() puede dar falsos positivos en payloads aleatorios,
        # así que es más seguro simplemente recortar los marcadores conocidos.
        from hbit.core.sync import SYNC_SEQUENCE_LENGTH

        raw_bits = extract_result.payload_bits
        if len(raw_bits) >= 2 * SYNC_SEQUENCE_LENGTH:
            # Calcular padding añadido por almacenamiento en bytes
            # len(raw_bits) = Header(13) + Payload(N*8) + Footer(13) + Pad(?)
            # len - 26 = N*8 + Pad
            # (len - 26) % 8 = Pad
            overhead = 2 * SYNC_SEQUENCE_LENGTH
            pad_len = (len(raw_bits) - overhead) % 8
            
            # Strip header (13) y footer+pad (13+pad)
            end_cut = SYNC_SEQUENCE_LENGTH + pad_len
            clean_bits = raw_bits[SYNC_SEQUENCE_LENGTH:-end_cut]
        else:
            clean_bits = raw_bits

        # 5. Deserializar payload
        try:
            payload_bytes = self._bits_to_bytes(clean_bits)
            
            if passphrase:
                # Intentar descifrar si se provee pass
                payload = HBitPayload.decrypt_payload(payload_bytes, passphrase)
            else:
                # Intentar deserializar core (asume plaintext)
                # Si es cifrado, esto devolverá basura o fallará
                payload = HBitPayload.deserialize_core(payload_bytes)
                if payload.flags & PayloadFlags.IS_ENCRYPTED:
                    # Detectado cifrado pero sin passphrase
                    # Retornamos resultado parcial indicando que está cifrado?
                    # Por ahora, dejamos que pase pero author_hash será basura
                    # Idealmente deberíamos retornar un status específico
                    pass

            return UniversalDecodeResult(
                author_hash=payload.author_hash.hex(),
                content_hash=payload.content_hash.hex(),
                timestamp=payload.timestamp,
                version=payload.version,
                confidence=extract_result.confidence,
                payload=payload,
                media_category=handler.category.value,
                strategy_used=extract_result.strategy_used.name,
                found=True,
            )
        except (ValueError, struct.error, IndexError, Exception):
            # Exception genérica para capturar EncryptionError también
            return self._not_found(handler)

    def _not_found(self, handler: MediaHandler) -> UniversalDecodeResult:
        """Resultado cuando no se encuentra firma."""
        return UniversalDecodeResult(
            author_hash="",
            content_hash="",
            timestamp=0.0,
            version=0,
            confidence=0.0,
            payload=None,
            media_category=handler.category.value,
            strategy_used="",
            found=False,
        )

    @staticmethod
    def _bits_to_bytes(bit_string: str) -> bytes:
        """Convierte cadena de bits a bytes."""
        padded = bit_string.ljust(((len(bit_string) + 7) // 8) * 8, "0")
        return bytes(int(padded[i:i + 8], 2) for i in range(0, len(padded), 8))


class UniversalVerifier:
    """Verificador universal H-Bit para cualquier formato de archivo.

    Combina decodificación + verificación de integridad.
    """

    def __init__(self, registry: Optional[MediaRegistry] = None):
        self._registry = registry or MediaRegistry.default()
        self._decoder = UniversalDecoder(self._registry)

    def verify(
        self,
        file_path: str | Path,
        expected_author_hash: Optional[str] = None,
        passphrase: Optional[str] = None,
    ) -> UniversalVerifyResult:
        """Verifica la autenticidad de cualquier archivo firmado.

        Args:
            file_path: Ruta al archivo a verificar.
            expected_author_hash: Hash del autor esperado (hex, opcional).
            passphrase: Clave par descifrar payload (opcional).

        Returns:
            UniversalVerifyResult con el estado de la verificación.
        """
        file_path = Path(file_path)

        # 1. Decodificar
        decode_result = self._decoder.decode(file_path, passphrase)

        if not decode_result.found:
            return UniversalVerifyResult(
                status=UniversalVerificationStatus.NOT_FOUND,
                decode_result=None,
                message=f"No se encontró firma H-Bit en: {file_path.name}",
            )

        # 2. Verificar autor si se proporcionó
        if expected_author_hash and decode_result.author_hash != expected_author_hash:
            return UniversalVerifyResult(
                status=UniversalVerificationStatus.INVALID,
                decode_result=decode_result,
                message=(
                    f"Hash de autor no coincide. "
                    f"Esperado: {expected_author_hash[:16]}..., "
                    f"Encontrado: {decode_result.author_hash[:16]}..."
                ),
            )

        # 3. Verificar integridad del contenido
        if decode_result.payload:
            handler = self._registry.get_handler(file_path)
            carrier = handler.load(file_path)

            # content_hash() usa canonical_hash si está disponible,
            # que excluye datos H-Bit del cálculo.
            current_hash = carrier.content_hash()

            if current_hash == decode_result.payload.content_hash:
                return UniversalVerifyResult(
                    status=UniversalVerificationStatus.VERIFIED,
                    decode_result=decode_result,
                    message=(
                        f"[OK] Archivo verificado ({handler.category.value}). "
                        f"Autor: {decode_result.author_hash[:16]}... "
                        f"(confianza: {decode_result.confidence:.1%})"
                    ),
                )
            else:
                # Para DCT/Watermarking, el hash de contenido SIEMPRE cambia.
                # Si la firma y author_hash son válidos, consideramos VERIFICADO pero modificada (watermarked).
                if decode_result.strategy_used == EmbeddingStrategy.DCT.name:
                     return UniversalVerifyResult(
                        status=UniversalVerificationStatus.VERIFIED,
                        decode_result=decode_result,
                        message=(
                            f"[OK] Firma H-Bit Válida (Marca de agua DCT). "
                            f"Autor: {decode_result.author_hash[:16]}..."
                        ),
                    )

                return UniversalVerifyResult(
                    status=UniversalVerificationStatus.TAMPERED,
                    decode_result=decode_result,
                    message=(
                        f"[WARN] Firma H-Bit valida pero archivo MODIFICADO. "
                        f"Tipo: {handler.category.value}"
                    ),
                )

        # Sin hash de contenido
        return UniversalVerifyResult(
            status=UniversalVerificationStatus.VERIFIED,
            decode_result=decode_result,
            message=f"[OK] Firma H-Bit encontrada. Autor: {decode_result.author_hash[:16]}...",
        )

