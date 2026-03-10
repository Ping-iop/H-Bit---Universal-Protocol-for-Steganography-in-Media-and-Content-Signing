"""
Estructura del payload H-Bit (firma serializada).

Define la estructura binaria del payload que se incrusta en la imagen:
[SYNC_HEADER][VERSION][FLAGS][AUTHOR_HASH][CONTENT_HASH][TIMESTAMP][SIGNATURE][ECC_PARITY][SYNC_FOOTER]

Cada campo tiene longitud fija para facilitar la sincronización
y la extracción incluso desde fragmentos dañados.
"""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass
from enum import IntEnum, IntFlag
from typing import Optional


# Versión del protocolo H-Bit
PROTOCOL_VERSION = 1

# Longitudes fijas en bytes
AUTHOR_HASH_LENGTH = 32    # SHA-256
CONTENT_HASH_LENGTH = 32   # SHA-256
TIMESTAMP_LENGTH = 8       # double (64-bit float)
SIGNATURE_LENGTH = 64      # Ed25519
VERSION_LENGTH = 1         # uint8
FLAGS_LENGTH = 1           # uint8


class EncodingMethod(IntEnum):
    """Método de codificación utilizado para incrustar el payload."""

    LSB = 0          # Solo LSB (Fase 1)
    DCT = 1          # Solo DCT (Fase 2)
    HYBRID = 2       # LSB + DCT combinado (Fase 2)


class PayloadFlags(IntFlag):
    """Flags indicando características del payload."""

    NONE = 0
    HAS_CONTENT_HASH = 1 << 0     # Incluye hash de integridad del contenido
    HAS_SIGNATURE = 1 << 1        # Incluye firma digital Ed25519
    HAS_ECC = 1 << 2              # Incluye paridad Reed-Solomon
    HAS_C2PA_REF = 1 << 3         # Incluye referencia a manifiesto C2PA
    HAS_PRNU_BINDING = 1 << 4     # Incluye vínculo PRNU del sensor
    USES_KDF = 1 << 5             # Clave derivada con KDF (no maestra)
    IS_ENCRYPTED = 1 << 6         # El payload está cifrado
    IS_COMPRESSED = 1 << 7        # El payload está comprimido (zlib)

    @classmethod
    def default(cls) -> PayloadFlags:
        """Flags por defecto: hash de contenido + ECC."""
        return cls.HAS_CONTENT_HASH | cls.HAS_ECC | cls.USES_KDF


