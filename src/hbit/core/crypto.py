"""
Módulo criptográfico del protocolo H-Bit.

Implementa las operaciones criptográficas fundamentales:
- Generación de pares de claves Ed25519
- Hash de identidad de autor (SHA-256)
- Firma y verificación digital de payloads
- Generación de ruido criptográfico para sal de sesión

Referencia: Sección 2.1 de la Especificación Técnica H-Bit.
Fórmula: H = SHA256(K_priv || ID_dev || N_sensor || T_stamp)
"""

from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)


@dataclass(frozen=True)
class HBitKeyPair:
    """Par de claves Ed25519 para el protocolo H-Bit.

    Attributes:
        private_key: Clave privada Ed25519 (nunca debe exponerse directamente).
        public_key: Clave pública Ed25519 (compartida para verificación).
    """

    private_key: Ed25519PrivateKey
    public_key: Ed25519PublicKey

    def export_private_pem(self) -> bytes:
        """Exporta la clave privada en formato PEM."""
        return self.private_key.private_bytes(
            encoding=Encoding.PEM,
            format=PrivateFormat.PKCS8,
            encryption_algorithm=NoEncryption(),
        )

    def export_public_pem(self) -> bytes:
        """Exporta la clave pública en formato PEM."""
        return self.public_key.public_bytes(
            encoding=Encoding.PEM,
            format=PublicFormat.SubjectPublicKeyInfo,
        )

    @property
    def public_key_hex(self) -> str:
        """Devuelve la representación hexadecimal de la clave pública (Raw)."""
        return self.public_key.public_bytes(
            encoding=Encoding.Raw,
            format=PublicFormat.Raw,
        ).hex()

    def save_to_directory(self, directory: Path) -> None:
        """Guarda las claves como archivos PEM en el directorio especificado.

        Args:
            directory: Ruta al directorio donde guardar las claves.
        """
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "hbit_private.pem").write_bytes(self.export_private_pem())
        (directory / "hbit_public.pem").write_bytes(self.export_public_pem())

    @classmethod
    def load_from_directory(cls, directory: Path) -> HBitKeyPair:
        """Carga un par de claves desde archivos PEM en el directorio.

        Args:
            directory: Ruta al directorio con los archivos PEM.

        Returns:
            HBitKeyPair con las claves cargadas.

        Raises:
            FileNotFoundError: Si los archivos PEM no existen.
        """
        from cryptography.hazmat.primitives.serialization import load_pem_private_key

        private_pem = (directory / "hbit_private.pem").read_bytes()
        private_key = load_pem_private_key(private_pem, password=None)
        if not isinstance(private_key, Ed25519PrivateKey):
            raise TypeError("La clave privada no es Ed25519")
        return cls(private_key=private_key, public_key=private_key.public_key())


@dataclass(frozen=True)
class AuthorIdentity:
    """Identidad del autor generada según la especificación H-Bit.

    Attributes:
        author_hash: Hash SHA-256 de la identidad del autor (32 bytes).
        device_id: Identificador único del dispositivo.
        timestamp: Marca de tiempo Unix de la generación.
        sensor_noise_sample: Muestra del ruido del sensor utilizado.
    """

    author_hash: bytes
    device_id: str
    timestamp: float
    sensor_noise_sample: bytes

    @property
    def author_hash_hex(self) -> str:
        """Hash del autor en formato hexadecimal."""
        return self.author_hash.hex()

    @property
    def author_hash_binary(self) -> str:
        """Hash del autor como cadena binaria (para incrustación)."""
        return bin(int.from_bytes(self.author_hash, "big"))[2:].zfill(256)


def generate_key_pair() -> HBitKeyPair:
    """Genera un nuevo par de claves Ed25519 para el protocolo H-Bit.

    Ed25519 se elige sobre RSA porque:
    - Claves más cortas (32 bytes vs 256+ bytes) → menos bits a incrustar
    - Firma más rápida (ideal para firmado en tiempo real en cámaras)
    - Estándar moderno (RFC 8032) con amplia adopción

    Returns:
        HBitKeyPair con clave privada y pública.
    """
    private_key = Ed25519PrivateKey.generate()
    return HBitKeyPair(
        private_key=private_key,
        public_key=private_key.public_key(),
    )


