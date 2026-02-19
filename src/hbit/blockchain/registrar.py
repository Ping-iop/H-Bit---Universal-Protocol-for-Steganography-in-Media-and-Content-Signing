"""
Registrar H-Bit en blockchain (Polygon / Ethereum L2).

Registra un hash de la firma H-Bit en un smart contract,
proporcionando un timestamping descentralizado inmutable.

Requisitos:
- web3.py (dependencia opcional: pip install hbit[blockchain])
- RPC endpoint de Polygon (Alchemy, Infura, o nodo propio)
- Wallet con MATIC para gas fees

El contrato almacena un mapping de imageHash → HBitRecord,
donde cada registro contiene el author hash, timestamp, y
el hash del payload H-Bit completo.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Optional


# ABI mínimo del contrato de registro H-Bit
# Se despliega con: solc --abi --bin HBitRegistry.sol
REGISTRY_ABI = json.loads("""[
    {
        "inputs": [
            {"name": "imageHash", "type": "bytes32"},
            {"name": "authorHash", "type": "bytes32"},
            {"name": "payloadHash", "type": "bytes32"},
            {"name": "timestamp", "type": "uint256"}
        ],
        "name": "register",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [{"name": "imageHash", "type": "bytes32"}],
        "name": "getRecord",
        "outputs": [
            {"name": "authorHash", "type": "bytes32"},
            {"name": "payloadHash", "type": "bytes32"},
            {"name": "timestamp", "type": "uint256"},
            {"name": "blockNumber", "type": "uint256"},
            {"name": "exists", "type": "bool"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"name": "imageHash", "type": "bytes32"},
            {"name": "payloadHash", "type": "bytes32"}
        ],
        "name": "verify",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function"
    }
]""")


@dataclass(frozen=True)
class BlockchainRecord:
    """Registro blockchain de una firma H-Bit.

    Attributes:
        image_hash: Hash SHA-256 del contenido de la imagen.
        author_hash: Hash del autor (H-Bit identity).
        payload_hash: Hash del payload H-Bit completo.
        timestamp_chain: Timestamp del bloque en la cadena.
        block_number: Número de bloque de la transacción.
        tx_hash: Hash de la transacción.
        chain_id: ID de la cadena (137 = Polygon Mainnet).
        exists: Si el registro existe on-chain.
    """

    image_hash: bytes
    author_hash: bytes
    payload_hash: bytes
    timestamp_chain: int
    block_number: int
    tx_hash: str
    chain_id: int
    exists: bool


@dataclass(frozen=True)
class RegistrationResult:
    """Resultado del registro en blockchain.

    Attributes:
        success: Si la transacción fue exitosa.
        record: Registro blockchain resultante.
        gas_used: Gas consumido por la transacción.
        error: Mensaje de error si falló.
    """

    success: bool
    record: Optional[BlockchainRecord]
    gas_used: int
    error: Optional[str]


class HBitRegistrar:
    """Cliente para registrar y verificar firmas H-Bit en blockchain.

    Uso:
        registrar = HBitRegistrar(rpc_url, contract_address, private_key)
        result = registrar.register(image_hash, author_hash, payload_hash)
        record = registrar.lookup(image_hash)
    """

    # Chain IDs conocidos
    POLYGON_MAINNET = 137
    POLYGON_AMOY = 80002  # Testnet
    ETHEREUM_MAINNET = 1
    ETHEREUM_SEPOLIA = 11155111

    def __init__(
        self,
        rpc_url: str,
        contract_address: str,
        private_key: Optional[str] = None,
        chain_id: int = POLYGON_MAINNET,
    ):
        """Inicializa el registrar.

        Args:
            rpc_url: URL del nodo RPC (ej: https://polygon-rpc.com).
            contract_address: Dirección del contrato HBitRegistry.
            private_key: Clave privada del wallet (para escritura).
            chain_id: ID de la cadena.
        """
        try:
            from web3 import Web3
        except ImportError:
            raise ImportError(
                "web3.py es necesario para blockchain. "
                "Instalar con: pip install hbit[blockchain]"
            )

        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        self.contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=REGISTRY_ABI,
        )
        self.chain_id = chain_id
        self._private_key = private_key
        self._account = None

        if private_key:
            self._account = self.w3.eth.account.from_key(private_key)

    @property
    def is_connected(self) -> bool:
        """Verifica la conexión al nodo RPC."""
        return self.w3.is_connected()

    def register(
        self,
        image_hash: bytes,
        author_hash: bytes,
        payload_hash: bytes,
        timestamp: Optional[int] = None,
    ) -> RegistrationResult:
        """Registra una firma H-Bit en la blockchain.

        Args:
            image_hash: SHA-256 del contenido visual (32 bytes).
            author_hash: Hash del autor H-Bit (32 bytes).
            payload_hash: SHA-256 del payload completo (32 bytes).
            timestamp: Timestamp Unix (default: time.time()).

        Returns:
            RegistrationResult con el resultado del registro.
        """
        if not self._account:
            return RegistrationResult(
                success=False, record=None, gas_used=0,
                error="Clave privada no configurada. Solo lectura.",
            )

        if timestamp is None:
            timestamp = int(time.time())

        try:
            # Construir transacción
            tx = self.contract.functions.register(
                image_hash, author_hash, payload_hash, timestamp
            ).build_transaction({
                "from": self._account.address,
                "nonce": self.w3.eth.get_transaction_count(self._account.address),
                "chainId": self.chain_id,
            })

            # Firmar y enviar
            signed = self.w3.eth.account.sign_transaction(tx, self._private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)

            # Esperar confirmación
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

            record = BlockchainRecord(
                image_hash=image_hash,
                author_hash=author_hash,
                payload_hash=payload_hash,
                timestamp_chain=timestamp,
                block_number=receipt.blockNumber,
                tx_hash=receipt.transactionHash.hex(),
                chain_id=self.chain_id,
                exists=True,
            )

            return RegistrationResult(
                success=receipt.status == 1,
                record=record,
                gas_used=receipt.gasUsed,
                error=None if receipt.status == 1 else "Transacción revertida",
            )

        except Exception as e:
            return RegistrationResult(
                success=False, record=None, gas_used=0,
                error=str(e),
            )

    def lookup(self, image_hash: bytes) -> Optional[BlockchainRecord]:
        """Busca un registro H-Bit en la blockchain.

        Args:
            image_hash: SHA-256 del contenido visual.

        Returns:
            BlockchainRecord si existe, None si no.
        """
        try:
            result = self.contract.functions.getRecord(image_hash).call()
            author_hash, payload_hash, ts, block_num, exists = result

            if not exists:
                return None

            return BlockchainRecord(
                image_hash=image_hash,
                author_hash=author_hash,
                payload_hash=payload_hash,
                timestamp_chain=ts,
                block_number=block_num,
                tx_hash="",  # No disponible desde view function
                chain_id=self.chain_id,
                exists=True,
            )
        except Exception:
            return None

    def verify_on_chain(
        self,
        image_hash: bytes,
        payload_hash: bytes,
    ) -> bool:
        """Verifica que un H-Bit está registrado en la blockchain.

        Args:
            image_hash: SHA-256 del contenido visual.
            payload_hash: SHA-256 del payload extraído.

        Returns:
            True si el registro existe y coincide.
        """
        try:
            return self.contract.functions.verify(
                image_hash, payload_hash
            ).call()
        except Exception:
            return False


def create_offline_proof(
    image_hash: bytes,
    author_hash: bytes,
    payload_hash: bytes,
) -> dict:
    """Crea una prueba offline para registro posterior.

    Genera un paquete JSON firmable que puede registrarse
    en blockchain más tarde (sin conexión en el momento de la firma).

    Args:
        image_hash: SHA-256 del contenido visual.
        author_hash: Hash del autor H-Bit.
        payload_hash: SHA-256 del payload.

    Returns:
        Dict con los datos de la prueba offline.
    """
    return {
        "version": 1,
        "protocol": "hbit",
        "image_hash": image_hash.hex(),
        "author_hash": author_hash.hex(),
        "payload_hash": payload_hash.hex(),
        "timestamp": int(time.time()),
        "status": "pending_registration",
    }
