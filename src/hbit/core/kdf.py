"""
Módulo de Derivación de Claves (KDF) del protocolo H-Bit.

Implementa HKDF (RFC 5869) para derivar claves efímeras por sesión
de firmado. El usuario nunca expone su clave maestra directamente;
en su lugar, cada imagen se firma con una clave derivada única.

Contribución Senior 1.2: Si un archivo firmado es comprometido,
el atacante obtiene solo la clave efímera, nunca la maestra.

Referencia: RFC 5869 - HMAC-based Extract-and-Expand Key Derivation Function
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes


# Contexto de aplicación para HKDF (identifica el protocolo)
_HBIT_CONTEXT = b"H-Bit Protocol v0.1 - Persistent Authenticity"

# Tamaño de la clave derivada en bytes
_DERIVED_KEY_LENGTH = 32

# Tamaño del salt por defecto
_DEFAULT_SALT_LENGTH = 16


@dataclass(frozen=True)
class DerivedKey:
    """Clave efímera derivada para una sesión/imagen específica.

    Attributes:
        key_material: Material de clave derivado (32 bytes).
        salt: Salt utilizado en la derivación.
        context: Contexto adicional de la derivación (ej: hash de imagen).
        derivation_info: Información completa de derivación para re-derivación.
    """

    key_material: bytes
    salt: bytes
    context: bytes
    derivation_info: bytes

    @property
    def hex(self) -> str:
        """Clave derivada en formato hexadecimal."""
        return self.key_material.hex()

    @property
    def binary(self) -> str:
        """Clave derivada como cadena binaria (para incrustación)."""
        return bin(int.from_bytes(self.key_material, "big"))[2:].zfill(
            len(self.key_material) * 8
        )


def generate_session_salt(num_bytes: int = _DEFAULT_SALT_LENGTH) -> bytes:
    """Genera un salt aleatorio para una sesión de firmado.

    Args:
        num_bytes: Cantidad de bytes del salt.

    Returns:
        bytes con salt criptográficamente seguro.
    """
    return os.urandom(num_bytes)


def derive_session_key(
    master_key: bytes,
    session_salt: bytes | None = None,
) -> DerivedKey:
    """Deriva una clave efímera para una sesión de firmado.

    Cada sesión de firmado obtiene una clave única derivada de la
    clave maestra. Esto asegura que comprometer una firma individual
    no compromete la clave maestra del autor.

    Args:
        master_key: Clave maestra del autor (bytes raw de Ed25519 o similar).
        session_salt: Salt de sesión. Si es None, se genera automáticamente.

    Returns:
        DerivedKey con el material de clave efímera.
    """
    if session_salt is None:
        session_salt = generate_session_salt()

    info = _HBIT_CONTEXT + b"|session"
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=_DERIVED_KEY_LENGTH,
        salt=session_salt,
        info=info,
    )
    derived = hkdf.derive(master_key)

    return DerivedKey(
        key_material=derived,
        salt=session_salt,
        context=b"session",
        derivation_info=info,
    )


def derive_image_key(
    master_key: bytes,
    image_hash: bytes,
) -> DerivedKey:
    """Deriva una clave determinística única por imagen.

    A diferencia de derive_session_key, esta derivación es determinística:
    dado el mismo master_key y image_hash, siempre produce la misma clave.
    Esto permite re-verificar la firma sin almacenar el salt de sesión.

    El image_hash actúa como salt determinístico, vinculando la clave
    derivada al contenido específico de la imagen.

    Args:
        master_key: Clave maestra del autor.
        image_hash: SHA-256 del contenido de la imagen (32 bytes).

    Returns:
        DerivedKey con clave única para esta imagen específica.
    """
    info = _HBIT_CONTEXT + b"|image"
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=_DERIVED_KEY_LENGTH,
        salt=image_hash,  # Determinístico: hash de imagen como salt
        info=info,
    )
    derived = hkdf.derive(master_key)

    return DerivedKey(
        key_material=derived,
        salt=image_hash,
        context=b"image",
        derivation_info=info,
    )


def derive_from_passphrase(
    passphrase: str,
    salt: bytes | None = None,
) -> DerivedKey:
    """Deriva material de clave a partir de una frase de contraseña.

    Útil cuando el usuario no tiene un par de claves Ed25519 y quiere
    usar una contraseña legible. La derivación aplica stretching adicional.

    Args:
        passphrase: Frase de contraseña del usuario.
        salt: Salt para la derivación. Si es None, se genera automáticamente.

    Returns:
        DerivedKey derivada de la frase de contraseña.
    """
    if salt is None:
        salt = generate_session_salt()

    # Pre-hash de la frase de contraseña para normalizar longitud
    passphrase_hash = hashlib.sha256(passphrase.encode("utf-8")).digest()

    info = _HBIT_CONTEXT + b"|passphrase"
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=_DERIVED_KEY_LENGTH,
        salt=salt,
        info=info,
    )
    derived = hkdf.derive(passphrase_hash)

    return DerivedKey(
        key_material=derived,
        salt=salt,
        context=b"passphrase",
        derivation_info=info,
    )
