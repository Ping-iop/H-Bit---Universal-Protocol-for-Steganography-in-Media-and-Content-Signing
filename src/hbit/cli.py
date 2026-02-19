"""
Interfaz de línea de comandos (CLI) del protocolo H-Bit.

Proporciona acceso completo al protocolo mediante subcomandos:
  hbit keygen   — Genera par de claves Ed25519
  hbit encode   — Firma cualquier archivo con H-Bit
  hbit decode   — Extrae la firma H-Bit de un archivo
  hbit verify   — Verifica autenticidad e integridad
  hbit info     — Muestra información de la firma
  hbit formats  — Lista formatos soportados
"""

from __future__ import annotations

from pathlib import Path

import click

from hbit import __version__


@click.group()
@click.version_option(__version__, prog_name="H-Bit")
def main():
    """H-Bit: Protocolo de Autenticidad Persistente.

    Sistema de firmado esteganográfico universal que establece
    un vínculo inalienable entre la autoría intelectual y
    cualquier archivo digital: imágenes, audio, video,
    documentos, y cualquier formato presente o futuro.
    """


@main.command()
@click.option(
    "--output", "-o",
    type=click.Path(),
    default="./hbit_keys",
    help="Directorio donde guardar las claves.",
)
def keygen(output: str):
    """Genera un nuevo par de claves Ed25519 para firma H-Bit."""
    from hbit.core.crypto import generate_key_pair

    key_pair = generate_key_pair()
    output_dir = Path(output)
    key_pair.save_to_directory(output_dir)

    click.echo(f"✓ Claves generadas en: {output_dir.absolute()}")
    click.echo(f"  · Privada: {output_dir / 'hbit_private.pem'}")
    click.echo(f"  · Pública: {output_dir / 'hbit_public.pem'}")
    click.echo()
    click.echo("⚠ Guarda la clave privada en un lugar seguro.")


@main.command()
@click.option(
    "--input", "-i", "input_path",
    required=True,
    type=click.Path(exists=True),
    help="Archivo de entrada a firmar.",
)
@click.option(
    "--key", "-k",
    required=True,
    help="Directorio con claves PEM o passphrase entre comillas.",
)
@click.option(
    "--output", "-o", "output_path",
    type=click.Path(),
    help="Ruta para el archivo firmado (default: input_hbit.ext).",
)
@click.option(
    "--channel", "-c",
    type=click.IntRange(0, 2),
    default=None,
    help="Canal de color (0=R, 1=G, 2=B). Solo para imágenes.",
)
@click.option(
    "--adaptive/--uniform",
    default=True,
    help="Usar redundancia adaptativa (default) o uniforme. Solo imágenes.",
)
@click.option(
    "--no-kdf",
    is_flag=True,
    default=False,
    help="Deshabilitar derivación de clave efímera.",
)
@click.option(
    "--legacy",
    is_flag=True,
    default=False,
    help="Usar el pipeline legacy de imágenes (solo PNG/JPG/BMP).",
)
@click.option(
    "--encrypt",
    is_flag=True,
    default=False,
    help="Cifrar el payload H-Bit (AES-256). Requiere usar passphrase en --key.",
)
def encode(
    input_path: str,
    key: str,
    output_path: str | None,
    channel: int | None,
    adaptive: bool,
    no_kdf: bool,
    legacy: bool,
    encrypt: bool,
):
    """Incrusta una firma H-Bit en cualquier archivo."""
    from hbit.core.crypto import HBitKeyPair

    input_file = Path(input_path)

    # Determinar ruta de salida
    if output_path is None:
        stem = input_file.stem
        ext = input_file.suffix or ".bin"
        output_path = str(input_file.parent / f"{stem}_hbit{ext}")

    # Resolver clave
    key_path = Path(key)
    if key_path.is_dir():
        author_key = HBitKeyPair.load_from_directory(key_path)
    else:
        author_key = key  # Se tratará como passphrase

    if legacy:
        # Pipeline legacy: solo imágenes
        _encode_legacy(
            input_path, author_key, output_path,
            channel, adaptive, no_kdf,
        )
    else:
        # Pipeline universal: cualquier formato
        try:
            _encode_universal(
                input_path, author_key, output_path, no_kdf, encrypt,
            )
        except ValueError as e:
            click.echo(f"Error: {e}")
            raise SystemExit(1)


