"""
H-Bit File System (HBFS) - Demo Prototype v0.1
==============================================

Este script simula el comportamiento del futuro sistema de archivos HBFS.
Crea una carpeta virtual `HBFS_Virtual` donde todo archivo copiado
es automáticamente firmado por el motor H-Bit.

Instrucciones:
1. Ejecuta este script.
2. Copia cualquier archivo (PDF, JPG, WAV, TXT...) a la carpeta `HBFS_Virtual/Input`.
3. El sistema detectará el archivo, lo firmará y lo moverá a `HBFS_Virtual/Signed`.
"""

import os
import sys
import time
import shutil
import logging
from pathlib import Path

# Configuración
BASE_DIR = Path("HBFS_Virtual")
INPUT_DIR = BASE_DIR / "Input"
SIGNED_DIR = BASE_DIR / "Signed"

# Asegurar que podemos importar H-Bit Core
sys.path.append(str(Path(__file__).parent / "src"))

try:
    from hbit.universal import UniversalEncoder
    from hbit.core.crypto import HBitKeyPair
except ImportError:
    print("Error: No se encuentra el módulo 'hbit'. Asegúrate de ejecutar desde la raíz del proyecto.")
    sys.exit(1)

# Logos y UI
def print_banner():
    print("""
    ╔════════════════════════════════════╗
    ║   HBFS - Sistemas de Archivos H-Bit ║
    ║   Prototipo de Inyección Automática ║
    ╚════════════════════════════════════╝
    """)
    print(f"[*] Monitoreando: {INPUT_DIR.absolute()}")
    print(f"[*] Destino:      {SIGNED_DIR.absolute()}")
    print("\n[!] Presiona Ctrl+C para detener.\n")

def setup_dirs():
    if not BASE_DIR.exists():
        os.makedirs(BASE_DIR)
        print(f"[+] Creado directorio base: {BASE_DIR}")
    
    if not INPUT_DIR.exists():
        os.makedirs(INPUT_DIR)
    
    if not SIGNED_DIR.exists():
        os.makedirs(SIGNED_DIR)

def process_file(file_path):
    filename = file_path.name
    print(f"\n[>] Detectado: {filename}")
    
    try:
        # Usar una passphrase por defecto para la demo
        passphrase = "hbfs-demo-key"
        
        # Output path
        output_path = SIGNED_DIR / filename
        
        print(f"    Firmando con motor UniversalEncoder...")
        encoder = UniversalEncoder()
        
        # Encriptamos por defecto en este modo "Secure FS"
        # Usamos encrypt=True para máxima seguridad demo
        encoder.encode(
            file_path=str(file_path),
            author_key=passphrase,  # Passphrase string mode
            output_path=str(output_path),
            encrypt=True
        )
        
        print(f"    [OK] Firmado y Cifrado -> {output_path.name}")
        
        # Eliminar original del input para simular "movimiento"
        os.remove(file_path)
        
    except Exception as e:
        print(f"    [X] Error procesando {filename}: {e}")
        # Mover a error dir? O dejar en input?
        # Dejamos en input renonmbrado para no buclear
        error_path = file_path.with_name(file_path.name + ".error")
        if not error_path.exists():
             shutil.move(file_path, error_path)

def main_loop():
    setup_dirs()
    print_banner()
    
    # Clave de prueba (simulada por passphrase arriba)
    
    while True:
        # Scan dir
        # Listar archivos ignorando carpetas y ocultos
        files = [f for f in INPUT_DIR.iterdir() if f.is_file() and not f.name.endswith(".error")]
        
        for file in files:
            # Esperar a que el archivo esté libre (sha1 lock check simple)
            # En windows si se está copiando, open puede fallar.
            try:
                # Intentar abrir para ver si terminó de copiarse
                with open(file, "rb") as _:
                    pass
                process_file(file)
            except PermissionError:
                # Archivo sigue en uso (copiando)
                continue
            except Exception as e:
                print(f"Error accediendo {file}: {e}")
        
        time.sleep(1.0)

if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        print("\n[!] Deteniendo hbfs monitoring...")
