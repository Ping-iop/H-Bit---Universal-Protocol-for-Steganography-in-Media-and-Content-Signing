"""
H-Bit Benchmark Suite — Métricas cuantitativas de rendimiento y robustez.

Mide:
- PSNR (Peak Signal-to-Noise Ratio): degradación visual tras embedding
- SSIM (Structural Similarity): calidad perceptual
- Velocidad de encode/decode
- Resistencia a compresión JPEG (quality 10-100)
- Resistencia a cropping (altura 5%-100%)
- Resistencia a resizing
- Confianza espectral en cada escenario
"""

import json
import time
import sys
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

import numpy as np
from PIL import Image, ImageFilter

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from hbit.core.crypto import generate_key_pair
from hbit.universal import UniversalEncoder, UniversalDecoder, UniversalVerifier
from hbit.analysis.spectrum import SpectrumVerifier
from hbit.formats.base import MediaRegistry


# ═══════════════════════════════════════════════════════════════════
# Métricas de calidad (implementación manual, sin scikit-image)
# ═══════════════════════════════════════════════════════════════════

def compute_psnr(original: np.ndarray, modified: np.ndarray) -> float:
    """Peak Signal-to-Noise Ratio (dB). Mayor = mejor calidad."""
    mse = np.mean((original.astype(np.float64) - modified.astype(np.float64)) ** 2)
    if mse == 0:
        return float("inf")
    return float(20 * np.log10(255.0 / np.sqrt(mse)))


def compute_ssim(original: np.ndarray, modified: np.ndarray) -> float:
    """Structural Similarity Index (0-1). Mayor = más similar."""
    C1 = (0.01 * 255) ** 2
    C2 = (0.03 * 255) ** 2

    orig = original.astype(np.float64)
    mod = modified.astype(np.float64)

    mu1 = orig.mean()
    mu2 = mod.mean()
    sigma1_sq = orig.var()
    sigma2_sq = mod.var()
    sigma12 = np.mean((orig - mu1) * (mod - mu2))

    ssim_val = ((2 * mu1 * mu2 + C1) * (2 * sigma12 + C2)) / (
        (mu1**2 + mu2**2 + C1) * (sigma1_sq + sigma2_sq + C2)
    )
    return float(np.clip(ssim_val, 0.0, 1.0))


# ═══════════════════════════════════════════════════════════════════
# Data classes
# ═══════════════════════════════════════════════════════════════════

@dataclass
class QualityMetrics:
    psnr_db: float
    ssim: float
    bits_embedded: int
    capacity_used: float


@dataclass
class SpeedMetrics:
    encode_time_ms: float
    decode_time_ms: float
    spectrum_time_ms: float
    file_size_original_bytes: int
    file_size_signed_bytes: int


@dataclass
class RobustnessResult:
    test_name: str
    parameter: str
    spectrum_verdict: str
    spectrum_confidence: float
    tiles_recovered: int
    tiles_valid: int


@dataclass
class BenchmarkReport:
    image_size: str
    format: str
    quality: QualityMetrics
    speed: SpeedMetrics
    jpeg_robustness: list[RobustnessResult] = field(default_factory=list)
    crop_robustness: list[RobustnessResult] = field(default_factory=list)
    resize_robustness: list[RobustnessResult] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════
# Benchmark engine
# ═══════════════════════════════════════════════════════════════════