def _encode_universal(input_path, author_key, output_path, no_kdf, encrypt=False):
    """Codificación universal via MediaRegistry."""
    from hbit.universal import UniversalEncoder

    encoder = UniversalEncoder(use_kdf=not no_kdf)
    input_file = Path(input_path)

    click.echo(f"Firmando: {input_file.name}")
    if encrypt:
        click.echo("🔒 Modo cifrado habilitado (AES-256-GCM)")

    result = encoder.encode(
        file_path=input_path,
        author_key=author_key,
        output_path=output_path,
        encrypt=encrypt,
    )

    click.echo(f"✓ Archivo firmado guardado: {result.output_path}")
    click.echo(f"  · Tipo:      {result.media_category}")
    click.echo(f"  · Handler:   {result.handler_name}")
    click.echo(f"  · Estrategia:{result.strategy_used}")
    click.echo(f"  · Autor:     {result.author_hash[:32]}...")
    click.echo(f"  · Contenido: {result.content_hash[:32]}...")
    click.echo(f"  · Bits:      {result.bits_embedded}")
    click.echo(f"  · Capacidad: {result.capacity_used:.1%}")


def _encode_legacy(input_path, author_key, output_path, channel, adaptive, no_kdf):
    """Codificación legacy solo para imágenes."""
    from hbit.pipeline import HBitEncoder

    encoder = HBitEncoder(
        adaptive_density=adaptive,
        auto_channel=channel is None,
        use_kdf=not no_kdf,
    )

    click.echo(f"Firmando (legacy): {Path(input_path).name}")
    result = encoder.encode(
        image_path=input_path,
        author_key=author_key,
        output_path=output_path,
        channel=channel,
    )

    click.echo(f"✓ Imagen firmada guardada: {result.output_path}")
    click.echo(f"  · Autor:     {result.author_hash[:32]}...")
    click.echo(f"  · Contenido: {result.content_hash[:32]}...")
    click.echo(f"  · Canal:     {['R', 'G', 'B'][result.channel_used]}")
    click.echo(f"  · Copias:    {result.units_embedded}")
    click.echo(f"  · Capacidad: {result.capacity_used:.1%}")
    click.echo(f"  · Payload:   {result.payload_size_bits} bits")


@main.command()
@click.option(
    "--input", "-i", "input_path",
    required=True,
    type=click.Path(exists=True),
    help="Archivo del que extraer la firma.",
)
@click.option(
    "--channel", "-c",
    type=click.IntRange(0, 2),
    default=None,
    help="Canal de color donde buscar (solo imágenes, default: auto).",
)
@click.option(
    "--legacy",
    is_flag=True,
    default=False,
    help="Usar el pipeline legacy de imágenes.",
)
@click.option(
    "--passphrase", "-p",
    default=None,
    help="Passphrase para descifrar el payload si está encriptado.",
)
def decode(input_path: str, channel: int | None, legacy: bool, passphrase: str | None):
    """Extrae la firma H-Bit de cualquier archivo."""
    if legacy:
        _decode_legacy(input_path, channel)
    else:
        _decode_universal(input_path, passphrase)


def _decode_universal(input_path, passphrase=None):
    """Decodificación universal."""
    from hbit.universal import UniversalDecoder

    decoder = UniversalDecoder()
    result = decoder.decode(input_path, passphrase)

    if not result.found:
        click.echo("✗ No se encontró firma H-Bit en el archivo.")
        raise SystemExit(1)

    click.echo(f"✓ Firma H-Bit encontrada:")
    click.echo(f"  · Tipo:      {result.media_category}")
    click.echo(f"  · Versión:   v{result.version}")
    click.echo(f"  · Autor:     {result.author_hash[:32]}...")
    click.echo(f"  · Contenido: {result.content_hash[:32]}...")
    click.echo(f"  · Timestamp: {result.timestamp}")
    click.echo(f"  · Confianza: {result.confidence:.1%}")


