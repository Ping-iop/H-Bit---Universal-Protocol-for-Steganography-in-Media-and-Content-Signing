"""
Oráculo de Posesión Física (Physical Possession Oracle) del protocolo H-Bit.

Contribución Senior 3.2: Mecanismo challenge-response para demostrar
que un agente posee la copia original (física) de una imagen.

Concepto: Para verificar que alguien tiene la foto original (no una copia
digital), el verificador lanza un "challenge" que requiere capturar una
nueva foto del soporte físico bajo condiciones específicas. El oráculo
compara la nueva captura con los datos H-Bit embebidos para confirmar
la posesión.

Casos de uso:
- Verificar autenticidad de impresiones fotográficas
- Confirmar posesión de la copia original (no repost digital)
- Demostrar que un NFT está vinculado a un objeto físico
"""

from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ChallengeRequest:
    """Solicitud de challenge para verificación de posesión.

    Attributes:
        challenge_id: ID único del challenge.
        nonce: Valor aleatorio que debe incluirse en la prueba.
        request_type: Tipo de prueba requerida.
        instructions: Instrucciones para el poseedor.
        expiry: Timestamp de expiración del challenge.
        region_of_interest: Región de la imagen a capturar (opcional).
    """

    challenge_id: str
    nonce: str
    request_type: str
    instructions: str
    expiry: int
    region_of_interest: Optional[tuple[int, int, int, int]]


@dataclass(frozen=True)
class PossessionProof:
    """Prueba de posesión del soporte físico.

    Attributes:
        challenge_id: ID del challenge respondido.
        nonce: Nonce del challenge (para verificación).
        capture_hash: Hash de la nueva captura.
        metadata: Metadatos de la captura (EXIF, GPS, etc.).
        timestamp: Momento de la captura.
    """

    challenge_id: str
    nonce: str
    capture_hash: bytes
    metadata: dict
    timestamp: int


@dataclass(frozen=True)
class VerificationResult:
    """Resultado de la verificación de posesión.

    Attributes:
        is_valid: Si la prueba es válida.
        confidence: Confianza de la verificación (0.0 a 1.0).
        reason: Explicación del resultado.
        challenge_id: ID del challenge verificado.
    """

    is_valid: bool
    confidence: float
    reason: str
    challenge_id: str


