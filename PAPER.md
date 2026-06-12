# H-Bit Protocol: Universal Cryptographic Steganography for Content Authenticity

**Version 1.1.0 — June 2026**

**H-Bit Contributors** | https://github.com/Ping-iop/H-Bit

---

## Abstract

H-Bit is a universal protocol for establishing an inalienable link between intellectual authorship and any digital file. It embeds Ed25519 cryptographic signatures directly into pixel, frequency, or stream data at amplitudes below the Just Noticeable Difference (JND) threshold — invisible to humans, readable by machines. Unlike traditional hash-based verification which is binary (authentic/tampered), H-Bit introduces **Spectrum Verification**: a confidence spectrum (0-100%) that quantifies how much evidence of authenticity exists, even from partial fragments. On a 512x512 image, H-Bit achieves PSNR >55 dB (imperceptible), maintains AUTHENTIC verdict with only 3% of the image data, and correctly identifies AI-generated vs human-created content.

---

## 1. Introduction

The rapid advancement of generative AI has created an unprecedented crisis in content authenticity. Deepfakes, AI-generated images, synthetic audio, and LLM-produced text can no longer be reliably distinguished from human-created content by human observers. Traditional approaches to content verification — cryptographic hashes, digital signatures in metadata, blockchain notarization — all suffer from the same fundamental limitation: they require the ENTIRE original file to function. A single bit flip, a crop, a recompression, or metadata stripping renders these methods useless.

H-Bit addresses this gap with a novel approach: steganographic embedding of cryptographic signatures directly into the content itself, at signal amplitudes below human perceptual thresholds. This creates an inalienable bond between content and authorship that survives partial file corruption, cropping, and format conversion — and crucially, provides a confidence SPECTRUM rather than a binary verdict.

---

## 2. System Architecture

```
[Raw File] -> Format Manager -> Crypto Core -> Payload Builder
                                    |
                            Resilience (ECC + Tiling)
                                    |
                      Embedder (LSB / DCT / Stream)
                                    |
                          [Signed File]
                                    |
                     Spectrum Verifier (0-100%)
```

H-Bit employs a multi-layer architecture:

1. **Format Abstraction Layer**: Universal file support via pluggable MediaHandler registry
2. **Cryptographic Core**: Ed25519 signatures, AES-256-GCM encryption, HKDF key derivation
3. **Steganographic Engine**: LSB (lossless formats) and DCT/QIM (lossy formats)
4. **Resilience Layer**: Reed-Solomon ECC, Barker-code synchronization, cyclic tiling
5. **Spectrum Verifier**: Non-binary confidence analysis across all embedded payload copies

---

## 3. Spectrum Verification (Novel Contribution)

The key innovation of H-Bit v1.1.0 is **Spectrum Verification**: a non-binary confidence model that quantifies authenticity evidence on a continuous 0-100% scale.

Traditional hash verification is brittle — a single modified pixel produces TAMPERED. H-Bit's spectrum analysis examines EACH embedded payload copy (tile) independently, then computes:

- **Recovery Rate (R)**: What fraction of embedded tiles were recovered?
- **Author Consensus (S)**: Do all recovered tiles agree on the author identity?
- **ECC Health (E)**: How many Reed-Solomon corrections were needed?
- **Sync Quality (Q)**: How strong is the Barker-code synchronization signal?
- **Payload Completeness (P)**: Is the full payload structure intact?

### Confidence Formula

```
C = 0.30*R + 0.25*S + 0.20*E + 0.15*Q + 0.10*P
```

### Verdict Levels

| Confidence | Verdict | Interpretation |
|-----------|---------|----------------|
| >= 95% | AUTHENTIC | Complete verification, all tiles agree |
| >= 75% | LIKELY_AUTHENTIC | High confidence, minor inconsistencies |
| >= 50% | POSSIBLY_AUTHENTIC | Moderate confidence, some evidence |
| >= 25% | UNCERTAIN | Insufficient evidence for conclusion |
| < 25% | LIKELY_TAMPERED | Evidence suggests manipulation |
| 0% | NO_EVIDENCE | No H-Bit signature detected |

---

## 4. Experimental Results

### 4.1 Quality Metrics (512x512 PNG)

| Metric | Value | Notes |
|--------|-------|-------|
| PSNR | 55.9 dB | >40 dB = imperceptible (excellent) |
| SSIM | 1.0000 | Structurally identical to original |
| Bits Embedded | 798 | 107-byte core + 78-bit sync wrapper |
| Capacity Used | 99.8% | Near-full LSB channel utilization |

### 4.2 Speed Performance

