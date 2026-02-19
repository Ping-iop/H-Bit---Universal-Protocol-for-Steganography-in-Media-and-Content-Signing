"""
H-Bit File System (HBFS) - Watchdog Monitor
-------------------------------------------

Prototipo de sistema de archivos autenticado en espacio de usuario.
Monitorea una carpeta de entrada y firma automáticamente cualquier archivo
nuevo o modificado, moviéndolo a una carpeta protegida.

Uso:
    python apps/hbfs/monitor.py [path_to_input] [path_to_protected]

Por defecto:
    Input:     ./apps/hbfs/input
    Protected: ./apps/hbfs/protected
"""

import sys
import time
import shutil
import logging
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Asegurar que src está en el path
sys.path.append(str(Path(__file__).parent.parent.parent / "src"))

from hbit.universal import UniversalEncoder
from hbit.core.crypto import HBitKeyPair, generate_key_pair

# Configuración de Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("HBFS")

class HBFSHandler(FileSystemEventHandler):
    """Manejador de eventos del sistema de archivos para HBFS."""

    def __init__(self, input_dir: Path, protected_dir: Path, encoder: UniversalEncoder, author_key: HBitKeyPair):
        self.input_dir = input_dir
        self.protected_dir = protected_dir
        self.encoder = encoder
        self.author_key = author_key
        self._processing = set()  # Set para evitar bucles infinitos o doble procesado

    def on_modified(self, event):
        if event.is_directory:
            return
        self._process_file(Path(event.src_path))

    def on_created(self, event):
        if event.is_directory:
            return
        self._process_file(Path(event.src_path))

    def _process_file(self, file_path: Path):
        """Procesa un archivo detectado en la carpeta de entrada."""
        # Ignorar archivos temporales o ocultos
        if file_path.name.startswith(".") or file_path.name.endswith(".tmp"):
            return

        # Ignorar si ya se está procesando (debounce simple)
        if file_path in self._processing:
            return

        self._processing.add(file_path)
        
        # Esperar a que el archivo deje de escribirse (debounce de escritura)
        time.sleep(1.0) 

        # Intentar procesar
        try:
            logger.info(f"⚡ Detectado: {file_path.name}")
            
            # Verificar si el archivo está listo (no bloqueado por otro proceso)
            if not self._wait_for_file_ready(file_path):
                logger.warning(f"⚠️ Archivo bloqueado o ilegible: {file_path.name}")
                self._processing.remove(file_path)
                return

            # Definir ruta de salida protegida
            # Añadimos extensión automática si es necesario, o mantenemos original
            # Para imagenes robustas, mantenemos extension (.jpg -> .jpg)
            dest_name = file_path.name
            output_path = self.protected_dir / dest_name

            logger.info(f"🔒 Firmando y protegiendo...")

            # Firmar usando UniversalEncoder (detecta formato automáticamente)
            # Usamos DCT para JPEG, LSB para PNG, Stream para PDF, etc.
            result = self.encoder.encode(
                file_path=file_path,
                author_key=self.author_key,
                output_path=output_path
            )

            logger.info(f"✅ PROTEGIDO: {output_path.name}")
            logger.info(f"   - Estrategia: {result.strategy_used}")
            logger.info(f"   - Autor: {result.author_hash[:8]}...")

            # Eliminar original (Secure Wipe simulado)
            # En un sistema real, haríamos shredding. Aquí solo borramos.
            try:
                file_path.unlink()
                logger.info(f"🗑️  Original eliminado (Input limpio)")
            except Exception as e:
                logger.error(f"❌ Error borrando original: {e}")

        except Exception as e:
            logger.error(f"❌ Error procesando {file_path.name}: {e}")
        finally:
            if file_path in self._processing:
                self._processing.remove(file_path)

    def _wait_for_file_ready(self, file_path: Path, timeout: float = 5.0) -> bool:
        """Espera a que el archivo pueda abrirse para lectura exclusiva."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                with open(file_path, "rb"):
                    return True
            except OSError:
                time.sleep(0.5)
        return False


def load_or_generate_key(app_dir: Path) -> HBitKeyPair:
    """Carga la identidad del nodo o genera una nueva."""
    try:
        keys = HBitKeyPair.load_from_directory(app_dir)
        logger.info("🔑 Identidad cargada desde disco.")
        return keys
    except (FileNotFoundError, TypeError):
        logger.info("🆕 Generando nueva identidad HBFS...")
        keys = generate_key_pair()
        keys.save_to_directory(app_dir)
        return keys


def main():
    # Rutas base
    base_dir = Path(__file__).parent
    input_dir = base_dir / "input"
    protected_dir = base_dir / "protected"

    # Argumentos CLI opcionales
    if len(sys.argv) > 1:
        input_dir = Path(sys.argv[1])
    if len(sys.argv) > 2:
        protected_dir = Path(sys.argv[2])

    input_dir.mkdir(parents=True, exist_ok=True)
    protected_dir.mkdir(parents=True, exist_ok=True)

    print(f"========================================")
    print(f"   H-Bit File System (HBFS) Watchdog    ")
    print(f"========================================")
    print(f"Monitoring: {input_dir}")
    print(f"Protected:  {protected_dir}")
    print(f"----------------------------------------")

    # Inicializar identidad
    author_key = load_or_generate_key(base_dir)
    print(f"Node Identity: {author_key.public_key_hex[:16]}...")

    # Inicializar Encoder (KDF=False para identidad estática verificable)
    encoder = UniversalEncoder(use_kdf=False)

    # Iniciar Watchdog
    event_handler = HBFSHandler(input_dir, protected_dir, encoder, author_key)
    observer = Observer()
    observer.schedule(event_handler, str(input_dir), recursive=False)
    observer.start()

    print("🚀 HBFS Monitor activo. Presiona Ctrl+C para detener.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Deteniendo HBFS Monitor...")
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()
