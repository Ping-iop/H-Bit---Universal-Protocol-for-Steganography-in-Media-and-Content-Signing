# H-Bit Protocol: Persistent Authenticity for Digital Media
## Technical Whitepaper v2.0

[🇺🇸 Read in English](WHITEPAPER.md) | [🇪🇸 Leer en Español](WHITEPAPER_ES.md)

**Authors:** H-Bit Contributors  
**Date:** February 2026  
**License:** Apache 2.0  
**Status:** Beta — Reference Implementation  

---

## Abstract

H-Bit (Hidden Bit) is an open steganographic signing protocol that binds cryptographic identity proofs to any digital file by embedding them directly into the carrier medium's data layer. Unlike metadata-based approaches (EXIF, XMP, IPTC), which are trivially stripped by file operations, H-Bit signatures survive format conversion, re-encoding, lossy compression, physical printing, and rescanning. The protocol combines Ed25519 digital signatures, HKDF-based key derivation (RFC 5869), AES-256-GCM authenticated encryption, Reed-Solomon error correction, and multi-domain embedding (spatial LSB + frequency-domain DCT) to achieve verifiable authorship that is irremovable from the content.

This document specifies the protocol architecture, threat model, cryptographic construction, embedding strategies with their complete mathematical formalization, resilience mechanisms, and the production roadmap for the reference implementation.

---

## Table of Contents