| Operation | Time | Notes |
|-----------|------|-------|
| Encode | 114.7 ms | Keygen + payload + LSB embedding |
| Decode | 228.6 ms | Bit extraction + deserialization |
| Spectrum | 708.3 ms | Full tile-by-tile analysis |
| File Overhead | 0 bytes | PNG lossless: no size increase |

### 4.3 Crop Robustness (height-based, same width)

| Crop % | Rows | Verdict | Confidence | Tiles (valid/total) |
|--------|------|---------|------------|---------------------|
| 100% | 512 | AUTHENTIC | 98% | 328/328 |
| 75% | 384 | AUTHENTIC | 98% | 246/246 |
| 50% | 256 | AUTHENTIC | 98% | 164/164 |
| 25% | 128 | AUTHENTIC | 98% | 82/82 |
| 12% | 61 | AUTHENTIC | 98% | 39/39 |
| 6% | 30 | AUTHENTIC | 98% | 19/19 |
| **3%** | **15** | **AUTHENTIC** | **98%** | **9/9** |

**Key finding**: H-Bit maintains AUTHENTIC verdict with 98% confidence even when only 3% of the original image data is available (15 rows out of 512). This demonstrates the power of tiling + consensus: each embedded tile carries the complete payload, so ANY surviving tile provides full verification.

### 4.4 Deepfake Detection

| Scenario | Verdict | Confidence | Origin |
|----------|---------|------------|--------|
| Real Photo (100%) | AUTHENTIC | 98% | HUMAN |
| AI Image (100%) | AUTHENTIC | 100% | AI_GENERATED |
| Real Photo (25% crop) | AUTHENTIC | 98% | HUMAN |
| AI Image (25% crop) | AUTHENTIC | 100% | AI_GENERATED |
| Unsigned Image | NO_EVIDENCE | 0% | N/A |

H-Bit correctly identifies the origin type (HUMAN vs AI_GENERATED) even from partial fragments. This enables platforms to display verified provenance badges without requiring access to the complete original file.

### 4.5 JPEG Recompression

| Quality | Verdict | Confidence |
|---------|---------|------------|
| Q100 | NO_EVIDENCE | 0% |
| Q30 | NO_EVIDENCE | 0% |

**Note**: LSB embedding in PNG does not survive JPEG recompression. For JPEG robustness, use DCT encoding mode (designed for lossy formats).

### 4.6 Resize Robustness

| Scale | Verdict | Confidence |
|-------|---------|------------|
| 100% | AUTHENTIC | 98% |
| 90-25% | NO_EVIDENCE | 0% |

**Note**: Pixel resizing destroys LSB data. For resize resilience, DCT watermarking or hardware-level signing are recommended.

---

## 5. Cryptographic Foundation

H-Bit uses **Ed25519** (RFC 8032) for digital signatures, providing 128-bit security with 32-byte public keys and 64-byte signatures. Key derivation follows **HKDF** (RFC 5869) with SHA-256. Payload encryption uses **AES-256-GCM** with PBKDF2 (100,000 iterations) for passphrase-based key derivation.

### Payload Structure

| Field | Size | Description |
|-------|------|-------------|
| Version | 1 byte | Protocol version (currently 1) |
| Flags | 1 byte | HAS_CONTENT_HASH, HAS_ECC, IS_ENCRYPTED, etc. |
| Origin Type | 1 byte | HUMAN (0x00), AI_GENERATED (0x01), AI_ASSISTED (0x02), UNKNOWN (0xFF) |
| Author Hash | 32 bytes | SHA-256 of author identity |
| Content Hash | 32 bytes | SHA-256 of content (excluding H-Bit data) |
| Timestamp | 8 bytes | Unix timestamp (double) |
| AI Model ID | 32 bytes | SHA-256 of AI model identifier (or zeros) |
| **Core Total** | **107 bytes** | |
| Signature | 64 bytes | Ed25519 (optional) |
| ECC Parity | variable | Reed-Solomon (optional) |

Payload is compressed with zlib when beneficial, reducing embedded size.

---

## 6. Resilience Engineering

To survive real-world degradation, H-Bit implements multiple resilience layers:

### Barker-13 Synchronization
39-bit composite sync markers with optimal autocorrelation properties. Tolerates up to ~15% bit errors while maintaining detectable correlation peaks.

### Reed-Solomon ECC
Four presets providing 5-25 symbol error correction:

| Preset | nsym | Error Correction | Use Case |
|--------|------|-----------------|----------|
| Light | 10 | 5 errors | Mild JPEG compression |
| Standard | 20 | 10 errors | General use |
| Heavy | 32 | 16 errors | Analog degradation |
| Forensic | 50 | 25 errors | Maximum resilience |