def _decode_legacy(input_path, channel):
    """Decodificación legacy para imágenes."""
    from hbit.pipeline import HBitDecoder

    decoder = HBitDecoder()
    result = decoder.decode(input_path, channel=channel)

    if result.payloads_found == 0:
        click.echo("✗ No se encontró firma H-Bit en la imagen.")
        raise SystemExit(1)

    click.echo(f"✓ Firma H-Bit encontrada:")
    click.echo(f"  · Versión:   v{result.version}")
    click.echo(f"  · Autor:     {result.author_hash[:32]}...")
    click.echo(f"  · Contenido: {result.content_hash[:32]}...")
    click.echo(f"  · Timestamp: {result.timestamp}")
    click.echo(f"  · Copias:    {result.payloads_found}")
    click.echo(f"  · Confianza: {result.confidence:.1%}")


@main.command()
@click.option(
    "--input", "-i", "input_path",
    required=True,
    type=click.Path(exists=True),
    help="Archivo a verificar.",
)
@click.option(
    "--author", "-a",
    default=None,
    help="Hash de autor esperado (hex) para verificación.",
)
@click.option(
    "--channel", "-c",
    type=click.IntRange(0, 2),
    default=None,
    help="Canal de color (solo imágenes, default: auto).",
)
@click.option(
    "--legacy",
    is_flag=True,
    default=False,
    help="Usar el pipeline legacy de imágenes.",
)
@click.option(
    "--passphrase", "-p",
    default=None,
    help="Passphrase para verificar integridad de payload cifrado.",
)
def verify(input_path: str, author: str | None, channel: int | None, legacy: bool, passphrase: str | None):
    """Verifica la autenticidad e integridad de un archivo firmado."""
    if legacy:
        _verify_legacy(input_path, author, channel)
    else:
        _verify_universal(input_path, author, passphrase)


def _verify_universal(input_path, author, passphrase=None):
    """Verificación universal."""
    from hbit.universal import UniversalVerifier

    verifier = UniversalVerifier()
    result = verifier.verify(
        file_path=input_path, 
        expected_author_hash=author,
        passphrase=passphrase,
    )

    click.echo(result.message)
    click.echo(f"  · Estado: {result.status.value}")

    if result.decode_result:
        click.echo(f"  · Tipo:      {result.decode_result.media_category}")
        click.echo(f"  · Confianza: {result.decode_result.confidence:.1%}")

    if result.status.value in ("NOT_FOUND", "INVALID", "TAMPERED"):
        raise SystemExit(1)


def _verify_legacy(input_path, author, channel):
    """Verificación legacy para imágenes."""
    from hbit.pipeline import HBitVerifier

    verifier = HBitVerifier()
    result = verifier.verify(
        image_path=input_path,
        expected_author_hash=author,
        channel=channel,
    )

    click.echo(result.message)
    click.echo(f"  · Estado: {result.status.value}")

    if result.decode_result:
        click.echo(f"  · Copias: {result.decode_result.payloads_found}")
        click.echo(f"  · Confianza: {result.decode_result.confidence:.1%}")

    if result.status.value in ("NOT_FOUND", "INVALID", "TAMPERED"):
        raise SystemExit(1)


