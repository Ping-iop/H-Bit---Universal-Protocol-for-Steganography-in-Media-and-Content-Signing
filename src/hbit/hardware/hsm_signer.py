"""
Hardware Security Module (HSM) Mock Signer.
This is a Phase 11 mock implementation.

In a production environment, this module interacts with physical HSMs
(like YubiKey via PKCS#11, or AWS KMS) to perform cryptographic signing
without the private key ever entering the system RAM.
"""

from hbit.core.crypto import HBitKeyPair

class HSMSigner:
    """
    Mock interface for an HSM-backed H-Bit signer.
    """
    
    def __init__(self, key_id: str):
        self.key_id = key_id
        # In reality, this connects to the HSM context
        self._connected = True
        
    def sign_payload(self, core_payload_bytes: bytes) -> bytes:
        """
        Send the core payload to the HSM to be signed.
        
        Args:
            core_payload_bytes: The Hash and Timestamp data.
            
        Returns:
            The raw Ed25519 signature (64 bytes).
        """
        if not self._connected:
            raise RuntimeError("HSM not connected")
            
        print(f"[HSM MOCK] Requesting signature from hardware key: {self.key_id}")
        
        # MOCK BEHAVIOR: We generate an ephemeral key just to satisfy the mock
        # In hardware, the HSM does this internally with the secure key.
        mock_key = HBitKeyPair.generate()
        return mock_key.sign(core_payload_bytes)

    def get_public_key(self) -> bytes:
        """Retrieves the public key associated with the HSM key ID."""
        print(f"[HSM MOCK] Retrieving public key for {self.key_id}")
        return b"mock_public_key_bytes_"[:32].ljust(32, b"0")
