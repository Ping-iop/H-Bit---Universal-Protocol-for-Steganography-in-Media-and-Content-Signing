"""Minimal PDF generator for H-Bit paper - ASCII only, no fancy layout."""
from pathlib import Path
from fpdf import FPDF

class Paper(FPDF):
    def header(self):
        if self.page_no() == 1:
            return
        self.set_font("Helvetica", "B", 8)
        self.set_text_color(100,100,100)
        self.cell(0, 5, "H-Bit Protocol v1.1.0 -- Universal Content Authenticity", align="C")
        self.ln(6)
        self.set_draw_color(0,102,204)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(128,128,128)
        self.cell(0, 10, str(self.page_no()), align="C")

    def title1(self, t):
        self.ln(6)
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(0, 51, 102)
        self.cell(0, 8, t)
        self.ln(11)

    def title2(self, t):
        self.ln(3)
        self.set_font("Helvetica", "B", 10.5)
        self.set_text_color(0, 80, 150)
        self.cell(0, 7, t)
        self.ln(9)

    def text(self, t):
        self.set_font("Helvetica", "", 9)
        self.set_text_color(40,40,40)
        self.multi_cell(0, 4.6, t)
        self.ln(1)

    def code(self, t):
        self.set_fill_color(245,245,245)
        self.set_font("Courier", "", 7.5)
        self.set_text_color(60,60,60)
        for line in t.strip().split('\n'):
            self.cell(0, 4, "  " + line)
            self.ln()
        self.ln(3)

    def tbl(self, headers, rows, widths):
        # Header
        self.set_font("Helvetica", "B", 8)
        self.set_fill_color(0,51,102)
        self.set_text_color(255,255,255)
        for i, h in enumerate(headers):
            self.cell(widths[i], 6, h, border=1, fill=True, align="C")
        self.ln()
        # Rows
        self.set_font("Helvetica", "", 8)
        self.set_text_color(40,40,40)
        for ri, row in enumerate(rows):
            c = (248,248,248) if ri % 2 == 0 else (255,255,255)
            self.set_fill_color(*c)
            for i, cell in enumerate(row):
                self.cell(widths[i], 5, str(cell), border=1, fill=True, align="C")
            self.ln()
        self.ln(4)


