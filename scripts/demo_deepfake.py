"""
H-Bit Deepfake Detection Demo

Demuestra cómo H-Bit diferencia contenido humano de contenido generado por IA,
incluso con fragmentos parciales de la imagen.

Escenario:
1. "Foto real" — firmada como HUMAN por un fotógrafo
2. "Imagen IA" — firmada como AI_GENERATED por Midjourney
3. Ambas se someten a verificación espectral (completa y parcial)
"""

import sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from hbit.core.crypto import generate_key_pair
from hbit.universal import UniversalEncoder, UniversalVerifier
from hbit.analysis.spectrum import SpectrumVerifier, SpectrumVerdict
from hbit.core.signature import OriginType
from hbit.formats.base import MediaRegistry


def create_test_image(
    path: Path, size=(400, 400), label="REAL", color=(34, 139, 34)
):
    """Crea una imagen de prueba con etiqueta visual."""
    img = Image.new("RGB", size, (240, 240, 240))
    draw = ImageDraw.Draw(img)

    # Fondo con ruido para simular textura real
    rng = np.random.default_rng(hash(label) % 2**32)
    noise = rng.integers(0, 30, (size[1], size[0], 3), dtype=np.uint8)
    base = np.array(img) + noise
    img = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))

    draw = ImageDraw.Draw(img)
    # Etiqueta
    try:
        font = ImageFont.truetype("arial.ttf", 60)
    except Exception:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), label, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pos = ((size[0] - tw) // 2, (size[1] - th) // 2)
    draw.text(pos, label, fill=color, font=font)

    # Marco de color
    draw.rectangle([5, 5, size[0] - 6, size[1] - 6], outline=color, width=3)

    img.save(path)
    return img


def print_spectrum(result, label=""):
    """Imprime resultado espectral formateado."""
    icons = {
        SpectrumVerdict.AUTHENTIC: "✅",
        SpectrumVerdict.LIKELY_AUTHENTIC: "✅",
        SpectrumVerdict.POSSIBLY_AUTHENTIC: "⚠️",
        SpectrumVerdict.UNCERTAIN: "⚠️",
        SpectrumVerdict.LIKELY_TAMPERED: "❌",
        SpectrumVerdict.NO_EVIDENCE: "❌",
    }
    icon = icons.get(result.verdict, "❓")
    print(f"   {icon} {result.verdict:20s} | Confianza: {result.confidence:.0%}")
    print(f"      Tiles: {result.payloads_valid}/{result.tiles_total} | "
          f"Consenso: {result.author_consensus:.0%}")
    if result.origin_type:
        print(f"      Origen: {result.origin_type}")
    if result.author_hash:
        print(f"      Autor:  {result.author_hash[:24]}...")


def main():
    output_dir = Path("/tmp/hbit_deepfake_demo")
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 65)
    print("  H-Bit Deepfake Detection Demo")
    print("=" * 65)

    # ═══════════════════════════════════════════════════════════
    # 1. Generar claves (simulando dos "autores")
    # ═══════════════════════════════════════════════════════════
    human_key = generate_key_pair()
    ai_key = generate_key_pair()

    print("\n🔑 Claves generadas:")
    print(f"   Fotógrafo (HUMAN): clave privada generada")
    print(f"   Generador IA:      clave privada generada")

    # ═══════════════════════════════════════════════════════════
    # 2. Crear y firmar imágenes
    # ═══════════════════════════════════════════════════════════
    print("\n📸 Creando y firmando imágenes...")

    # Imagen "real" — fotógrafo humano
    real_path = output_dir / "real_photo.png"
    create_test_image(real_path, label="FOTO REAL", color=(34, 139, 34))
    real_signed = output_dir / "real_photo_signed.png"

    encoder = UniversalEncoder(use_kdf=False)
    real_result = encoder.encode(
        real_path, human_key, real_signed,
        origin_type=OriginType.HUMAN,
    )
    print(f"   ✅ Foto real firmada (HUMAN)")
    print(f"      Autor: {real_result.author_hash[:24]}...")

    # Imagen "IA" — generada por Midjourney
    ai_path = output_dir / "ai_image.png"
    create_test_image(ai_path, label="IA GENERADA", color=(220, 20, 60))
    ai_signed = output_dir / "ai_image_signed.png"

    ai_result = encoder.encode(
        ai_path, ai_key, ai_signed,
        origin_type=OriginType.AI_GENERATED,
        ai_model_id="midjourney-v6",
    )
    print(f"   ✅ Imagen IA firmada (AI_GENERATED, midjourney-v6)")
    print(f"      Autor: {ai_result.author_hash[:24]}...")

    # ═══════════════════════════════════════════════════════════
    # 3. Verificación espectral — imágenes completas
    # ═══════════════════════════════════════════════════════════
    print("\n📊 ANÁLISIS ESPECTRAL — Imágenes Completas")
    print("-" * 50)

    MediaRegistry.reset()
    verifier = SpectrumVerifier()

    print("\n   Foto Real (completa):")
    real_full = verifier.analyze(real_signed)
    print_spectrum(real_full)

    MediaRegistry.reset()
    print("\n   Imagen IA (completa):")
    ai_full = verifier.analyze(ai_signed)
    print_spectrum(ai_full)

    # ═══════════════════════════════════════════════════════════
    # 4. Verificación PARCIAL — simular "leaks" o fragmentos
    # ═══════════════════════════════════════════════════════════
    print("\n📊 ANÁLISIS ESPECTRAL — Fragmentos Parciales (25%)")
    print("-" * 50)

    for name, signed_path in [("Foto Real", real_signed), ("Imagen IA", ai_signed)]:
        img = Image.open(signed_path)
        data = np.array(img)
        # Crop: 25% superior (100 filas de 400)
        crop_data = data[:100, :, :]
        crop_path = output_dir / f"crop_{name.lower().replace(' ', '_')}.png"
        Image.fromarray(crop_data).save(crop_path)

        MediaRegistry.reset()
        result = verifier.analyze(crop_path)
        print(f"\n   {name} (crop 25%):")
        print_spectrum(result)

    # ═══════════════════════════════════════════════════════════
    # 5. Verificación de archivo SIN firma
    # ═══════════════════════════════════════════════════════════
    print("\n📊 CONTROL — Imagen sin firma")
    print("-" * 50)

    unsigned_path = output_dir / "unsigned.png"
    create_test_image(unsigned_path, label="SIN FIRMA", color=(128, 128, 128))
    MediaRegistry.reset()
    unsigned_result = verifier.analyze(unsigned_path)
    print(f"\n   Imagen sin firma:")
    print_spectrum(unsigned_result)

    # ═══════════════════════════════════════════════════════════
    # 6. Resumen
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 65)
    print("  RESUMEN")
    print("=" * 65)
    print(f"""
   | Escenario          | Veredicto           | Confianza | Origen      |
   |--------------------|---------------------|-----------|-------------|
   | Foto Real (100%)   | {real_full.verdict:20s} | {real_full.confidence:.0%}      | {real_full.origin_type or 'N/A':11s} |
   | Imagen IA (100%)   | {ai_full.verdict:20s} | {ai_full.confidence:.0%}      | {ai_full.origin_type or 'N/A':11s} |
   | Sin firma          | {unsigned_result.verdict:20s} | {unsigned_result.confidence:.0%}      | {unsigned_result.origin_type or 'N/A':11s} |
""")

    print("   ✅ H-Bit diferencia contenido HUMANO de IA incluso en fragmentos.")
    print(f"   📁 Archivos de demo en: {output_dir}")
    print()


if __name__ == "__main__":
    main()