class HBitBenchmark:
    def __init__(self, output_dir: Path = None):
        self.output_dir = output_dir or Path("/tmp/hbit_benchmarks")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._keypair = generate_key_pair()
        self._verifier = SpectrumVerifier()

    def run(self, image_size: tuple = (512, 512)) -> BenchmarkReport:
        """Ejecuta todos los benchmarks."""
        w, h = image_size
        report = BenchmarkReport(
            image_size=f"{w}×{h}",
            format="PNG",
            quality=None,
            speed=None,
        )

        print(f"\n{'='*60}")
        print(f"  H-Bit Benchmark Suite — {w}×{h} PNG")
        print(f"{'='*60}")

        # Crear imagen de prueba
        rng = np.random.default_rng(42)
        original = rng.integers(0, 256, (h, w, 3), dtype=np.uint8)
        orig_path = self.output_dir / "original.png"
        Image.fromarray(original).save(orig_path)

        # 1. Quality metrics
        print("\n📊 Calidad de Embedding:")
        report.quality = self._bench_quality(original, orig_path)
        print(f"   PSNR: {report.quality.psnr_db:.1f} dB")
        print(f"   SSIM: {report.quality.ssim:.4f}")
        print(f"   Bits: {report.quality.bits_embedded}")
        print(f"   Capacidad: {report.quality.capacity_used:.1%}")

        # 2. Speed metrics
        print("\n⚡ Velocidad:")
        report.speed = self._bench_speed(orig_path)
        print(f"   Encode: {report.speed.encode_time_ms:.1f} ms")
        print(f"   Decode: {report.speed.decode_time_ms:.1f} ms")
        print(f"   Spectrum: {report.speed.spectrum_time_ms:.1f} ms")

        # 3. JPEG robustness
        print("\n🔄 Robustez JPEG:")
        report.jpeg_robustness = self._bench_jpeg_robustness(
            orig_path, original
        )
        for r in report.jpeg_robustness:
            status = "✅" if r.spectrum_confidence > 0.5 else "❌"
            print(f"   {status} Q{r.parameter:>3}: {r.spectrum_verdict:20s} {r.spectrum_confidence:.0%} ({r.tiles_valid}/{r.tiles_recovered} tiles)")

        # 4. Crop robustness (height-based, same width)
        print("\n✂️  Robustez Crop (filas):")
        report.crop_robustness = self._bench_crop_robustness(
            orig_path, original
        )
        for r in report.crop_robustness:
            status = "✅" if r.spectrum_confidence > 0.5 else "❌"
            print(f"   {status} {r.parameter:>6}: {r.spectrum_verdict:20s} {r.spectrum_confidence:.0%} ({r.tiles_valid}/{r.tiles_recovered} tiles)")

        # 5. Resize robustness
        print("\n🔍 Robustez Resize:")
        report.resize_robustness = self._bench_resize_robustness(
            orig_path, original
        )
        for r in report.resize_robustness:
            status = "✅" if r.spectrum_confidence > 0.5 else "❌"
            conf = r.spectrum_confidence
            print(f"   {status} {r.parameter:>6}: {r.spectrum_verdict:20s} {conf:.0%}")

        print(f"\n{'='*60}")
        print(f"  Benchmark completo. Datos en: {self.output_dir}")
        print(f"{'='*60}\n")

        return report

    def _bench_quality(
        self, original: np.ndarray, orig_path: Path
    ) -> QualityMetrics:
        signed_path = self.output_dir / "signed_quality.png"
        encoder = UniversalEncoder(use_kdf=False)
        result = encoder.encode(orig_path, self._keypair, signed_path)

        signed_img = np.array(Image.open(signed_path))
        psnr = compute_psnr(original, signed_img)
        ssim = compute_ssim(original, signed_img)

        return QualityMetrics(
            psnr_db=psnr,
            ssim=ssim,
            bits_embedded=result.bits_embedded,
            capacity_used=result.capacity_used,
        )

    def _bench_speed(self, orig_path: Path) -> SpeedMetrics:
        signed_path = self.output_dir / "signed_speed.png"

        # Encode speed
        t0 = time.perf_counter()
        encoder = UniversalEncoder(use_kdf=False)
        for _ in range(5):
            encoder.encode(orig_path, self._keypair, signed_path)
        encode_time = (time.perf_counter() - t0) / 5 * 1000

        # Decode speed
        t0 = time.perf_counter()
        decoder = UniversalDecoder()
        for _ in range(5):
            decoder.decode(signed_path)
        decode_time = (time.perf_counter() - t0) / 5 * 1000

        # Spectrum speed
        t0 = time.perf_counter()
        MediaRegistry.reset()
        verifier = SpectrumVerifier()
        for _ in range(3):
            verifier.analyze(signed_path)
        spectrum_time = (time.perf_counter() - t0) / 3 * 1000

        orig_size = orig_path.stat().st_size
        signed_size = signed_path.stat().st_size

        return SpeedMetrics(
            encode_time_ms=encode_time,
            decode_time_ms=decode_time,
            spectrum_time_ms=spectrum_time,
            file_size_original_bytes=orig_size,
            file_size_signed_bytes=signed_size,
        )

    def _bench_jpeg_robustness(
        self, orig_path: Path, original: np.ndarray
    ) -> list[RobustnessResult]:
        results = []
        signed_path = self.output_dir / "signed_jpeg_test.png"
        encoder = UniversalEncoder(use_kdf=False)
        encoder.encode(orig_path, self._keypair, signed_path)

        signed_img = Image.open(signed_path)

        for quality in [100, 95, 90, 80, 70, 60, 50, 30, 10]:
            jpeg_path = self.output_dir / f"jpeg_q{quality}.jpg"
            signed_img.save(jpeg_path, "JPEG", quality=quality)

            try:
                MediaRegistry.reset()
                result = self._verifier.analyze(jpeg_path)
                results.append(RobustnessResult(
                    test_name="jpeg_compression",
                    parameter=str(quality),
                    spectrum_verdict=result.verdict,
                    spectrum_confidence=result.confidence,
                    tiles_recovered=result.tiles_total,
                    tiles_valid=result.payloads_valid,
                ))
            except Exception as e:
                results.append(RobustnessResult(
                    test_name="jpeg_compression",
                    parameter=str(quality),
                    spectrum_verdict="ERROR",
                    spectrum_confidence=0.0,
                    tiles_recovered=0,
                    tiles_valid=0,
                ))

        return results

    def _bench_crop_robustness(
        self, orig_path: Path, original: np.ndarray
    ) -> list[RobustnessResult]:
        results = []
        signed_path = self.output_dir / "signed_crop_test.png"
        encoder = UniversalEncoder(use_kdf=False)
        encoder.encode(orig_path, self._keypair, signed_path)

        signed_data = np.array(Image.open(signed_path))
        h, w = signed_data.shape[:2]

        for pct in [100, 75, 50, 25, 12, 6, 3]:
            rows = max(1, int(h * pct / 100))
            crop_data = signed_data[:rows, :, :]
            crop_path = self.output_dir / f"crop_{pct}pct.png"
            Image.fromarray(crop_data).save(crop_path)

            try:
                MediaRegistry.reset()
                result = self._verifier.analyze(crop_path)
                results.append(RobustnessResult(
                    test_name="crop_height",
                    parameter=f"{pct}% ({rows}px)",
                    spectrum_verdict=result.verdict,
                    spectrum_confidence=result.confidence,
                    tiles_recovered=result.tiles_total,
                    tiles_valid=result.payloads_valid,
                ))
            except Exception as e:
                results.append(RobustnessResult(
                    test_name="crop_height",
                    parameter=f"{pct}% ({rows}px)",
                    spectrum_verdict="ERROR",
                    spectrum_confidence=0.0,
                    tiles_recovered=0,
                    tiles_valid=0,
                ))

        return results

    def _bench_resize_robustness(
        self, orig_path: Path, original: np.ndarray
    ) -> list[RobustnessResult]:
        results = []
        signed_path = self.output_dir / "signed_resize_test.png"
        encoder = UniversalEncoder(use_kdf=False)
        encoder.encode(orig_path, self._keypair, signed_path)

        signed_img = Image.open(signed_path)
        orig_w, orig_h = signed_img.size

        for scale in [1.0, 0.9, 0.75, 0.5, 0.25]:
            new_w = max(1, int(orig_w * scale))
            new_h = max(1, int(orig_h * scale))
            resized = signed_img.resize((new_w, new_h), Image.LANCZOS)
            resize_path = self.output_dir / f"resize_{int(scale*100)}pct.png"
            resized.save(resize_path)

            try:
                MediaRegistry.reset()
                result = self._verifier.analyze(resize_path)
                results.append(RobustnessResult(
                    test_name="resize",
                    parameter=f"{int(scale*100)}% ({new_w}×{new_h})",
                    spectrum_verdict=result.verdict,
                    spectrum_confidence=result.confidence,
                    tiles_recovered=result.tiles_total,
                    tiles_valid=result.payloads_valid,
                ))
            except Exception as e:
                results.append(RobustnessResult(
                    test_name="resize",
                    parameter=f"{int(scale*100)}%",
                    spectrum_verdict="ERROR",
                    spectrum_confidence=0.0,
                    tiles_recovered=0,
                    tiles_valid=0,
                ))

        return results


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    bench = HBitBenchmark()
    report = bench.run(image_size=(512, 512))

    # Guardar reporte JSON
    report_path = bench.output_dir / "benchmark_report.json"
    report_dict = asdict(report)
    report_path.write_text(json.dumps(report_dict, indent=2, default=str))
    print(f"\n📄 Reporte JSON: {report_path}")

    # Guardar también como markdown
    md = f"""# H-Bit Benchmark Report

## Image: {report.image_size} {report.format}

### Quality
| Metric | Value |
|--------|-------|
| PSNR | {report.quality.psnr_db:.1f} dB |
| SSIM | {report.quality.ssim:.4f} |
| Bits Embedded | {report.quality.bits_embedded} |
| Capacity Used | {report.quality.capacity_used:.1%} |

### Speed
| Operation | Time |
|-----------|------|
| Encode | {report.speed.encode_time_ms:.1f} ms |
| Decode | {report.speed.decode_time_ms:.1f} ms |
| Spectrum | {report.speed.spectrum_time_ms:.1f} ms |
| File Size (orig) | {report.speed.file_size_original_bytes:,} bytes |
| File Size (signed) | {report.speed.file_size_signed_bytes:,} bytes |

### JPEG Robustness
| Quality | Verdict | Confidence | Tiles |
|---------|---------|------------|-------|
"""
    for r in report.jpeg_robustness:
        md += f"| {r.parameter} | {r.spectrum_verdict} | {r.spectrum_confidence:.1%} | {r.tiles_valid}/{r.tiles_recovered} |\n"

    md += "\n### Crop Robustness (height %, same width)\n"
    md += "| Crop | Verdict | Confidence | Tiles |\n"
    md += "|------|---------|------------|-------|\n"
    for r in report.crop_robustness:
        md += f"| {r.parameter} | {r.spectrum_verdict} | {r.spectrum_confidence:.1%} | {r.tiles_valid}/{r.tiles_recovered} |\n"

    md += "\n### Resize Robustness\n"
    md += "| Scale | Verdict | Confidence | Tiles |\n"
    md += "|-------|---------|------------|-------|\n"
    for r in report.resize_robustness:
        md += f"| {r.parameter} | {r.spectrum_verdict} | {r.spectrum_confidence:.1%} | {r.tiles_valid}/{r.tiles_recovered} |\n"

    md_path = bench.output_dir / "benchmark_report.md"
    md_path.write_text(md)
    print(f"📄 Reporte Markdown: {md_path}")