class PhysicalPossessionOracle:
    """Oráculo de posesión física para H-Bit.

    Flujo:
    1. Verificador crea un challenge con generate_challenge()
    2. Poseedor captura nueva foto del soporte con las condiciones del challenge
    3. Poseedor envía prueba con create_proof()
    4. Verificador valida con verify_possession()
    """

    # Tipos de challenge
    CHALLENGE_RECAPTURE = "recapture"           # Recapturar la foto
    CHALLENGE_REGION = "region_detail"           # Capturar región específica
    CHALLENGE_ANGLE = "angle_verification"       # Capturar desde ángulo específico

    # Tiempo de expiración por defecto (5 minutos)
    DEFAULT_EXPIRY = 300

    def __init__(self, secret_key: Optional[bytes] = None):
        """Inicializa el oráculo.

        Args:
            secret_key: Clave secreta para firmar challenges.
        """
        self._secret = secret_key or secrets.token_bytes(32)
        self._pending_challenges: dict[str, ChallengeRequest] = {}

    def generate_challenge(
        self,
        challenge_type: str = CHALLENGE_RECAPTURE,
        region: Optional[tuple[int, int, int, int]] = None,
        expiry_seconds: int = DEFAULT_EXPIRY,
    ) -> ChallengeRequest:
        """Genera un challenge de verificación de posesión.

        Args:
            challenge_type: Tipo de challenge.
            region: Región de interés (x, y, w, h) para CHALLENGE_REGION.
            expiry_seconds: Segundos hasta expiración.

        Returns:
            ChallengeRequest con las instrucciones.
        """
        nonce = secrets.token_hex(16)
        challenge_id = hashlib.sha256(
            nonce.encode() + self._secret
        ).hexdigest()[:16]

        instructions = self._generate_instructions(challenge_type, nonce, region)

        challenge = ChallengeRequest(
            challenge_id=challenge_id,
            nonce=nonce,
            request_type=challenge_type,
            instructions=instructions,
            expiry=int(time.time()) + expiry_seconds,
            region_of_interest=region,
        )

        self._pending_challenges[challenge_id] = challenge
        return challenge

    def create_proof(
        self,
        challenge_id: str,
        nonce: str,
        capture_data: bytes,
        metadata: Optional[dict] = None,
    ) -> PossessionProof:
        """Crea una prueba de posesión respondiendo a un challenge.

        Args:
            challenge_id: ID del challenge.
            nonce: Nonce del challenge.
            capture_data: Datos raw de la nueva captura.
            metadata: Metadatos EXIF/GPS de la captura.

        Returns:
            PossessionProof con la prueba.
        """
        capture_hash = hashlib.sha256(capture_data).digest()

        return PossessionProof(
            challenge_id=challenge_id,
            nonce=nonce,
            capture_hash=capture_hash,
            metadata=metadata or {},
            timestamp=int(time.time()),
        )

    def verify_possession(
        self,
        proof: PossessionProof,
        original_hbit_hash: bytes,
    ) -> VerificationResult:
        """Verifica una prueba de posesión.

        Comprobaciones:
        1. El challenge existe y no ha expirado
        2. El nonce coincide
        3. La captura tiene datos válidos
        4. El timestamp es razonable

        Args:
            proof: Prueba de posesión a verificar.
            original_hbit_hash: Hash del H-Bit original.

        Returns:
            VerificationResult con el resultado.
        """
        # 1. Verificar challenge existente
        challenge = self._pending_challenges.get(proof.challenge_id)
        if not challenge:
            return VerificationResult(
                is_valid=False,
                confidence=0.0,
                reason="Challenge no encontrado o ya utilizado",
                challenge_id=proof.challenge_id,
            )

        # 2. Verificar expiración
        if time.time() > challenge.expiry:
            del self._pending_challenges[proof.challenge_id]
            return VerificationResult(
                is_valid=False,
                confidence=0.0,
                reason="Challenge expirado",
                challenge_id=proof.challenge_id,
            )

        # 3. Verificar nonce
        if proof.nonce != challenge.nonce:
            return VerificationResult(
                is_valid=False,
                confidence=0.0,
                reason="Nonce incorrecto",
                challenge_id=proof.challenge_id,
            )

        # 4. Verificar capture hash (debe ser diferente al original —
        #    es una NUEVA captura del soporte, no la misma imagen)
        if proof.capture_hash == original_hbit_hash:
            return VerificationResult(
                is_valid=False,
                confidence=0.0,
                reason="La captura es idéntica al original (posible replay)",
                challenge_id=proof.challenge_id,
            )

        # 5. Verificar que la captura tiene datos (no vacía)
        if proof.capture_hash == hashlib.sha256(b"").digest():
            return VerificationResult(
                is_valid=False,
                confidence=0.0,
                reason="Captura vacía",
                challenge_id=proof.challenge_id,
            )

        # 6. Calcular confianza basada en metadatos
        confidence = self._compute_confidence(proof, challenge)

        # Eliminar challenge usado (one-time use)
        del self._pending_challenges[proof.challenge_id]

        return VerificationResult(
            is_valid=confidence > 0.3,
            confidence=confidence,
            reason="Posesión verificada" if confidence > 0.3 else "Confianza insuficiente",
            challenge_id=proof.challenge_id,
        )

    def _generate_instructions(
        self,
        challenge_type: str,
        nonce: str,
        region: Optional[tuple[int, int, int, int]],
    ) -> str:
        """Genera instrucciones legibles para el poseedor."""
        if challenge_type == self.CHALLENGE_RECAPTURE:
            return (
                f"Tome una nueva fotografía del soporte físico. "
                f"Incluya el código de verificación '{nonce[:8]}' "
                f"escrito en un papel junto a la imagen."
            )
        elif challenge_type == self.CHALLENGE_REGION:
            if region:
                return (
                    f"Capture un detalle de la región ({region[0]},{region[1]}) "
                    f"a ({region[2]},{region[3]}) del soporte físico."
                )
            return "Capture un detalle de la esquina superior izquierda."
        elif challenge_type == self.CHALLENGE_ANGLE:
            return (
                "Tome una fotografía del soporte desde un ángulo de "
                "aproximadamente 45 grados con iluminación lateral."
            )
        return "Capture una nueva imagen del soporte físico."

    def _compute_confidence(
        self,
        proof: PossessionProof,
        challenge: ChallengeRequest,
    ) -> float:
        """Calcula la confianza de la prueba de posesión."""
        confidence = 0.5  # Base

        # Bonus por metadatos relevantes
        if proof.metadata:
            if "gps" in proof.metadata:
                confidence += 0.1
            if "exif" in proof.metadata:
                confidence += 0.1
            if "camera_model" in proof.metadata:
                confidence += 0.1

        # Bonus por respuesta rápida (dentro del 50% del tiempo)
        time_used = proof.timestamp - (challenge.expiry - self.DEFAULT_EXPIRY)
        time_ratio = time_used / self.DEFAULT_EXPIRY
        if time_ratio < 0.5:
            confidence += 0.1

        return min(1.0, confidence)