def generate_sensor_noise(num_bytes: int = 32) -> bytes:
    """Genera ruido aleatorio que simula el ruido del sensor.

    En una implementación a nivel hardware (ISP), este valor provendría
    del ruido térmico real del sensor CMOS. En la implementación de
    referencia software, usamos CSPRNG del sistema operativo.

    Args:
        num_bytes: Cantidad de bytes de ruido a generar.

    Returns:
        bytes con ruido criptográficamente seguro.
    """
    return os.urandom(num_bytes)


def generate_author_hash(
    private_key: Ed25519PrivateKey,
    device_id: str,
    sensor_noise: Optional[bytes] = None,
    timestamp: Optional[float] = None,
) -> AuthorIdentity:
    """Genera la identidad del autor según la fórmula H-Bit.

    Implementa: H = SHA256(K_priv || ID_dev || N_sensor || T_stamp)

    El hash resultante es único por cada combinación de autor, dispositivo,
    momento y condiciones del sensor, evitando firmas idénticas incluso
    en ráfagas de disparo rápido.

    Args:
        private_key: Clave privada Ed25519 del autor.
        device_id: Identificador único del dispositivo (ej: UUID de la cámara).
        sensor_noise: Ruido aleatorio del sensor. Si es None, se genera automáticamente.
        timestamp: Marca de tiempo Unix. Si es None, se usa la hora actual.

    Returns:
        AuthorIdentity con el hash y metadata asociada.
    """
    if sensor_noise is None:
        sensor_noise = generate_sensor_noise()
    if timestamp is None:
        timestamp = time.time()

    # Serializar la clave privada en formato raw (32 bytes para Ed25519)
    private_key_bytes = private_key.private_bytes(
        encoding=Encoding.Raw,
        format=PrivateFormat.Raw,
        encryption_algorithm=NoEncryption(),
    )

    # Concatenar componentes: K_priv || ID_dev || N_sensor || T_stamp
    hasher = hashlib.sha256()
    hasher.update(private_key_bytes)
    hasher.update(device_id.encode("utf-8"))
    hasher.update(sensor_noise)
    hasher.update(str(timestamp).encode("utf-8"))

    return AuthorIdentity(
        author_hash=hasher.digest(),
        device_id=device_id,
        timestamp=timestamp,
        sensor_noise_sample=sensor_noise[:8],  # Solo muestra, no el ruido completo
    )


def sign_payload(private_key: Ed25519PrivateKey, payload: bytes) -> bytes:
    """Firma digitalmente un payload con la clave privada del autor.

    Args:
        private_key: Clave privada Ed25519.
        payload: Datos a firmar (típicamente el payload H-Bit serializado).

    Returns:
        bytes con la firma digital Ed25519 (64 bytes).
    """
    return private_key.sign(payload)


def verify_signature(
    public_key: Ed25519PublicKey, payload: bytes, signature: bytes
) -> bool:
    """Verifica una firma digital contra la clave pública del autor.

    Args:
        public_key: Clave pública Ed25519 del autor.
        payload: Datos que fueron firmados.
        signature: Firma digital a verificar.

    Returns:
        True si la firma es válida, False si no lo es.
    """
    try:
        public_key.verify(signature, payload)
        return True
    except Exception:
        return False


def compute_content_hash(image_data: bytes) -> bytes:
    """Calcula el hash SHA-256 del contenido de la imagen.

    Este hash se usa para el doble hash de integridad (Hito 1.4):
    si se modifica un solo píxel de la imagen, el hash cambiará
    y el sistema detectará la manipulación.

    Args:
        image_data: Datos crudos de la imagen (array de píxeles serializado).

    Returns:
        Hash SHA-256 del contenido (32 bytes).
    """
    return hashlib.sha256(image_data).digest()
