// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.0;

/**
 * @title HBitRegistry
 * @dev Immutable registry for H-Bit cryptographic signatures.
 * Provides decentralized timestamping, proof of existence,
 * and AI provenance tracking for digital media.
 *
 * OriginType values mirror the H-Bit protocol:
 *   0x00 = HUMAN        — Content created entirely by a human
 *   0x01 = AI_GENERATED — Content generated entirely by AI
 *   0x02 = AI_ASSISTED  — Human content with AI assistance
 *   0xFF = UNKNOWN      — Undeclared origin
 */
contract HBitRegistry {
    
    struct Record {
        bytes32 authorHash;
        bytes32 payloadHash;
        uint8   originType;       // 0=HUMAN, 1=AI_GENERATED, 2=AI_ASSISTED, 255=UNKNOWN
        bytes32 aiModelHash;      // SHA-256 of AI model identifier (zero if N/A)
        uint256 timestamp;
        uint256 blockNumber;
        bool exists;
    }

    // Mapping from Image Hash (content) to H-Bit Record
    mapping(bytes32 => Record) private registry;

    // Index: origin type => list of content hashes (for provenance queries)
    mapping(uint8 => bytes32[]) private originIndex;

    // Events
    event HBitRegistered(
        bytes32 indexed imageHash, 
        bytes32 indexed authorHash, 
        bytes32 payloadHash,
        uint8   originType,
        bytes32 aiModelHash,
        uint256 timestamp
    );

    /**
     * @dev Register a new H-Bit signature with AI provenance metadata.
     * @param imageHash SHA-256 hash of the original clean media content.
     * @param authorHash SHA-256 hash of the author's public identity.
     * @param payloadHash SHA-256 hash of the full encoded payload.
     * @param originType Origin of the content (0=HUMAN, 1=AI_GENERATED, 2=AI_ASSISTED, 255=UNKNOWN).
     * @param aiModelHash SHA-256 hash of the AI model identifier (zero bytes if not applicable).
     * @param timestamp Unix timestamp of the signature creation.
     */
    function register(
        bytes32 imageHash, 
        bytes32 authorHash, 
        bytes32 payloadHash,
        uint8   originType,
        bytes32 aiModelHash,
        uint256 timestamp
    ) external {
        require(!registry[imageHash].exists, "H-Bit already registered for this content");
        
        registry[imageHash] = Record({
            authorHash: authorHash,
            payloadHash: payloadHash,
            originType: originType,
            aiModelHash: aiModelHash,
            timestamp: timestamp,
            blockNumber: block.number,
            exists: true
        });

        originIndex[originType].push(imageHash);

        emit HBitRegistered(imageHash, authorHash, payloadHash, originType, aiModelHash, timestamp);
    }

    /**
     * @dev Retrieve a registered H-Bit record.
     * @param imageHash The SHA-256 hash of the original media content.
     * @return authorHash The author's hash identity.
     * @return payloadHash The full payload hash.
     * @return originType The declared content origin type.
     * @return aiModelHash The AI model hash (zero if N/A).
     * @return timestamp The claimed creation timestamp.
     * @return blockNumber The block number when it was registered.
     * @return exists True if the record exists.
     */
    function getRecord(bytes32 imageHash) external view returns (
        bytes32 authorHash,
        bytes32 payloadHash,
        uint8   originType,
        bytes32 aiModelHash,
        uint256 timestamp,
        uint256 blockNumber,
        bool exists
    ) {
        Record memory rec = registry[imageHash];
        return (
            rec.authorHash,
            rec.payloadHash,
            rec.originType,
            rec.aiModelHash,
            rec.timestamp,
            rec.blockNumber,
            rec.exists
        );
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

    /**
     * @dev Check if content is declared as AI-generated or AI-assisted.
     * @param imageHash The SHA-256 hash of the media content.
     * @return isAI True if origin is AI_GENERATED or AI_ASSISTED.
     * @return originType The specific origin type.
     * @return aiModelHash The AI model hash (zero if N/A).
     */
    function isAIContent(bytes32 imageHash) external view returns (
        bool isAI,
        uint8 originType,
        bytes32 aiModelHash
    ) {
        Record memory rec = registry[imageHash];
        if (!rec.exists) {
            return (false, 0, bytes32(0));
        }
        bool ai = rec.originType == 1 || rec.originType == 2;
        return (ai, rec.originType, rec.aiModelHash);
    }

    /**
     * @dev Get the count of registered records by origin type.
     * @param originType The origin type to query.
     * @return count Number of records with the given origin type.
     */
    function countByOrigin(uint8 originType) external view returns (uint256 count) {
        return originIndex[originType].length;
    }
}