@dataclass
class HBitPayload:
    """Payload completo del protocolo H-Bit.

    Contiene toda la información que se incrusta en la imagen.

    Attributes:
        version: Versión del protocolo (para compatibilidad futura).
        flags: Flags indicando qué campos están presentes.
        author_hash: Hash SHA-256 de la identidad del autor (32 bytes).
        content_hash: Hash SHA-256 del contenido de la imagen (32 bytes, opcional).
        timestamp: Marca de tiempo Unix de la creación.
        signature: Firma digital Ed25519 del payload (64 bytes, opcional).
        ecc_parity: Bytes de paridad Reed-Solomon (longitud variable, opcional).
        c2pa_reference: URI de manifiesto C2PA (bytes, opcional).
        channel_used: Canal de color utilizado para la incrustación.
        encoding_method: Método de codificación utilizado.
    """

    version: int
    flags: PayloadFlags
    author_hash: bytes
    content_hash: bytes
    timestamp: float
    signature: bytes = b""
    ecc_parity: bytes = b""
    c2pa_reference: bytes = b""
    channel_used: int = 2  # Canal azul por defecto
    encoding_method: EncodingMethod = EncodingMethod.LSB

    @classmethod
    def create(
        cls,
        author_hash: bytes,
        content_hash: bytes | None = None,
        timestamp: float | None = None,
        flags: PayloadFlags | None = None,
    ) -> HBitPayload:
        """Crea un nuevo payload H-Bit.

        Args:
            author_hash: Hash del autor (32 bytes, obligatorio).
            content_hash: Hash del contenido (32 bytes, opcional).
            timestamp: Marca de tiempo. Si es None, se usa la hora actual.
            flags: Flags del payload. Si es None, se usan los defaults.

        Returns:
            HBitPayload configurado.

        Raises:
            ValueError: Si el author_hash no tiene la longitud correcta.
        """
        if len(author_hash) != AUTHOR_HASH_LENGTH:
            raise ValueError(
                f"author_hash debe tener {AUTHOR_HASH_LENGTH} bytes, "
                f"recibido: {len(author_hash)}"
            )

        if content_hash is None:
            content_hash = b"\x00" * CONTENT_HASH_LENGTH

        if len(content_hash) != CONTENT_HASH_LENGTH:
            raise ValueError(
                f"content_hash debe tener {CONTENT_HASH_LENGTH} bytes, "
                f"recibido: {len(content_hash)}"
            )

        if timestamp is None:
            timestamp = time.time()

        if flags is None:
            flags = PayloadFlags.default()

        return cls(
            version=PROTOCOL_VERSION,
            flags=flags,
            author_hash=author_hash,
            content_hash=content_hash,
            timestamp=timestamp,
        )

    def encrypt_payload(self, passphrase: str) -> bytes:
        """Serializa y cifra el payload completo.

        Args:
            passphrase: Clave para cifrar.

        Returns:
            bytes con el payload cifrado listo para incrustar.
            Estructura: [VERSION][FLAGS|ENCRYPTED][SALT][NONCE][TAG][CIPHERTEXT]
        """
        from hbit.core.encryption import HBitEncryptor

        # 1. Serializar el payload original (plaintext)
        # Nota: serialize() ya aplicará compresión si es eficiente.
        plaintext = self.serialize()

        # 2. Cifrar
        encryptor = HBitEncryptor()
        encrypted = encryptor.encrypt(plaintext, passphrase)

        # 3. Construir paquete cifrado
        # Flags con bit ENCRYPTED activado (preservando compression flag si existe)
        # Pero ojo: el outer header tiene flags. El inner payload (plaintext) tiene su header con flags.
        # El outer header DEBE reflejar features del transporte.
        # Si el plaintext está comprimido, ¿importa afuera? No necesariamente.
        # Pero es bueno propagar flags críticos.
        # Sin embargo, serialize() retorna BYTES. El outer header se construye AQUÍ.
        # Usamos self.flags que tiene el estado "lógico".
        # PERO si serialize() comprimió, el bytes resultante tiene estructura [V][F|COMP][ZLIB].
        # El outer header [V][F|ENC][SALT]... contiene el CIPHERTEXT.
        # Al descifrar, tenemos [V][F|COMP][ZLIB].
        # deserialize() funciona bien.
        
        flags_byte = int(self.flags | PayloadFlags.IS_ENCRYPTED)
        
        # Estructura:
        # Version (1) + Flags (1) + Salt (16) + Nonce (12) + Tag (16) + Ciphertext (N)
        return (
            struct.pack("!BB", self.version, flags_byte)
            + encrypted.salt
            + encrypted.nonce
            + encrypted.tag
            + encrypted.ciphertext
        )

    @classmethod
    def decrypt_payload(cls, data: bytes, passphrase: str) -> HBitPayload:
        """Descifra y deserializa un payload cifrado.

        Args:
            data: Bytes cifrados (extraídos del medio).
            passphrase: Clave para descifrar.

        Returns:
            HBitPayload descifrado.
        """
        from hbit.core.encryption import HBitEncryptor, EncryptedPayload

        # Leer header mínimo (Version + Flags)
        if len(data) < 2:
            raise ValueError("Datos insuficientes para payload")

        version, flags_raw = struct.unpack_from("!BB", data, 0)
        flags = PayloadFlags(flags_raw)

        if not (flags & PayloadFlags.IS_ENCRYPTED):
            # No está cifrado, intentar deserializar normal
            return cls.deserialize_core(data)

        # Para payloads cifrados necesitamos: Version+Flags+Salt+Nonce+Tag
        if len(data) < 2 + 16 + 12 + 16:
            raise ValueError("Datos insuficientes para payload cifrado")

        # Extraer metadata crypto
        offset = 2
        salt = data[offset : offset + 16]
        offset += 16
        nonce = data[offset : offset + 12]
        offset += 12
        tag = data[offset : offset + 16]
        offset += 16
        ciphertext = data[offset:]

        # Descifrar
        encrypted = EncryptedPayload(salt, nonce, ciphertext, tag)
        encryptor = HBitEncryptor()
        plaintext = encryptor.decrypt(encrypted, passphrase)

        # Deserializar el plaintext
        return cls.deserialize(plaintext)

    def serialize_core(self) -> bytes:
        """Serializa los campos core del payload (sin ECC ni firma).

        El formato binario es:
        - 1 byte:  versión del protocolo
        - 1 byte:  flags
        - 32 bytes: author_hash
        - 32 bytes: content_hash
        - 8 bytes:  timestamp (double)
        = 74 bytes total de core

        Returns:
            bytes con el payload core serializado.
        """
        return struct.pack(
            f"!BB{AUTHOR_HASH_LENGTH}s{CONTENT_HASH_LENGTH}sd",
            self.version,
            int(self.flags),
            self.author_hash,
            self.content_hash,
            self.timestamp,
        )

    def serialize(self) -> bytes:
        """Serializa el payload completo incluyendo firma y ECC.
        
        Aplica compresión zlib automáticamente si reduce el tamaño.

        Returns:
            bytes con el payload completo (posiblemente comprimido).
        """
        import zlib
        
        core = self.serialize_core()
        raw_payload = core

        if self.flags & PayloadFlags.HAS_SIGNATURE and self.signature:
            raw_payload += self.signature

        if self.flags & PayloadFlags.HAS_ECC and self.ecc_parity:
            # Prefijo con longitud del ECC (2 bytes)
            raw_payload += struct.pack("!H", len(self.ecc_parity))
            raw_payload += self.ecc_parity

        if self.flags & PayloadFlags.HAS_C2PA_REF and self.c2pa_reference:
            # Prefijo con longitud de la referencia C2PA (2 bytes)
            raw_payload += struct.pack("!H", len(self.c2pa_reference))
            raw_payload += self.c2pa_reference

        # Intentar compresión
        # Excluir los dos primeros bytes (Version + Flags) para recomponer header
        # Header [V][F]
        # Body [Hash...Sig...Ecc]
        # Comprimir Body
        header = raw_payload[:2]
        body = raw_payload[2:]
        
        compressed_body = zlib.compress(body, level=9)
        
        if len(compressed_body) < len(body):
            # Compresión efectiva: usar comprimido
            # Actualizar flag en el header DE ESTE paquete serializado
            version = self.version
            flags = self.flags | PayloadFlags.IS_COMPRESSED
            new_header = struct.pack("!BB", version, int(flags))
            return new_header + compressed_body
        else:
            # Compresión no efectiva: retornar raw
            return raw_payload

    def to_binary_string(self) -> str:
        """Convierte el payload serializado a cadena binaria para incrustación.

        Returns:
            str con la representación binaria (solo '0' y '1').
        """
        serialized = self.serialize()
        return "".join(format(byte, "08b") for byte in serialized)

    @classmethod
    def deserialize(cls, data: bytes) -> HBitPayload:
        """Deserializa el payload completo.

        Maneja automáticamente la descompresión zlib si es necesario.

        Args:
            data: bytes con el payload (posiblemente comprimido).

        Returns:
            HBitPayload con todos los campos restaurados según los flags.

        Raises:
            ValueError: Si los datos son insuficientes o corruptos.
        """
        if len(data) < 2:
            raise ValueError("Datos insuficientes (header)")

        version, flags_raw = struct.unpack_from("!BB", data, 0)

        if version != PROTOCOL_VERSION:
            raise ValueError(f"Versión de protocolo no soportada: {version}")

        flags = PayloadFlags(flags_raw)

        if flags & PayloadFlags.IS_COMPRESSED:
            import zlib
            try:
                # El resto es stream zlib
                decompressed_body = zlib.decompress(data[2:])
                # Restaurar flags originales (quitar IS_COMPRESSED)
                orig_flags = flags & ~PayloadFlags.IS_COMPRESSED
                clean_header = struct.pack("!BB", version, int(orig_flags))

                decompressed_data = clean_header + decompressed_body
                return cls.deserialize(decompressed_data)
            except Exception as e:
                raise ValueError(f"Fallo al descomprimir payload: {e}")

        # Lógica estándar para payload no comprimido
        core_size = (
            VERSION_LENGTH
            + FLAGS_LENGTH
            + AUTHOR_HASH_LENGTH
            + CONTENT_HASH_LENGTH
            + TIMESTAMP_LENGTH
        )
        if len(data) < core_size:
            raise ValueError(
                f"Datos insuficientes: se necesitan {core_size} bytes para el core, "
                f"recibido: {len(data)}"
            )

        offset = 2

        author_hash = data[offset : offset + AUTHOR_HASH_LENGTH]
        offset += AUTHOR_HASH_LENGTH

        content_hash = data[offset : offset + CONTENT_HASH_LENGTH]
        offset += CONTENT_HASH_LENGTH

        (timestamp,) = struct.unpack_from("!d", data, offset)
        offset += TIMESTAMP_LENGTH

        # Campos opcionales
        signature = b""
        if flags & PayloadFlags.HAS_SIGNATURE:
            if len(data) < offset + SIGNATURE_LENGTH:
                raise ValueError("Datos insuficientes para la firma")
            signature = data[offset : offset + SIGNATURE_LENGTH]
            offset += SIGNATURE_LENGTH

        ecc_parity = b""
        if flags & PayloadFlags.HAS_ECC:
            if len(data) < offset + 2:
                raise ValueError("Datos insuficientes para longitud de ECC")
            (ecc_len,) = struct.unpack_from("!H", data, offset)
            offset += 2
            if len(data) < offset + ecc_len:
                raise ValueError("Datos insuficientes para ECC parity")
            ecc_parity = data[offset : offset + ecc_len]
            offset += ecc_len

        c2pa_reference = b""
        if flags & PayloadFlags.HAS_C2PA_REF:
            if len(data) < offset + 2:
                raise ValueError("Datos insuficientes para longitud de C2PA ref")
            (c2pa_len,) = struct.unpack_from("!H", data, offset)
            offset += 2
            if len(data) < offset + c2pa_len:
                raise ValueError("Datos insuficientes para C2PA ref")
            c2pa_reference = data[offset : offset + c2pa_len]
            offset += c2pa_len

        return cls(
            version=version,
            flags=flags,
            author_hash=author_hash,
            content_hash=content_hash,
            timestamp=timestamp,
            signature=signature,
            ecc_parity=ecc_parity,
            c2pa_reference=c2pa_reference,
        )

    @classmethod
    def deserialize_core(cls, data: bytes) -> HBitPayload:
        """Deserializa el payload (alias de deserialize para compatibilidad).

        Maneja automáticamente la descompresión zlib si es necesario.

        Args:
            data: bytes con el payload (posiblemente comprimido).

        Returns:
            HBitPayload con los campos restaurados.

        Raises:
            ValueError: Si los datos son insuficientes o corruptos.
        """
        return cls.deserialize(data)

    @property
    def core_size_bits(self) -> int:
        """Tamaño del payload core en bits."""
        return len(self.serialize_core()) * 8

    @property
    def total_size_bits(self) -> int:
        """Tamaño total del payload serializado en bits."""
        # Se asume payload NO cifrado para este cálculo.
        # Si estuviera cifrado, el tamaño variable del ciphertext complica esto.
        return len(self.serialize()) * 8