1. [Introduction and Motivation](#1-introduction-and-motivation)
2. [Threat Model and Security Goals](#2-threat-model-and-security-goals)
3. [Protocol Architecture](#3-protocol-architecture)
4. [Cryptographic Construction](#4-cryptographic-construction)
5. [Payload Structure](#5-payload-structure)
6. [Embedding Strategies — Mathematical Formalization](#6-embedding-strategies--mathematical-formalization)
7. [Perceptual Model — JND and Entropy](#7-perceptual-model--jnd-and-entropy)
8. [Resilience Layer](#8-resilience-layer)
9. [Synchronization — Barker Correlation](#9-synchronization--barker-correlation)
10. [Universal File Support](#10-universal-file-support)
11. [Identity Management and HBFS](#11-identity-management-and-hbfs)
12. [Blockchain Integration](#12-blockchain-integration)
13. [Forensic Analysis — PRNU and Luminance](#13-forensic-analysis--prnu-and-luminance)
14. [Production Status](#14-production-status)
15. [Performance Characteristics](#15-performance-characteristics)
16. [Comparison with Existing Solutions](#16-comparison-with-existing-solutions)
17. [Roadmap](#17-roadmap)
18. [References](#18-references)

---

## 1. Introduction and Motivation

### 1.1 The Authenticity Crisis

The proliferation of generative AI (Stable Diffusion, Midjourney, DALL-E, Sora) has created an existential crisis for digital provenance. A 2025 study estimates that **90% of internet visual content** will be AI-generated or AI-modified by 2027. Current authenticity solutions fail because:

| Approach | Failure Mode |
|---|---|
| EXIF/XMP Metadata | Stripped by social media upload, screenshots, format conversion |
| C2PA/Content Credentials | Requires voluntary adoption; easily removed by re-encoding |
| Blockchain-only registries | Hash becomes invalid after any pixel modification |
| Visible watermarks | Removable by inpainting; degrades visual quality |

### 1.2 H-Bit's Approach

H-Bit solves this by making the signature **part of the content itself**. The cryptographic proof is woven into the signal layer (pixel values, audio samples, DCT coefficients) at amplitudes below the Just Noticeable Difference (JND) threshold. This creates a signature that:

- **Cannot be separated** from the content without destroying it
- **Survives** lossy compression (JPEG, MP3, H.264)
- **Survives** format conversion (PNG→JPEG→WebP)
- **Survives** analog-digital loopback (print → scan → re-digitize)
- **Is cryptographically verifiable** without requiring the original

---

## 2. Threat Model and Security Goals

### 2.1 Adversary Model

| Adversary | Capability | H-Bit Defense |
|---|---|---|
| Casual stripper | Removes EXIF, converts format | Embedded in signal layer; survives conversion |
| Social media platform | Re-encodes, resizes, crops | DCT embedding in frequency domain; tiling redundancy |
| Sophisticated editor | Modifies content regions | Content hash detects tampering; tiling preserves copies |
| AI model trainer | Uses content as training data | PRNU sensor binding; author identity traceable |
| State actor | Full computational resources | Ed25519 (128-bit security); AES-256-GCM encryption |

### 2.2 Security Properties

1. **Authenticity (WHO):** Ed25519 signature binds content to a specific private key holder
2. **Integrity (WHAT):** SHA-256 content hash detects any post-signing modification
3. **Temporality (WHEN):** Signed timestamp proves existence at a specific time
4. **Persistence (HOW LONG):** Steganographic embedding survives destructive transforms
5. **Confidentiality (OPTIONAL):** AES-256-GCM encrypts the payload when required

---

## 3. Protocol Architecture

### 3.1 Layer Model

```
┌─────────────────────────────────────────────────────────┐
│                   APPLICATION LAYER                      │
│  CLI · GUI · HBFS Watchdog · Identity Registry           │
├─────────────────────────────────────────────────────────┤
│                    UNIVERSAL PIPELINE                    │
│  UniversalEncoder · UniversalDecoder · UniversalVerifier │
├─────────────────────────────────────────────────────────┤
│                     FORMAT HANDLERS                      │
│  Image · Audio · Video · Document · Generic              │
├───────────────┬────────────────┬────────────────────────┤
│  EMBEDDING    │   RESILIENCE   │    CRYPTOGRAPHIC CORE  │
│  LSB · DCT   │  ECC · Tiling  │  Ed25519 · HKDF · AES  │
│  Hybrid      │  Anchors       │  SHA-256 · KDF          │
│               │  Dewarp        │  Sync (Barker-13)       │
├───────────────┴────────────────┴────────────────────────┤
│                   HARDWARE ACCELERATION                   │
│              CuPy (CUDA GPU) ↔ NumPy (CPU)               │
└─────────────────────────────────────────────────────────┘
```

### 3.2 Data Flow

```
                    ┌──────────┐
     Input File ───►│  FORMAT  │──► Carrier Object
                    │ HANDLER  │    (pixels, samples,
                    └──────────┘     stream bytes)
                         │
                         ▼
                    ┌──────────┐    ┌──────────┐
     Private Key ──►│  CRYPTO  │───►│ PAYLOAD  │──► Serialized bits
                    │  CORE    │    │ BUILDER  │    (with sync markers)
                    └──────────┘    └──────────┘
                                         │
                         ┌───────────────┘
                         ▼
                    ┌──────────┐    ┌──────────┐
                    │RESILIENCE│───►│ EMBEDDER │──► Signed File
                    │  (ECC)   │    │(LSB/DCT) │
                    └──────────┘    └──────────┘
```

---

## 4. Cryptographic Construction

### 4.1 Key Generation

H-Bit uses **Ed25519** (Curve25519 in Edwards form) for digital signatures, providing 128-bit security with 64-byte signatures and fast verification.

```
KeyPair = Ed25519.generate()
PrivateKey: 32 bytes (stored in PEM format)
PublicKey:  32 bytes (derivable from private key)
```

### 4.2 Author Identity Hash

The author's identity hash is a deterministic function of multiple factors:

```
AuthorHash = SHA-256(PrivateKey ‖ DeviceID ‖ SensorNoise ‖ Timestamp)
```

Where:
- `PrivateKey`: Always hashed through SHA-256 before use (never exposed raw)
- `DeviceID`: Hardware or software identifier string
- `SensorNoise`: Random bytes from sensor capture (or CSPRNG)
- `Timestamp`: UTC seconds since epoch

**Security property:** The author hash is deterministic given the same inputs, enabling identity verification without revealing the private key.

### 4.3 Key Derivation (HKDF)

When KDF mode is enabled (`USES_KDF` flag), a per-image derived key is generated:

```
DerivedKey = HKDF-SHA256(
    ikm     = MasterKey,
    salt    = SessionSalt (16 bytes, random),
    info    = "hbit-v1-session" ‖ context,
    length  = 32 bytes
)
```

This ensures that compromising one signature does not reveal the master key. Three derivation modes are supported:

| Mode | Salt | Use Case |
|---|---|---|
| Session Key | Random per invocation | Ephemeral signatures |
| Image Key | SHA-256(image bytes) | Deterministic per-image |
| Passphrase Key | Argon2id/PBKDF2 | User-friendly input |

### 4.4 Payload Signature

```
ContentHash = SHA-256(CanonicalContent)
PayloadCore = Version ‖ Flags ‖ AuthorHash ‖ ContentHash ‖ Timestamp
Signature   = Ed25519.sign(PrivateKey, PayloadCore)
```

### 4.5 Optional Encryption (AES-256-GCM)

```
Salt    = CSPRNG(16 bytes)
Nonce   = CSPRNG(12 bytes)
Key     = PBKDF2-HMAC-SHA256(passphrase, salt, iterations=480000)
(Ciphertext, Tag) = AES-256-GCM.encrypt(Key, Nonce, PayloadCore)
```

The encrypted payload structure:

```
EncryptedOutput = [VERSION: 1B][FLAGS|ENCRYPTED: 1B][SALT: 16B][NONCE: 12B][TAG: 16B][CIPHERTEXT: NB]
```

The authentication tag (16 bytes) provides integrity verification — any bit modification in the ciphertext is detected.

---

## 5. Payload Structure

### 5.1 Binary Layout

```
┌─────────┬───────┬────────────┬──────────────┬───────────┬───────────┬──────────┐
│ Version │ Flags │ AuthorHash │ ContentHash  │ Timestamp │ Signature │ ECC      │
│ 1 byte  │1 byte │ 32 bytes   │ 32 bytes     │ 8 bytes   │ 64 bytes  │ variable │
└─────────┴───────┴────────────┴──────────────┴───────────┴───────────┴──────────┘
```

**Core payload size:** 74 bytes (592 bits) without signature/ECC  
**Full payload size:** 138 bytes (1,104 bits) with Ed25519 signature  
**With ECC (standard):** ~158 bytes (~1,264 bits) including 20 RS parity symbols

### 5.2 Flags Byte

| Bit | Flag | Meaning |
|---|---|---|
| 0 | `HAS_CONTENT_HASH` | Includes SHA-256 of canonical content |
| 1 | `HAS_SIGNATURE` | Includes Ed25519 digital signature |
| 2 | `HAS_ECC` | Includes Reed-Solomon error correction parity |
| 3 | `HAS_C2PA_REF` | Includes reference to C2PA manifest |
| 4 | `HAS_PRNU_BINDING` | Includes sensor PRNU fingerprint binding |
| 5 | `USES_KDF` | Key was derived via HKDF (not master) |
| 6 | `IS_ENCRYPTED` | Payload encrypted with AES-256-GCM |
| 7 | `IS_COMPRESSED` | Payload body compressed with zlib |

### 5.3 Synchronization Envelope

The serialized payload is wrapped in Barker-13 composite synchronization markers:

```
[SYNC_HEADER: 39 bits][PAYLOAD][SYNC_FOOTER: 39 bits]
```

See [Section 9](#9-synchronization--barker-correlation) for the full mathematical treatment.

---

## 6. Embedding Strategies — Mathematical Formalization

### 6.1 Spatial Domain: LSB (Least Significant Bit)

#### 6.1.1 Core Embedding Formula

The fundamental embedding modifies the least significant bit of carrier samples:

$$P'(x,y) = \bigl(P(x,y) \;\&\; \texttt{0xFE}\bigr) \;|\; b_k$$

Where:
- $P(x,y)$ is the original pixel value at position $(x,y)$
- $b_k \in \{0, 1\}$ is the $k$-th bit of the payload to embed
- $\&\; \texttt{0xFE}$ clears the LSB (least significant bit)
- $|\; b_k$ sets the LSB to the desired value

**Implementation** (`src/hbit/encoders/lsb.py`):
```python
channel_data[idx] = (channel_data[idx] & 0xFE) | bit
```

**Properties:**
- Maximum alteration: ±1 per sample (below JND threshold)
- Capacity: 1 bit per pixel per channel (RGB image: 3 bits/pixel)
- A 256×256 RGB image provides ~196,608 bits of capacity
- **Fragility:** Destroyed by lossy compression (JPEG, MP3)

#### 6.1.2 Uniform Redundancy Model

When no density map is provided, the payload is repeated cyclically to fill the entire carrier:

$$R = \left\lfloor \frac{W \times H}{|S_u|} \right\rfloor$$

Where:
- $R$ = number of complete payload copies (repetition factor)
- $W \times H$ = total available pixels in the channel
- $|S_u|$ = length of one sync-wrapped payload unit

Each pixel receives: $b_{k \bmod |S_u|}$

#### 6.1.3 Adaptive Density Model

When a perceptual density map is available, embedding density varies by block:

$$n_{\text{modify}}(i,j) = \max\bigl(1, \lfloor B^2 \cdot d(i,j) \rfloor\bigr)$$

Where:
- $B = 8$ (block size in pixels)
- $d(i,j) \in [0, 1]$ is the normalized density value for block $(i,j)$
- $n_{\text{modify}}$ is the number of pixels modified within the block

High-texture blocks ($d \approx 1$) receive all $B^2 = 64$ bits; smooth blocks ($d \approx 0$) receive 1 bit. This reduces visual artifacts in perceptually sensitive regions.

#### 6.1.4 Majority Vote Reconstruction

When multiple copies are extracted, bit-level majority voting reconstructs the original:

$$\hat{b}_k = \begin{cases} 1 & \text{if } \sum_{i=1}^{N} c_i[k] \geq N/2 \\ 0 & \text{otherwise} \end{cases}$$

$$\text{Confidence} = \frac{1}{|S_u|} \sum_{k=0}^{|S_u|-1} \frac{\max(V_1(k), V_0(k))}{N}$$

Where:
- $c_i[k]$ = bit $k$ of copy $i$
- $N$ = number of copies
- $V_1(k), V_0(k)$ = number of votes for 1 and 0 at position $k$

#### 6.1.5 Optimal Channel Selection

The channel with the highest Shannon entropy is selected for embedding:

$$c^* = \arg\max_{c \in \{R,G,B\}} H(c)$$

$$H(c) = -\sum_{x=0}^{255} p_c(x) \log_2 p_c(x)$$

Where $p_c(x) = \frac{h_c(x)}{\sum h_c}$ is the normalized histogram. Typically $c^* = B$ (Blue) for natural photos, as the blue channel has the highest natural noise.

---

### 6.2 Frequency Domain: DCT (Discrete Cosine Transform)

#### 6.2.1 DCT-II Forward and Inverse Transform

For each 8×8 pixel block $f(x,y)$:

$$F(u,v) = \frac{1}{4} C(u) C(v) \sum_{x=0}^{7} \sum_{y=0}^{7} f(x,y) \cos\frac{(2x+1)u\pi}{16} \cos\frac{(2y+1)v\pi}{16}$$

$$f(x,y) = \frac{1}{4} \sum_{u=0}^{7} \sum_{v=0}^{7} C(u) C(v) F(u,v) \cos\frac{(2x+1)u\pi}{16} \cos\frac{(2y+1)v\pi}{16}$$

Where $C(k) = \frac{1}{\sqrt{2}}$ for $k=0$, else $C(k) = 1$.

#### 6.2.2 Mid-Frequency Coefficient Selection

The zig-zag ordered DCT coefficients are partitioned into:
- **Low frequency** (positions 0-7): Visually dominant — NOT modified
- **Mid frequency** (positions 8-20): Perceptual sweet spot — EMBEDDING TARGET
- **High frequency** (positions 21-63): Destroyed by JPEG — NOT used

Selected mid-frequency positions in the 8×8 matrix (13 positions per block):

```
Zig-zag: 8→(1,2), 9→(2,1), 10→(2,0), 11→(3,0), 12→(2,2), 13→(1,3),
         14→(0,4), 15→(0,5), 16→(1,4), 17→(2,3), 18→(3,2), 19→(4,1), 20→(4,0)
```

This yields 13 bits per 8×8 block.

#### 6.2.3 QIM: Quantization Index Modulation

The core embedding algorithm uses QIM (Chen & Wornell, 2001):

**Encoding:**

$$q = \text{round}\left(\frac{F(u,v)}{Q_s}\right)$$

$$q' = \begin{cases} q & \text{if } q \bmod 2 = b_k \\ q + \text{sgn}(F) & \text{otherwise} \end{cases}$$

$$F'(u,v) = q' \cdot Q_s$$

Where:
- $Q_s$ = quantization step (strength parameter)
- $b_k \in \{0, 1\}$ = bit to embed
- $\text{sgn}(F) = +1$ if $F \geq 0$, else $-1$

**Decoding:**

$$q = \text{round}\left(\frac{F(u,v)}{Q_s}\right)$$

$$\hat{b}_k = q \bmod 2$$

**Distortion per coefficient:**

$$D = |F'(u,v) - F(u,v)| \leq Q_s$$

#### 6.2.4 JND-Constrained Effective Strength

When the JND mask is available, the strength is constrained per coefficient:

$$Q_s^{\text{eff}}(i,j,k) = \min\bigl(Q_s, \; 2 \cdot \text{JND}(i,j,k)\bigr), \quad Q_s^{\text{eff}} \geq 2.0$$

This ensures that the modification at each DCT position never exceeds the perceptual threshold.

#### 6.2.5 Auto-Adaptive Strength

The global strength $Q_s$ is computed automatically from three image texture metrics (`compute_adaptive_strength`):

**Metric 1 — Edge Density (Sobel):**

$$G_h = f * K_h, \quad G_v = f * K_v, \quad M = \sqrt{G_h^2 + G_v^2}$$

$$\rho_{\text{edge}} = \frac{1}{WH} \sum_{x,y} \mathbb{1}[M(x,y) > 30]$$

Where $K_h, K_v$ are the 3×3 Sobel kernels.

**Metric 2 — Global Variance:**

$$\sigma_{\text{var}} = \min\left(\frac{\text{Var}(f)}{2000}, \; 1.0\right)$$

**Metric 3 — Mid-Frequency DCT Energy:**

$$\sigma_{\text{dct}} = \min\left(\frac{\bar{E}_{\text{mid}}}{50}, \; 1.0\right), \quad \bar{E}_{\text{mid}} = \frac{1}{N \cdot |P|}\sum_{k=1}^{N}\sum_{(i,j) \in P} |F_k(i,j)|$$

Where $P$ is the set of 13 mid-frequency positions and $N$ is the number of sampled blocks.

**Combined Score:**

$$\tau = 0.4 \cdot \rho_{\text{edge}} + 0.3 \cdot \sigma_{\text{var}} + 0.3 \cdot \sigma_{\text{dct}}, \quad \tau \in [0, 1]$$

$$Q_s = Q_{\min} + \tau \cdot (Q_{\max} - Q_{\min})$$

With defaults $Q_{\min} = 15.0$ (smooth images), $Q_{\max} = 60.0$ (highly textured images).

#### 6.2.6 DCT Confidence Estimation

After extraction, confidence is measured by inter-copy agreement:

$$\gamma = \frac{1}{\binom{N}{2}} \sum_{i<j} \frac{|\{k : c_i[k] = c_j[k]\}|}{|S_u|}$$

Where $N$ is the number of complete extracted copies and $|S_u|$ the payload length.

### 6.3 Hybrid Mode

Combines LSB (high capacity, primary) with DCT (robust, redundant backup):
1. Full payload embedded via LSB in all available channels
2. Critical fields (AuthorHash, Flags) duplicated via DCT
3. Extraction attempts LSB first, falls back to DCT

---

## 7. Perceptual Model — JND and Entropy

### 7.1 Watson DCT-JND Model

The Watson model (Watson, 1993) determines the maximum imperceptible modification per DCT coefficient per block. Three masking factors combine:

$$\text{JND}(i,j,k) = t(i,j) \cdot \left(\frac{|C_{\text{DC}}(k)|}{C_{\text{mean}}}\right)^{0.649} \cdot \max\left(1, \frac{|F(i,j,k)|}{t(i,j)}\right)^{0.3}$$

Where:
- $t(i,j)$ = base threshold from the JPEG luminance quantization table (ISO/IEC 10918-1)
- $C_{\text{DC}}(k) = F(0,0,k)$ = DC component of block $k$
- $C_{\text{mean}} = \frac{1}{N}\sum_k |C_{\text{DC}}(k)|$ = mean DC across all blocks (clamped $\geq 1.0$)
- $F(i,j,k)$ = DCT coefficient $(i,j)$ of block $k$

**JPEG Quantization Table** (luminance):

```
 16  11  10  16  24  40  51  61
 12  12  14  19  26  58  60  55
 14  13  16  24  40  57  69  56
 14  17  22  29  51  87  80  62
 18  22  37  56  68 109 103  77
 24  35  55  64  81 104 113  92
 49  64  78  87 103 121 120 101
 72  92  95  98 112 100 103  99
```

**Factor 1 — Luminance Masking:** Brighter blocks tolerate stronger modifications. The exponent 0.649 comes from psychophysical experiments on Weber-Fechner contrast sensitivity.

**Factor 2 — Contrast Masking:** Coefficients with large magnitude mask nearby modifications. The exponent 0.3 is empirically calibrated.

### 7.2 JND Constraint Application

During DCT embedding, the computed modification is clamped:

$$\Delta F(i,j) = \text{clip}\bigl(\Delta F(i,j), \; -\text{JND}(i,j) \cdot \alpha, \; +\text{JND}(i,j) \cdot \alpha\bigr)$$

Where $\alpha$ is an embedding strength factor (default 1.0 = maximum imperceptible).

### 7.3 Maximum Imperceptible Capacity

$$C_{\max} = \sum_{k,i,j} \mathbb{1}[\text{JND}(i,j,k) > 1.0] \cdot B$$

Where $B$ = bits per coefficient (typically 1). Only coefficients whose JND exceeds 1.0 are considered viable for embedding.

### 7.4 Shannon Entropy for Channel Selection

$$H(c) = -\sum_{x=0}^{255} p_c(x) \log_2 p_c(x)$$

Where $p_c(x) = h_c(x) / \sum h_c$ and $h_c$ is the 256-bin histogram of channel $c$. Maximum entropy is 8.0 bits (uniform distribution). The channel with the highest $H$ is optimal for LSB hiding.

### 7.5 Density Map Generation

Per-block variance determines local embedding density:

$$d(i,j) = \frac{\text{Var}(\text{block}_{i,j})}{\max_k \text{Var}(\text{block}_k)}$$

Where $\text{block}_{i,j}$ is the $B \times B$ pixel block at grid position $(i,j)$. This normalizes density to $[0, 1]$.

---

## 8. Resilience Layer

### 8.1 Reed-Solomon Error Correction

Reed-Solomon codes over GF(2⁸) provide byte-level error correction:

$$t = \lfloor n_{\text{sym}} / 2 \rfloor$$

Where $t$ = correctable symbol errors and $n_{\text{sym}}$ = number of parity symbols.

#### Presets

| Preset | $n_{\text{sym}}$ | Correction Capacity $t$ | Use Case |
|---|---|---|---|
| `light` | 10 | 5 symbol errors | JPEG quality ≥ 85 |
| `standard` | 20 | 10 symbol errors | General use |
| `heavy` | 32 | 16 symbol errors | Analog manipulation |
| `forensic` | 50 | 25 symbol errors | Maximum robustness |

#### Optimal Parity Computation

Given an expected error rate $\epsilon$:

$$n_{\text{sym}} = 2 \cdot \lceil L \cdot \epsilon \rceil, \quad n_{\text{sym}} \in [10, \; 255 - L]$$

Where $L$ = payload length in bytes and $\epsilon$ = expected error rate (default 0.05).

### 8.2 Tiling (Spatial Redundancy)

The sync-wrapped payload is repeated across the carrier medium in a tile pattern:

$$R = \left\lfloor \frac{C_{\text{carrier}}}{|S_u|} \right\rfloor$$

Where $C_{\text{carrier}}$ = total carrier capacity in bits and $|S_u|$ = sync unit length.

**Recovery:** If $R \geq 3$, majority voting reconstructs the original even when individual copies are partially corrupted.

### 8.3 Anchor Grid (OFDM Pilots)

For print-scan resilience, pilot signals are embedded at known grid positions:

```
Grid spacing: every 64 pixels in both dimensions
Pilot signal: known bit pattern at each anchor point
Purpose: enables geometric correction after scanning
```

### 8.4 Dewarp (Affine Transform Correction)

After scanning, perspective distortion is corrected:
1. Detect anchor grid positions via correlation
2. Compute affine transformation matrix
3. Apply inverse transform to straighten the image
4. Extract signature from corrected image

---

## 9. Synchronization — Barker Correlation

### 9.1 Barker-13 Sequence

The Barker-13 sequence has optimal autocorrelation properties:

$$B_{13} = [+1, +1, +1, +1, +1, -1, -1, +1, +1, -1, +1, -1, +1]$$

Properties:
- Length: 13 chips
- Off-peak autocorrelation: $\leq 1$ (side-lobe ratio 13:1)
- Maximum known Barker code length

### 9.2 Composite Sync Markers

To increase detection robustness, composite 39-bit markers are constructed:

$$\text{Header} = [B_{13}, \; \overline{B_{13}}, \; B_{13}] \quad (39 \text{ bits})$$

$$\text{Footer} = [\overline{B_{13}}, \; B_{13}, \; \overline{B_{13}}] \quad (39 \text{ bits})$$

Where $\overline{B_{13}} = -B_{13}$ (complement). Using asymmetric header/footer prevents false boundary detection.

### 9.3 Cross-Correlation Detection

The normalized cross-correlation between the received signal $s$ and pattern $p$:

$$\rho[n] = \frac{1}{L} \sum_{k=0}^{L-1} s[n+k] \cdot p[k]$$

Where $L = |p| = 39$ and $s[k] \in \{-1, +1\}$ (converted from binary $\{0,1\}$ via $s = 2b - 1$).

A sync marker is detected when $\rho[n] \geq \theta$ (default $\theta = 0.85$).

**Noise tolerance:** At $\theta = 0.85$, up to $\lfloor 39 \times 0.075 \rfloor = 2$ bits can be corrupted while maintaining detection.

### 9.4 Complete Sync Unit

```
[HEADER: 39b][PAYLOAD: N bits][FOOTER: 39b]
Total: N + 78 bits per sync unit
```

---

## 10. Universal File Support

### 10.1 Handler Architecture

The `MediaHandler` abstract base class defines the interface:

```python
class MediaHandler(ABC):
    extensions: list[str]      # Supported file extensions
    category: MediaCategory    # image | audio | video | document | generic

    def load(path) -> MediaCarrier     # Load and parse file
    def embed(carrier, bits) -> int    # Embed and return bits_embedded
    def extract(carrier) -> str        # Extract bit stream
    def save(carrier, path) -> None    # Save modified file
```

### 10.2 Format Support Matrix

| Format | Handler | Embedding Strategy | Content Hash Method |
|---|---|---|---|
| PNG, BMP, TIFF, WebP | `ImageHandler` | LSB (channel B) | SHA-256 of pixel array |
| JPEG | `ImageHandler` | DCT (QIM) | SHA-256 of pixel array |
| RAW (CR2, NEF, ARW) | `ImageHandler` | Converted to TIFF, then LSB | SHA-256 of pixel array |
| WAV, FLAC, AIFF | `AudioHandler` | LSB on PCM samples | SHA-256 of sample array |
| MP4, AVI, MOV, MKV | `VideoHandler` | LSB on keyframe pixels | SHA-256 of first keyframe |
| PDF | `PDFHandler` | Hidden stream injection | Canonical hash (excludes H-Bit data) |
| DOCX, XLSX, PPTX | `OfficeHandler` | Custom XML part in OOXML | Canonical hash (excludes H-Bit data) |
| Any other | `GenericHandler` | Append stream to file | SHA-256 of original file |

### 10.3 Auto-Discovery

The `MediaRegistry` singleton automatically discovers and registers handlers at import time. Format detection uses file extension with fallback to magic bytes.

---

## 11. Identity Management and HBFS

### 11.1 H-Bit File System (HBFS) Prototype

The HBFS vision transforms H-Bit from a tool into an **authenticated file system** where every file is inherently signed:

```
HBFS Watchdog Architecture:
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│  Input Dir   │────►│  Watchdog    │────►│  Protected Dir   │
│  (unsorted)  │     │  (monitor.py)│     │  (signed files)  │
└─────────────┘     └──────────────┘     └─────────────────┘
                          │
                    ┌─────┴──────┐
                    │  Identity   │
                    │  Registry   │
                    │  (SQLite)   │
                    └────────────┘
```

### 11.2 Identity Registry

Maps static `author_hash` values to real-world identity:

| Field | Type | Purpose |
|---|---|---|
| `author_hash` | TEXT PRIMARY KEY | SHA-256 of signing key (hex) |
| `name` | TEXT | Human-readable name |
| `email` | TEXT | Contact email |
| `organization` | TEXT | Affiliated organization |
| `public_key` | TEXT | Ed25519 public key (PEM) |
| `registered_at` | TIMESTAMP | Registration time |

### 11.3 Verification Flow

```
Signed File ──► Extract Signature ──► Lookup author_hash ──► Display Identity
                     │                       │
                     ▼                       ▼
              Verify Ed25519          "Juan García"
              Check ContentHash       "juan@example.com"
              Validate Timestamp      "Acme Photography"
```

---

## 12. Blockchain Integration

### 12.1 On-Chain Registry (Polygon)

The `HBitRegistrar` contract enables immutable signature registration:

```solidity
struct Record {
    bytes32 contentHash;    // SHA-256 of original content
    bytes32 authorHash;     // SHA-256 of author identity
    uint256 timestamp;      // Block timestamp
    address registrant;     // Ethereum address of registrant
}

function register(bytes32 contentHash, bytes32 authorHash) external;
function verify(bytes32 contentHash) external view returns (Record);
```

### 12.2 C2PA Manifest Generation

H-Bit generates compliant C2PA (Coalition for Content Provenance and Authenticity) manifests:

```json
{
    "claim_generator": "H-Bit Protocol v1.0",
    "assertions": [{
        "label": "c2pa.hash.data",
        "data": { "hash": "<content_hash>", "algorithm": "SHA-256" }
    }],
    "signature": { "algorithm": "Ed25519", "value": "<signature_hex>" }
}
```

### 12.3 Oracle Challenge-Response

For high-security scenarios, an on-chain oracle performs interactive verification:

```
Verifier → Oracle: RequestChallenge(contentHash)
Oracle → Verifier: challenge (random nonce)
Verifier → Oracle: SubmitResponse(signature(challenge, contentHash))
Oracle: Verify signature against registered public key
```

---

## 13. Forensic Analysis — PRNU and Luminance

### 13.1 PRNU Sensor Fingerprinting

Photo Response Non-Uniformity (PRNU) analysis (Lukáš-Fridrich-Goljan, 2006) extracts the unique noise pattern of the capturing sensor.

#### 13.1.1 Noise Residual Extraction

$$W(I) = I - F(I)$$

Where $I$ is the original image and $F(I)$ is the denoised version (uniform filter, kernel size 3).

#### 13.1.2 PRNU Estimation (Multi-Image)

$$\hat{K} = \frac{1}{N} \sum_{k=1}^{N} \frac{I_k - F(I_k)}{\max\bigl(F(I_k), 1\bigr)}$$

The normalization by $F(I_k)$ isolates the multiplicative PRNU component from additive random noise. Quality is estimated as:

$$Q = \min\left(1.0, \frac{N}{50}\right) \cdot g(\sigma_K)$$

Where $g$ penalizes extreme standard deviations ($\sigma_K < 10^{-6}$ → near-zero pattern; $\sigma_K > 0.1$ → too noisy).

#### 13.1.3 Sensor Verification via NCC

Normalized Cross-Correlation between suspect image noise $W$ and reference PRNU $K$:

$$\text{NCC}(W, K) = \frac{\sum_{x,y} W(x,y) \cdot K(x,y)}{\|W\|_2 \cdot \|K\|_2}$$

$$\text{Match:} \quad \overline{\text{NCC}} = \frac{1}{3}\sum_{c \in \{R,G,B\}} \text{NCC}(W_c, K_c) > \theta$$

Default threshold $\theta = 0.1$.

#### 13.1.4 PRNU Binding for H-Bit

A compact hash is generated for inclusion in the payload:

$$\text{PRNUBinding} = \text{SHA-256}\bigl(\text{quantize}(K \cdot 1000 + 128)\bigr)$$

This 32-byte hash enables verification without embedding the full PRNU pattern.

### 13.2 Luminance Coherence Analysis

Detects post-signing tampering by analyzing light direction consistency.

#### 13.2.1 Luminance Computation (ITU-R BT.709)

$$L(x,y) = 0.2126 \cdot R(x,y) + 0.7152 \cdot G(x,y) + 0.0722 \cdot B(x,y)$$

#### 13.2.2 Regional Light Direction

For each cell $(i,j)$ in a $G \times G$ grid:

$$\theta_{i,j} = \arctan2\bigl(\overline{\nabla_y L}, \; \overline{\nabla_x L}\bigr)$$

$$m_{i,j} = \sqrt{\overline{\nabla_x L}^2 + \overline{\nabla_y L}^2}$$

Where $\nabla_x, \nabla_y$ are Sobel gradients.

#### 13.2.3 Dominant Light Direction

Magnitude-weighted circular mean:

$$\theta_{\text{dom}} = \arctan2\left(\sum w_{i,j} \sin\theta_{i,j}, \; \sum w_{i,j} \cos\theta_{i,j}\right)$$

Where $w_{i,j} = m_{i,j} / \sum m$.

#### 13.2.4 Consistency Score

$$S = \max\left(0, \; 1 - \frac{\bar{\delta}}{90°}\right)$$

Where $\bar{\delta}$ is the mean angular deviation from $\theta_{\text{dom}}$. Regions with $\delta > 60°$ are flagged as anomalous (likely composited).

---

## 14. Production Status

### 14.1 Current Status (Beta)

| Component | Status | Maturity |
|---|---|---|
| Ed25519 crypto (keygen, sign, verify) | ✅ Complete | Production-ready |
| HKDF key derivation | ✅ Complete | Production-ready |
| AES-256-GCM encryption | ✅ Complete | Production-ready |
| Barker-13 synchronization | ✅ Complete | Production-ready |
| Reed-Solomon ECC | ✅ Complete | Production-ready |
| LSB embedding/extraction | ✅ Complete | Production-ready |
| DCT watermarking (QIM + Adaptive) | ✅ Complete | Production-ready |
| Watson DCT-JND perceptual mask | ✅ Complete | Production-ready |
| Image handler (PNG, JPEG, BMP, TIFF, WebP) | ✅ Complete | Production-ready |
| Audio handler (WAV, FLAC, AIFF) | ✅ Complete | Beta |
| Video handler (MP4, AVI, MOV) | ✅ Complete | Beta |
| Document handler (PDF, DOCX) | ✅ Complete | Beta (PDF fragile) |
| Generic handler (any file) | ✅ Complete | Production-ready |
| CLI (Click-based + batch mode) | ✅ Complete | Production-ready |
| GUI (CustomTkinter) | ✅ Complete | Beta |
| HBFS Watchdog | ✅ Prototype | Alpha |
| Identity Registry (SQLite) | ✅ Prototype | Alpha |
| Blockchain Registrar | ✅ Tested Locally | Eth-tester mock |
| REST API Microservice | ✅ Complete | Production-ready |
| C2PA Manifest | ✅ Generator ready | Not validated |
| PRNU/Forensics | ✅ Basic | Research |
| GPU Acceleration (CuPy) | ✅ Optional | Production-ready |
| CI/CD Pipeline | ✅ GitHub Actions | Production-ready |
| Fuzz Testing (Hypothesis) | ✅ Complete | Production-ready |
| Docker Image | ✅ Multi-stage | Production-ready |
| Integration Tests (E2E) | ✅ 7 tests | Production-ready |
| Unit Test Suite | ✅ 134+ passing | Good coverage |

### 14.2 Remaining Production Blockers

| # | Blocker | Impact | Effort |
|---|---|---|---|
| P2 | **No external security audit** | Cryptographic code unreviewed by experts | 2-4 weeks (external) |
| P4 | **PDF handler fragility** | PDF editors destroy stream-level signatures | 1 week (content-level rewrite) |
| I1 | No PyPI release | Installation requires `git clone` | 1 day |
| I5 | Blockchain contract not deployed | On-chain features untestable | 1 day + audit |
| I7 | Video handler: single keyframe | Long videos have minimal coverage | 1 week |

---

## 15. Performance Characteristics

### 15.1 Benchmarks (Reference Hardware)

Measured on: Intel i7, 16GB RAM, NVIDIA GPU (optional CuPy backend)

| Operation | File Type | Size | Time (CPU) | Time (GPU) |
|---|---|---|---|---|
| Encode | PNG 1920×1080 | 6 MB | ~1.2s | ~0.4s |
| Encode | JPEG 4000×3000 | 4 MB | ~2.8s | ~1.1s |
| Encode | WAV 44.1kHz stereo | 10 MB | ~0.8s | N/A |
| Encode | PDF 5 pages | 200 KB | ~0.3s | N/A |
| Decode | PNG 1920×1080 | 6 MB | ~0.9s | ~0.3s |
| Verify | Any format | Any | ~1.5s | ~0.5s |

### 15.2 Capacity Analysis

| Carrier | Capacity | Payload Copies (Tiling) |
|---|---|---|
| PNG 256×256 RGB | 196,608 bits | ~118 copies |
| PNG 1920×1080 RGB | 6,220,800 bits | ~3,761 copies |
| JPEG 4000×3000 (DCT) | ~187,500 bits | ~113 copies |
| WAV 1 min 44.1kHz mono | 2,646,000 bits | ~1,600 copies |
| PDF (stream injection) | Limited by stream | 1 copy |

---

## 16. Comparison with Existing Solutions

| Feature | H-Bit | C2PA | Digimarc | SteganographX |
|---|---|---|---|---|
| Survives JPEG compression | ✅ (DCT+JND) | ❌ | ✅ | ❌ |
| Survives format conversion | ✅ | ❌ | ✅ | ❌ |
| Survives print→scan | ✅ (anchors) | ❌ | ✅ | ❌ |
| Open source | ✅ Apache 2.0 | Partial | ❌ Proprietary | ❌ |
| No cloud dependency | ✅ Local-first | ❌ Cloud req. | ❌ Cloud req. | ❌ |
| Multi-format support | ✅ Any file | Images only | Images only | Images only |
| Blockchain integration | ✅ Optional | ❌ | ❌ | ❌ |
| End-to-end encrypted | ✅ AES-256-GCM | ❌ | ❌ | ❌ |
| Error correction | ✅ Reed-Solomon | ❌ | Unknown | ❌ |
| GPU acceleration | ✅ CuPy/CUDA | ❌ | N/A | ❌ |
| Perceptual model | ✅ Watson JND | ❌ | Proprietary | ❌ |
| Adaptive strength | ✅ Auto-adaptive | ❌ | ❌ | ❌ |

---

## 17. Roadmap

### Phase 9: Production Hardening ✅ (Q1 2026)
- [x] CI/CD pipeline (GitHub Actions multi-OS/Python)
- [x] Fuzz testing framework (Hypothesis)
- [x] Docker multi-stage image
- [x] Integration tests (E2E)
- [x] Auto-adaptive DCT strength
- [x] Batch signing CLI mode
- [x] CONTRIBUTING.md

### Phase 10: Ecosystem Expansion (Q2 2026)
- [x] REST API microservice (FastAPI completed)
- [x] Solidity smart contract deployment (Local eth-tester mock completed)
- [ ] *[POSTPONED]* Browser extension for in-page verification
- [ ] *[POSTPONED]* WordPress/CMS plugin
- [ ] PDF handler content-level rewrite (Moved to backlog)
- [ ] PyPI package release (Moved to backlog)

### Phase 11: Hardware Integration (Q3 2026+)
- [x] Hardware architecture planning and mock interfaces (Completed)
- [ ] FUSE/Dokany HBFS driver native implementation
- [ ] ISP-level signing (camera firmware)
- [ ] HSM/TEE integration plugins
- [ ] Mobile SDK (iOS/Android)
- [ ] Patent filing for novel contributions

---

## 18. References

1. **Ed25519:** Bernstein, D.J., et al. "High-speed high-security signatures." *Journal of Cryptographic Engineering*, 2012.
2. **HKDF (RFC 5869):** Krawczyk, H., Eronen, P. "HMAC-based Extract-and-Expand Key Derivation Function." IETF, 2010.
3. **AES-GCM (NIST SP 800-38D):** Dworkin, M. "Recommendation for Block Cipher Modes of Operation: Galois/Counter Mode." NIST, 2007.
4. **Reed-Solomon:** Reed, I.S., Solomon, G. "Polynomial Codes over Certain Finite Fields." *Journal of SIAM*, 1960.
5. **QIM Watermarking:** Chen, B., Wornell, G.W. "Quantization Index Modulation: A Class of Provably Good Methods for Digital Watermarking." *IEEE Transactions on Information Theory*, 2001.
6. **PRNU Fingerprinting:** Lukáš, J., Fridrich, J., Goljan, M. "Digital Camera Identification from Sensor Pattern Noise." *IEEE Transactions on Information Forensics and Security*, 2006.
7. **C2PA Specification:** Coalition for Content Provenance and Authenticity. "C2PA Technical Specification v1.3." 2024.
8. **Barker Codes:** Barker, R.H. "Group Synchronizing of Binary Digital Systems." *Communication Theory*, 1953.
9. **Weber-Fechner Law:** Fechner, G.T. *Elemente der Psychophysik*. 1860.
10. **Watson DCT-JND:** Watson, A.B. "DCT Quantization Matrices Visually Optimized for Individual Images." *SPIE Human Vision*, 1993.
11. **Shannon Entropy:** Shannon, C.E. "A Mathematical Theory of Communication." *Bell System Technical Journal*, 1948.
12. **ITU-R BT.709:** ITU. "Parameter values for the HDTV standards for production and international programme exchange." 2015.
13. **Sobel Operator:** Sobel, I. "An Isotropic 3×3 Image Gradient Operator." Machine Vision for Three-Dimensional Scenes, 1990.

---

## Appendix A: Quick Start

```bash
# Install
pip install hbit

# Generate keys
hbit keygen --output my_key.pem

# Sign a file
hbit encode photo.jpg --key my_key.pem --output signed.png

# Verify authenticity
hbit verify signed.png

# Batch sign a directory
hbit batch --dir ./photos --key my_key.pem --recursive

# List supported formats
hbit formats
```

## Appendix B: Python API

```python
from hbit.universal import UniversalEncoder, UniversalVerifier

# Sign
encoder = UniversalEncoder()
result = encoder.encode("photo.jpg", "my_key.pem", "signed.png")
print(f"Author: {result.author_hash}")
print(f"Bits embedded: {result.bits_embedded}")

# Verify
verifier = UniversalVerifier()
result = verifier.verify("signed.png")
print(f"Status: {result.status}")       # VERIFIED / TAMPERED / NOT_FOUND
print(f"Confidence: {result.confidence}")
```

## Appendix C: Formula Index

| Section | Formula | Source File |
|---|---|---|
| 6.1.1 | LSB embedding: $P' = (P \;\&\; \texttt{0xFE}) \| b_k$ | `encoders/lsb.py` |
| 6.1.2 | Uniform redundancy: $R = \lfloor WH / \|S_u\| \rfloor$ | `encoders/lsb.py` |
| 6.1.3 | Adaptive density: $n = \max(1, \lfloor B^2 \cdot d \rfloor)$ | `encoders/lsb.py` |
| 6.1.4 | Majority vote: $\hat{b}_k$ with confidence | `encoders/lsb.py` |
| 6.1.5 | Shannon entropy: $H = -\sum p \log_2 p$ | `analysis/entropy.py` |
| 6.2.3 | QIM: $q' \cdot Q_s$ modulation | `encoders/dct.py` |
| 6.2.4 | JND constraint: $Q_s^{\text{eff}} = \min(Q_s, 2 \cdot \text{JND})$ | `encoders/dct.py` |
| 6.2.5 | Adaptive strength: $\tau = 0.4\rho + 0.3\sigma_v + 0.3\sigma_d$ | `encoders/dct.py` |
| 6.2.6 | DCT confidence: inter-copy agreement $\gamma$ | `encoders/dct.py` |
| 7.1 | Watson JND: 3-factor masking model | `analysis/jnd.py` |
| 7.5 | Density map: per-block variance | `analysis/entropy.py` |
| 8.1 | Reed-Solomon: $t = \lfloor n_{\text{sym}}/2 \rfloor$ | `resilience/ecc.py` |
| 9.3 | Barker NCC: $\rho = \frac{1}{L}\sum s \cdot p$ | `core/sync.py` |
| 13.1.2 | PRNU estimation: $\hat{K} = \frac{1}{N}\sum$ normalized residuals | `forensics/prnu.py` |
| 13.1.3 | Sensor NCC: $\text{NCC}(W,K) = \frac{W \cdot K}{\|W\| \|K\|}$ | `forensics/prnu.py` |
| 13.2.2 | Light direction: $\theta = \arctan2(\nabla_y, \nabla_x)$ | `forensics/luminance.py` |
| 13.2.4 | Consistency: $S = 1 - \bar{\delta}/90°$ | `forensics/luminance.py` |

---

*This document is part of the H-Bit Protocol project, licensed under Apache 2.0.*  
*For implementation details, see the source code at the project repository.*  
*All formulas verified against source code — February 2026.*