@main.command()
@click.option(
    "--input", "-i", "input_path",
    required=True,
    type=click.Path(exists=True),
    help="Archivo a inspeccionar.",
)
def info(input_path: str):
    """Muestra información detallada del archivo y su firma H-Bit."""
    from hbit.formats import MediaRegistry

    input_file = Path(input_path)
    registry = MediaRegistry.default()

    handler = registry.get_handler(input_file)
    carrier = handler.load(input_file)

    click.echo(f"Archivo: {input_file.name}")
    click.echo(f"  · Tamaño:     {input_file.stat().st_size:,} bytes")
    click.echo(f"  · Tipo:       {handler.category.value}")
    click.echo(f"  · Handler:    {handler.name}")
    click.echo(f"  · Capacidad:  {carrier.capacity_bits:,} bits")
    click.echo(f"  · Estrategia: {carrier.strategy.name}")

    if carrier.metadata:
        click.echo(f"  · Formato:    {carrier.metadata.get('format', 'unknown')}")

    # Imprimir info específica para imágenes
    if handler.category.value == "image":
        w = carrier.metadata.get("width", "?")
        h = carrier.metadata.get("height", "?")
        click.echo(f"  · Resolución: {w}×{h}")

    # Buscar firma
    extract = handler.extract(carrier)
    if extract.payloads_found > 0:
        click.echo(f"\n  Firma H-Bit detectada:")
        click.echo(f"  · Estrategia: {extract.strategy_used.name}")
        click.echo(f"  · Confianza:  {extract.confidence:.1%}")
    else:
        click.echo(f"\n  · No se detectó firma H-Bit.")


@main.command("formats")
def list_formats():
    """Lista todos los formatos soportados por H-Bit."""
    from hbit.formats import MediaRegistry

    registry = MediaRegistry.default()
    handlers = registry.registered_handlers

    click.echo("Formatos soportados por H-Bit:\n")

    # Agrupar por handler
    grouped: dict[str, list[str]] = {}
    for ext, name in handlers.items():
        grouped.setdefault(name, []).append(ext)

    for handler_name, exts in grouped.items():
        ext_list = ", ".join(f".{e}" for e in sorted(exts))
        click.echo(f"  {handler_name}: {ext_list}")

    click.echo(f"\n  + GenericHandler: cualquier otro formato (fallback)")
    click.echo(f"\nTotal: {len(handlers)} extensiones registradas")


@main.command()
@click.option(
    "--dir", "-d", "dir_path",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help="Directorio con archivos a firmar.",
)
@click.option(
    "--key", "-k",
    required=True,
    help="Directorio con claves PEM o passphrase.",
)
@click.option(
    "--output-dir", "-o", "output_dir",
    type=click.Path(),
    default=None,
    help="Directorio de salida (default: mismo directorio + subfolder 'signed').",
)
@click.option(
    "--recursive/--no-recursive",
    default=False,
    help="Procesar subdirectorios recursivamente.",
)
@click.option(
    "--encrypt",
    is_flag=True,
    default=False,
    help="Cifrar los payloads H-Bit.",
)
def batch(
    dir_path: str,
    key: str,
    output_dir: str | None,
    recursive: bool,
    encrypt: bool,
):
    """Firma todos los archivos de un directorio en batch."""
    from hbit.core.crypto import HBitKeyPair
    from hbit.formats import MediaRegistry
    from hbit.universal import UniversalEncoder

    input_dir = Path(dir_path)
    out_dir = Path(output_dir) if output_dir else input_dir / "signed"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Resolver clave
    key_path = Path(key)
    if key_path.is_dir():
        author_key = HBitKeyPair.load_from_directory(key_path)
    else:
        author_key = key

    # Descubrir archivos
    registry = MediaRegistry.default()
    if recursive:
        files = [f for f in input_dir.rglob("*") if f.is_file()]
    else:
        files = [f for f in input_dir.iterdir() if f.is_file()]

    # Filtrar archivos procesables
    files = [f for f in files if f.suffix.lstrip(".") in registry.registered_handlers or True]

    if not files:
        click.echo("No se encontraron archivos para firmar.")
        return

    click.echo(f"Batch: {len(files)} archivos en {input_dir}")
    click.echo(f"Salida: {out_dir}")
    click.echo()

    encoder = UniversalEncoder()
    success = 0
    errors = 0

    for f in files:
        try:
            rel = f.relative_to(input_dir)
            dest = out_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)

            result = encoder.encode(f, author_key, dest, encrypt=encrypt)
            click.echo(f"  [OK] {rel} ({result.strategy_used})")
            success += 1
        except Exception as e:
            click.echo(f"  [ERR] {rel}: {e}")
            errors += 1

    click.echo()
    click.echo(f"Completado: {success} firmados, {errors} errores.")


if __name__ == "__main__":
    main()