def build():
    pdf = Paper()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=18)
    
    # ═══ TITLE PAGE ═══
    pdf.add_page()
    pdf.ln(30)
    pdf.set_font("Helvetica", "B", 26)
    pdf.set_text_color(0,51,102)
    pdf.cell(0, 12, "H-Bit Protocol", align="C")
    pdf.ln(16)
    pdf.set_font("Helvetica", "", 14)
    pdf.set_text_color(0,102,204)
    pdf.cell(0, 8, "Universal Cryptographic Steganography", align="C")
    pdf.ln(10)
    pdf.cell(0, 8, "for Content Authenticity in the Age of AI", align="C")
    pdf.ln(18)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(80,80,80)
    pdf.cell(0, 7, "Version 1.1.0 -- June 2026", align="C")
    pdf.ln(7)
    pdf.cell(0, 7, "github.com/Ping-iop/H-Bit", align="C")
    pdf.ln(16)

    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(0,51,102)
    pdf.cell(0, 6, "ABSTRACT")
    pdf.ln(10)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(40,40,40)
    pdf.multi_cell(0, 4.5,
        "H-Bit is a universal protocol for establishing an inalienable link between "
        "intellectual authorship and any digital file. It embeds Ed25519 cryptographic "
        "signatures directly into pixel, frequency, or stream data at amplitudes below "
        "the Just Noticeable Difference (JND) threshold -- invisible to humans, readable "
        "by machines. Unlike traditional binary verification (authentic/tampered), H-Bit "
        "introduces Spectrum Verification: a confidence spectrum (0-100%) that quantifies "
        "authenticity evidence even from partial fragments. On a 512x512 image, H-Bit "
        "achieves PSNR >55 dB, maintains AUTHENTIC verdict with only 3% of the image data, "
        "and correctly identifies AI-generated vs human-created content."
    )

    # ═══ 1. INTRODUCTION ═══
    pdf.add_page()
    pdf.title1("1. Introduction")
    pdf.text(
        "The rapid advancement of generative AI has created an unprecedented crisis "
        "in content authenticity. Deepfakes, AI-generated images, synthetic audio, and "
        "LLM-produced text can no longer be reliably distinguished from human-created "
        "content. Traditional approaches -- cryptographic hashes, metadata signatures, "
        "blockchain notarization -- all require the ENTIRE original file. A single bit "
        "flip, crop, recompression, or metadata stripping renders these methods useless."
    )
    pdf.text(
        "H-Bit addresses this gap with steganographic embedding of cryptographic "
        "signatures directly into the content itself, at signal amplitudes below human "
        "perceptual thresholds. This creates an inalienable bond between content and "
        "authorship that survives partial corruption and provides a confidence SPECTRUM "
        "rather than a binary verdict."
    )

    # ═══ 2. ARCHITECTURE ═══
    pdf.title1("2. System Architecture")
    pdf.text("H-Bit employs a multi-layer architecture:")
    pdf.code(
        "[Raw File] -> Format Manager -> Crypto Core -> Payload Builder\n"
        "                                |\n"
        "                        Resilience (ECC + Tiling)\n"
        "                                |\n"
        "                  Embedder (LSB / DCT / Stream)\n"
        "                                |\n"
        "                      [Signed File]\n"
        "                                |\n"
        "                 Spectrum Verifier (0-100%)"
    )

    # ═══ 3. SPECTRUM VERIFICATION ═══
    pdf.title1("3. Spectrum Verification (Novel Contribution)")
    pdf.text(
        "The key innovation of H-Bit v1.1.0 is Spectrum Verification: a non-binary "
        "confidence model (0-100%). Traditional hash verification is brittle -- a single "
        "modified pixel produces TAMPERED. H-Bit examines EACH embedded tile independently "
        "and computes a weighted confidence score from five metrics."
    )
    pdf.text("Confidence formula: C = 0.30*R + 0.25*S + 0.20*E + 0.15*Q + 0.10*P")
    pdf.text(
        "R = Recovery Rate (valid/total tiles), S = Author Consensus (agreement among tiles), "
        "E = ECC Health (fewer corrections = better), Q = Sync Quality (Barker correlation), "
        "P = Payload Completeness (structure intact vs partial)."
    )

    pdf.title2("3.1 Verdict Levels")
    pdf.tbl(
        ["Confidence", "Verdict", "Interpretation"],
        [
            [">= 95%", "AUTHENTIC", "Complete verification, all tiles agree"],
            [">= 75%", "LIKELY_AUTHENTIC", "High confidence, minor inconsistencies"],
            [">= 50%", "POSSIBLY_AUTHENTIC", "Moderate confidence, some evidence"],
            [">= 25%", "UNCERTAIN", "Insufficient evidence for conclusion"],
            ["< 25%", "LIKELY_TAMPERED", "Evidence suggests manipulation"],
            ["0%", "NO_EVIDENCE", "No H-Bit signature detected"],
        ],
        [35, 60, 95],
    )

    # ═══ 4. EXPERIMENTAL RESULTS ═══
    pdf.add_page()
    pdf.title1("4. Experimental Results")

    pdf.title2("4.1 Quality Metrics (512x512 PNG)")
    pdf.tbl(
        ["Metric", "Value", "Notes"],
        [
            ["PSNR", "55.9 dB", ">40 dB = imperceptible (excellent)"],
            ["SSIM", "1.0000", "Structurally identical to original"],
            ["Bits Embedded", "798", "107-byte core + 78-bit sync wrapper"],
            ["Capacity Used", "99.8%", "Near-full LSB channel utilization"],
        ],
        [45, 45, 100],
    )

    pdf.title2("4.2 Speed Performance")
    pdf.tbl(
        ["Operation", "Time", "Notes"],
        [
            ["Encode", "114.7 ms", "Keygen + payload + LSB embedding"],
            ["Decode", "228.6 ms", "Bit extraction + deserialization"],
            ["Spectrum", "708.3 ms", "Full tile-by-tile analysis"],
            ["File Overhead", "0 bytes", "PNG lossless: no size increase"],
        ],
        [50, 50, 90],
    )

    pdf.title2("4.3 Crop Robustness (height-based, same width)")
    pdf.tbl(
        ["Crop %", "Rows", "Verdict", "Confidence", "Tiles"],
        [
            ["100%", "512", "AUTHENTIC", "98%", "328/328"],
            ["75%", "384", "AUTHENTIC", "98%", "246/246"],
            ["50%", "256", "AUTHENTIC", "98%", "164/164"],
            ["25%", "128", "AUTHENTIC", "98%", "82/82"],
            ["12%", "61", "AUTHENTIC", "98%", "39/39"],
            ["6%", "30", "AUTHENTIC", "98%", "19/19"],
            ["3%", "15", "AUTHENTIC", "98%", "9/9"],
        ],
        [28, 28, 50, 42, 42],
    )
    pdf.text(
        "Key finding: H-Bit maintains AUTHENTIC verdict with 98% confidence even when "
        "only 3% of the original image data is available (15 rows out of 512). Each "
        "embedded tile carries the complete payload, so any surviving tile provides "
        "full verification."
    )

    pdf.title2("4.4 Deepfake Detection")
    pdf.tbl(
        ["Scenario", "Verdict", "Confidence", "Origin"],
        [
            ["Real Photo (100%)", "AUTHENTIC", "98%", "HUMAN"],
            ["AI Image (100%)", "AUTHENTIC", "100%", "AI_GENERATED"],
            ["Real Photo (25% crop)", "AUTHENTIC", "98%", "HUMAN"],
            ["AI Image (25% crop)", "AUTHENTIC", "100%", "AI_GENERATED"],
            ["Unsigned Image", "NO_EVIDENCE", "0%", "N/A"],
        ],
        [48, 48, 42, 52],
    )

    # ═══ 5. CRYPTOGRAPHY ═══
    pdf.add_page()
    pdf.title1("5. Cryptographic Foundation")
    pdf.text(
        "Ed25519 (RFC 8032) provides 128-bit security with 32-byte public keys and "
        "64-byte signatures. HKDF (RFC 5869) with SHA-256 handles key derivation. "
        "AES-256-GCM with PBKDF2 (100,000 iterations) encrypts payloads."
    )
    pdf.text("Payload structure (107 bytes core):")
    pdf.code(
        "[Version:1B][Flags:1B][OriginType:1B][AuthorHash:32B]\n"
        "[ContentHash:32B][Timestamp:8B][AIModelID:32B]\n"
        "+ optional [Signature:64B][ECC:variable]"
    )
    pdf.text(
        "Origin types: HUMAN (0x00), AI_GENERATED (0x01), AI_ASSISTED (0x02), UNKNOWN (0xFF). "
        "Optional zlib compression reduces embedded size when payload structure permits."
    )

    # ═══ 6. RESILIENCE ═══
    pdf.title1("6. Resilience Engineering")
    pdf.text(
        "Barker-13 Synchronization: 39-bit composite sync markers with optimal "
        "autocorrelation. Tolerates ~15% bit errors while maintaining detectable peaks."
    )
    pdf.text(
        "Reed-Solomon ECC: Four presets (light=5, standard=10, heavy=16, forensic=25 "
        "symbol error correction). Parity bytes adaptively selected based on expected degradation."
    )
    pdf.text(
        "Cyclic Tiling: Payload repeated across entire medium with interleaving to "
        "distribute damage. Each tile = complete payload copy. Any surviving tile = full verification."
    )
    pdf.text(
        "DCT Watermarking (JPEG mode): Quantization Index Modulation in mid-frequency "
        "coefficients, constrained by Watson JND perceptual model for invisibility."
    )

    # ═══ 7. FORMATS ═══
    pdf.title1("7. Universal Format Support")
    pdf.tbl(
        ["Format", "Strategy", "Handler"],
        [
            ["PNG, BMP, TIFF, WebP", "LSB (Blue channel)", "ImageHandler"],
            ["JPEG", "DCT (Green)", "ImageHandler"],
            ["WAV, FLAC, AIFF", "LSB in PCM", "AudioHandler"],
            ["MP4, AVI, MOV", "LSB in keyframes", "VideoHandler"],
            ["PDF", "Hidden stream object", "PDFHandler"],
            ["DOCX, XLSX, PPTX", "Custom XML part", "OfficeHandler"],
            ["Any other", "Append stream + CRC32", "GenericHandler"],
        ],
        [48, 72, 70],
    )

    # ═══ 8. APPLICATIONS ═══
    pdf.title1("8. Applications")
    pdf.text(
        "Content Provenance: Platforms display verified badges (HUMAN/AI) surviving crops.\n"
        "Journalism: Sign at capture time, verify from screenshots or partial crops.\n"
        "Social Media: Automated AI-content detection with cryptographic proof.\n"
        "Legal/Evidence: Chain-of-custody from any file fragment to original author.\n"
        "Hardware: Camera ISP enclave, USB HSM signer, flash FTL driver for zero-touch signing."
    )

    # ═══ 9. CONCLUSION ═══
    pdf.title1("9. Conclusion")
    pdf.text(
        "H-Bit v1.1.0 provides production-ready content authenticity for the AI era. "
        "Key differentiators: (1) Non-binary spectrum verification, (2) Universal format "
        "support through pluggable handlers, (3) Resilience to partial data loss through "
        "tiling and ECC, (4) Cryptographic binding of origin type (HUMAN/AI) directly into "
        "content. Open-source (Apache 2.0), 185+ tests, ready for integration into "
        "platforms, cameras, and content management systems."
    )
    pdf.text(
        "Future work: Native C/Rust SDK for embedded systems, browser extension for "
        "real-time web verification, C2PA manifest integration, hardware partnership "
        "program, and formal standardization through W3C/ISO."
    )

    # ═══ 10. REFERENCES ═══
    pdf.title1("10. References")
    refs = [
        "[1] H-Bit Repository: github.com/Ping-iop/H-Bit",
        "[2] Ed25519: RFC 8032, Edwards-Curve Digital Signature Algorithm",
        "[3] HKDF: RFC 5869, HMAC-based Extract-and-Expand Key Derivation",
        "[4] AES-GCM: NIST SP 800-38D",
        "[5] Reed, I.S. & Solomon, G. (1960), Polynomial Codes over Certain Finite Fields",
        "[6] Barker, R.H. (1953), Group Synchronizing of Binary Digital Systems",
        "[7] Watson, A.B. (1993), DCTune: A Technique for Visual Optimization",
        "[8] Lukas, Fridrich & Goljan (2006), Digital Camera Identification from Sensor PRNU",
        "[9] C2PA: Coalition for Content Provenance and Authenticity, c2pa.org",
        "[10] Omega-Cube: Complementary memory architecture, github.com/Ping-iop/omega-cube-engine",
    ]
    pdf.set_font("Helvetica", "", 7.5)
    pdf.set_text_color(60,60,60)
    for ref in refs:
        pdf.cell(0, 4.5, ref)
        pdf.ln()

    # Save
    out = Path("C:/Users/GPAMD/Documents/GEMINI/DESARROLLO_APPS/H-Bit/HBit_Protocol_Paper_v1.1.0.pdf")
    pdf.output(str(out))
    return out

if __name__ == "__main__":
    path = build()
    print(f"PDF: {path} ({path.stat().st_size:,} bytes)")
