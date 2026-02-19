"""
Módulo de cifrado del protocolo H-Bit (Fase 6).

Implementa cifrado autenticado AES-256-GCM para proteger la privacidad
del payload. Utiliza PBKDF2-HMAC-SHA256 para derivación robusta de claves
a partir de una passphrase.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class EncryptionError(Exception):
    """Error base para fallos de cifrado/descifrado."""
    pass


@dataclass
class EncryptedPayload:
    """Contenedor de datos cifrados.
    
    Attributes:
        salt: Sal aleatoria usada para derivación de clave (16 bytes).
        nonce: Número usado una vez para AES-GCM (12 bytes).
        ciphertext: Datos cifrados.
        tag: Etiqueta de autenticación GCM (16 bytes, usualmente appendada al ciphertext).
    """
    salt: bytes
    nonce: bytes
    ciphertext: bytes
    tag: bytes  # Nota: AESGCM.encrypt devuelve ciphertext + tag concatenados


class HBitEncryptor:
    """Encriptador AES-256-GCM para el protocolo H-Bit."""

    SALT_SIZE = 16
    NONCE_SIZE = 12
    KEY_SIZE = 32  # AES-256
    ITERATIONS = 100_000  # OWASP recommendation for PBKDF2

    def encrypt(self, data: bytes, passphrase: str) -> EncryptedPayload:
        """Cifra datos usando AES-256-GCM con una clave derivada de la passphrase.

        Args:
            data: Datos a cifrar (bytes).
            passphrase: Contraseña segura.

        Returns:
            EncryptedPayload con los componentes necesarios para descifrar.
        """
        if not passphrase:
             # Permitir passphrase vacía si se desea, o lanzar error. 
             # Por consistencia con tests, permitimos.
             pass

        # 1. Generar salt y nonce aleatorios
        salt = os.urandom(self.SALT_SIZE)
        nonce = os.urandom(self.NONCE_SIZE)

        # 2. Derivar clave AES-256
        key = self._derive_key(passphrase, salt)

        # 3. Cifrar (AESGCM añade el tag al final del ciphertext automáticamente)
        aesgcm = AESGCM(key)
        ciphertext_with_tag = aesgcm.encrypt(nonce, data, associated_data=None)

        # Separar tag (últimos 16 bytes por defecto en cryptography)
        # Nota: cryptography devuelve todo junto. Para H-Bit struct, 
        # conceptualmente los separamos, pero almacenaremos como bytes.
        
        return EncryptedPayload(
            salt=salt,
            nonce=nonce,
            ciphertext=ciphertext_with_tag[:-16],
            tag=ciphertext_with_tag[-16:]
        )

    def decrypt(self, encrypted: EncryptedPayload, passphrase: str) -> bytes:
        """Descifra datos validados con AES-256-GCM.

        Args:
            encrypted: Objeto EncryptedPayload.
            passphrase: Contraseña usada en el cifrado.

        Returns:
            Datos originales descifrados.

        Raises:
            EncryptionError: Si la contraseña es incorrecta o los datos fueron manipulados.
        """
        # 1. Derivar clave con el mismo salt
        key = self._derive_key(passphrase, encrypted.salt)

        # 2. Reconstruir ciphertext + tag para cryptography
        ciphertext_with_tag = encrypted.ciphertext + encrypted.tag

        # 3. Descifrar y autenticar
        aesgcm = AESGCM(key)
        try:
            return aesgcm.decrypt(encrypted.nonce, ciphertext_with_tag, associated_data=None)
        except Exception as e:
            raise EncryptionError("Decryption failed: Invalid passphrase or tampered data") from e

    def _derive_key(self, passphrase: str, salt: bytes) -> bytes:
        """Deriva una clave de 256 bits usando PBKDF2-HMAC-SHA256."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=self.KEY_SIZE,
            salt=salt,
            iterations=self.ITERATIONS,
        )
        return kdf.derive(passphrase.encode("utf-8"))
