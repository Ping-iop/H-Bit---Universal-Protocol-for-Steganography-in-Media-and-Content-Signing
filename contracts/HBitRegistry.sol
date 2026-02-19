// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.0;

/**
 * @title HBitRegistry
 * @dev Immutable registry for H-Bit cryptographic signatures.
 * Provides decentralized timestamping and proof of existence for digital media.
 */
contract HBitRegistry {
    
    struct Record {
        bytes32 authorHash;
        bytes32 payloadHash;
        uint256 timestamp;
        uint256 blockNumber;
        bool exists;
    }

    // Mapping from Image Hash (content) to H-Bit Record
    mapping(bytes32 => Record) private registry;

    // Events
    event HBitRegistered(
        bytes32 indexed imageHash, 
        bytes32 indexed authorHash, 
        bytes32 payloadHash, 
        uint256 timestamp
    );

    /**
     * @dev Register a new H-Bit signature.
     * @param imageHash SHA-256 hash of the original clean media content.
     * @param authorHash SHA-256 hash of the author's public identity.
     * @param payloadHash SHA-256 hash of the full encoded payload.
     * @param timestamp Unix timestamp of the signature creation.
     */
    function register(
        bytes32 imageHash, 
        bytes32 authorHash, 
        bytes32 payloadHash, 
        uint256 timestamp
    ) external {
        require(!registry[imageHash].exists, "H-Bit already registered for this content");
        
        registry[imageHash] = Record({
            authorHash: authorHash,
            payloadHash: payloadHash,
            timestamp: timestamp,
            blockNumber: block.number,
            exists: true
        });

        emit HBitRegistered(imageHash, authorHash, payloadHash, timestamp);
    }

    /**
     * @dev Retrieve a registered H-Bit record.
     * @param imageHash The SHA-256 hash of the original media content.
     * @return authorHash The author's hash identity.
     * @return payloadHash The full payload hash.
     * @return timestamp The claimed creation timestamp.
     * @return blockNumber The block number when it was registered.
     * @return exists True if the record exists.
     */
    function getRecord(bytes32 imageHash) external view returns (
        bytes32 authorHash,
        bytes32 payloadHash,
        uint256 timestamp,
        uint256 blockNumber,
        bool exists
    ) {
        Record memory rec = registry[imageHash];
        return (rec.authorHash, rec.payloadHash, rec.timestamp, rec.blockNumber, rec.exists);
    }

    /**
     * @dev Quick verification if a specific payload matches the registered image.
     * @param imageHash The SHA-256 hash of the original media content.
     * @param payloadHash The SHA-256 hash of the payload to verify.
     * @return True if the registry matches the payload.
     */
    function verify(bytes32 imageHash, bytes32 payloadHash) external view returns (bool) {
        Record memory rec = registry[imageHash];
        return rec.exists && rec.payloadHash == payloadHash;
    }
}
