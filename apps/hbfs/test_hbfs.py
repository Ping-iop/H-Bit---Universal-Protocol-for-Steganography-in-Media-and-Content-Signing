import sys
import os
import time
import shutil
import threading
from pathlib import Path

# Configurar Path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.append(str(PROJECT_ROOT / "src"))

from hbit.universal import UniversalVerifier, UniversalVerificationStatus
from watchdog.observers import Observer

# Importar el handler del monitor (asumiendo que está en el mismo paquete o path)
sys.path.append(str(Path(__file__).parent))
from monitor import HBFSHandler, load_or_generate_key
from hbit.universal import UniversalEncoder

def test_hbfs_integration():
    print("--- INICIANDO TEST HBFS WATCHDOG ---")
    
    # Configurar directorios de prueba
    base_dir = Path(__file__).parent
    input_dir = base_dir / "input_test"
    protected_dir = base_dir / "protected_test"
    app_dir = base_dir / "data_test"

    # Limpiar y crear
    if input_dir.exists(): shutil.rmtree(input_dir)
    if protected_dir.exists(): shutil.rmtree(protected_dir)
    if app_dir.exists(): shutil.rmtree(app_dir)
    
    input_dir.mkdir(parents=True)
    protected_dir.mkdir(parents=True)
    app_dir.mkdir(parents=True)

    # 1. Iniciar Monitor
    print("1. Iniciando Watchdog...")
    author_key = load_or_generate_key(app_dir)
    encoder = UniversalEncoder(use_kdf=False)
    event_handler = HBFSHandler(input_dir, protected_dir, encoder, author_key)
    
    observer = Observer()
    observer.schedule(event_handler, str(input_dir), recursive=False)
    observer.start()

    try:
        # 2. Copiar archivo de prueba (usar una imagen real si existe, o crear texto)
        # Buscamos una imagen en los fixtures
        fixture_img = PROJECT_ROOT / "tests" / "fixtures" / "_FOC4517.jpg"
        test_file = input_dir / "test_image.jpg"
        
        if fixture_img.exists():
            print(f"2. Copiando imagen de prueba: {fixture_img.name}")
            shutil.copy(fixture_img, test_file)
        else:
            print("2. Creando archivo de texto de prueba")
            test_file = input_dir / "test_doc.txt"
            test_file.write_text("Confidential Content for HBFS Test")

        # 3. Esperar a que el watchdog procese (tiene debounce de 1s + procesado)
        print("3. Esperando procesamiento (5s)...")
        time.sleep(5)

        # 4. Verificar resultado
        signed_file = protected_dir / test_file.name
        
        if not signed_file.exists():
            print(f"[FAIL] El archivo firmado no existe en {protected_dir}")
            return False
            
        print(f"[OK] Archivo encontrado en Protected: {signed_file.name}")
        
        # 5. Verificar firma
        print("5. Verificando firma H-Bit...")
        verifier = UniversalVerifier()
        result = verifier.verify(signed_file)
        
        print(f"   Estado: {result.status}")
        print(f"   Mensaje: {result.message}")
        print(f"   Estrategía: {result.decode_result.strategy_used if result.decode_result else 'N/A'}")

        if result.status == UniversalVerificationStatus.VERIFIED:
            print("[OK] TEST EXITOSO: Firma verificada correctamente.")
            return True
        else:
            print("[FAIL] FALLO: La verificación de la firma falló.")
            return False

    except Exception as e:
        print(f"[ERROR] EXCEPCION: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        observer.stop()
        observer.join()
        # Limpieza opcional
        # shutil.rmtree(input_dir)
        # shutil.rmtree(protected_dir)

if __name__ == "__main__":
    success = test_hbfs_integration()
    sys.exit(0 if success else 1)