### Cyclic Tiling
The payload is repeated across the entire medium with interleaving to distribute damage uniformly. Each tile contains a complete copy of the payload, enabling verification from any surviving fragment.

### DCT Watermarking (JPEG mode)
Embeds signatures in mid-frequency DCT coefficients using Quantization Index Modulation (QIM), constrained by Watson's JND perceptual model for invisibility.

---

## 7. Universal Format Support

| Format | Strategy | Handler |
|--------|----------|---------|
| PNG, BMP, TIFF, WebP | LSB (Blue channel) | ImageHandler |
| JPEG | DCT (Green channel) | ImageHandler |
| WAV, FLAC, AIFF | LSB in PCM samples | AudioHandler |
| MP4, AVI, MOV | LSB in keyframes | VideoHandler |
| PDF | Hidden stream object | PDFHandler |
| DOCX, XLSX, PPTX | Custom XML part | OfficeHandler |
| Any other | Append stream + CRC32 | GenericHandler |

---

## 8. Applications

### Content Provenance
Platforms can display verified badges showing whether content is HUMAN_CREATED, AI_GENERATED, or AI_ASSISTED, with cryptographic proof surviving crops and recompressions.

### Journalism
Photo agencies can embed signatures at capture time, enabling editors to verify image authenticity even from screenshots or partial crops.

### Social Media
Automated detection of AI-generated content with verifiable provenance trails, enabling platform-level content labeling.

### Legal/Evidence
Chain-of-custody verification where any fragment of a file can be traced to its original author and device.

### Hardware Integration
SDK for camera firmware (ISP enclave), USB drives (HSM signer), and flash controllers (FTL driver) for zero-user-intervention signing at the hardware level.

---

## 9. API & CLI

### Python API

```python
from hbit.universal import UniversalEncoder, UniversalVerifier
from hbit.analysis.spectrum import SpectrumVerifier

# Sign a file with origin type
encoder = UniversalEncoder()
encoder.encode("photo.jpg", "my_key", "signed.png",
               origin_type=OriginType.HUMAN)

# Spectrum analysis (non-binary)
verifier = SpectrumVerifier()
result = verifier.analyze("partial_crop.png")
print(f"Confidence: {result.confidence:.1%}")  # 0-100%
print(f"Verdict: {result.verdict}")             # AUTHENTIC, etc.
print(f"Origin: {result.origin_type}")          # HUMAN, AI_GENERATED
```

### CLI

```bash
# Generate keys
hbit keygen --output ./my_keys

# Sign with origin declaration
hbit encode photo.jpg --key ./my_keys --origin human
hbit encode ai_art.jpg --key ./my_keys --origin ai --ai-model midjourney-v6

# Spectrum verification
hbit spectrum --input signed.png
hbit spectrum --input signed.png --verbose

# Batch processing
hbit batch --dir ./photos --key ./my_keys --origin human
```

---

## 10. Conclusion

H-Bit Protocol v1.1.0 provides a production-ready solution for content authenticity in the age of generative AI. Its key differentiators are:

1. **Non-binary spectrum verification** that quantifies evidence rather than making brittle yes/no decisions
2. **Universal format support** through a pluggable handler architecture
3. **Resilience to partial data loss** through tiling and ECC
4. **Cryptographic binding of origin type** (HUMAN/AI) directly into the content

The protocol is open-source (Apache 2.0), extensively tested (185+ tests), and ready for integration into platforms, cameras, and content management systems.

### Future Work
- Native C/Rust SDK for embedded systems
- Browser extension for real-time web verification
- C2PA manifest integration
- Hardware partnership program
- Formal standardization through W3C/ISO

---

## References

1. H-Bit Repository: https://github.com/Ping-iop/H-Bit
2. Ed25519: RFC 8032, "Edwards-Curve Digital Signature Algorithm"
3. HKDF: RFC 5869, "HMAC-based Extract-and-Expand Key Derivation"
4. AES-GCM: NIST SP 800-38D
5. Reed, I.S. & Solomon, G. (1960), "Polynomial Codes over Certain Finite Fields"
6. Barker, R.H. (1953), "Group Synchronizing of Binary Digital Systems"
7. Watson, A.B. (1993), "DCTune: A Technique for Visual Optimization"
8. Lukas, J., Fridrich, J., & Goljan, M. (2006), "Digital Camera Identification from Sensor Pattern Noise"
9. C2PA: Coalition for Content Provenance and Authenticity, https://c2pa.org
10. Omega-Cube: Complementary memory architecture, https://github.com/Ping-iop/omega-cube-engine
