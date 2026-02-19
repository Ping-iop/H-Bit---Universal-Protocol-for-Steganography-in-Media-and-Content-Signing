"""
H-Bit Identity Tool (CLI)
-------------------------

Herramienta de mantenimiento para el Registro de Identidades H-Bit.
Permite registrar autores y verificar archivos mostrando la identidad real.

Uso:
    python apps/hbfs/identity_tool.py register --name "Juan" --email "juan@mail.com" --key "apps/hbfs/hbit_private.pem"
    python apps/hbfs/identity_tool.py verify "apps/hbfs/protected/image.jpg"
    python apps/hbfs/identity_tool.py list
"""

import sys
import argparse
from pathlib import Path

# Configurar Path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.append(str(PROJECT_ROOT / "src"))

from hbit.core.crypto import HBitKeyPair, generate_author_hash
from hbit.universal import UniversalVerifier, UniversalVerificationStatus
from identity_registry import IdentityRegistry

def cmd_register(args, registry):
    key_path = Path(args.key)
    if not key_path.exists():
        print(f"❌ Error: Archivo de clave no encontrado: {key_path}")
        return

    try:
        # Cargar clave para obtener public key y hash
        # Nota: HBitKeyPair espera 'hbit_private.pem' en un directorio, 
        # pero aquí pasamos el archivo directo. 
        # Workaround: cargar la clave privada directamente con cryptography
        from cryptography.hazmat.primitives.serialization import load_pem_private_key
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        
        pem_data = key_path.read_bytes()
        private_key = load_pem_private_key(pem_data, password=None)
        
        if not isinstance(private_key, Ed25519PrivateKey):
             print("❌ Error: Clave no es Ed25519")
             return

        # Generar Author Hash (simulado, mismo proceso que UniversalEncoder)
        # OJO: El hash depende de (Key + DeviceID + SensorNoise + Timestamp).
        # El UniversalEncoder genera una identidad "efímera" o "persistente" según implementación.
        # En la implementación actual (crypto.py), author_hash se deriva... ¡espera!
        # crypto.generate_author_hash usa SHA256(PrivKey + DeviceID + Noise + Time).
        # ¡Esto cambia cada vez!
        #
        # CORRECCIÓN IMPORTANTE:
        # Para que la identidad sea VERIFICABLE y PERSISTENTE, el `author_hash` que incrustamos
        # debe ser constante (o rastreable) para un mismo autor.
        # 
        # REVISIÓN DE `UniversalEncoder`:
        # self._normalize_key(effective_key) -> Hash(PrivKey).
        #
        # Si NO usamos KDF (use_kdf=False), author_hash es SHA256(PrivKey).
        # Si usamos KDF (use_kdf=True, default), author_hash se deriva por imagen.
        #
        # ¡Ajá! Si `use_kdf=True` (default), el author_hash cambia por imagen.
        # Entonces el registro NO puede mapear `author_hash` -> Identidad, porque hay infinitos hashes.
        # 
        # SOLUCIÓN:
        # El `author_hash` que se extrae del payload debe poder vincularse al autor.
        # En el diseño actual, si usamos KDF, estamos anonimizando.
        #
        # Para esta implementación de "Autoridad", asumiremos que queremos 
        # vincular la CLAVE PÚBLICA o un HASH MAESTRO.
        #
        # PERO: `UniversalVerifier` devuelve `author_hash`.
        # Si ese hash es derivado por imagen... no podemos hacer lookup inverso fácilmente
        # sin conocer la semilla inicial.
        #
        # REVISANDO `UniversalEncoder.encode`:
        # if self.use_kdf:
        #     image_derived = derive_image_key(...)
        #     effective_key = image_derived.key_material
        # author_hash = self._normalize_key(effective_key)
        #
        # Efectivamente, con KDF activo, el author_hash es único por imagen.
        #
        # WORKAROUND PARA FASE 7.2:
        # Vamos a registrar la CLAVE PÚBLICA MAESTRA en la base de datos.
        # Y `verifier` deberá... uhm.
        #
        # Si el `author_hash` es único, ¿cómo sabe el verificador quién es?
        # El protocolo H-Bit original (whitepaper) dice que el author_hash permite
        # probar autoría revelando la pre-imagen (la clave/nonce) "Challenge-Response".
        #
        # Para este prototipo de "Identidad Pública Visible":
        # Necesitamos un identificador ESTÁTICO incrustado o derivable.
        # 
        # OPCIÓN RÁPIDA: Desactivar KDF en el Monitor para que el author_hash sea constante
        # (SHA256 de la Private Key).
        # Esto reduce privacidad pero permite identificación pública, que es lo que pide el usuario.
        
        # Calculamos el Hash Estático (sin KDF)
        import hashlib
        private_bytes = private_key.private_bytes(
            encoding=sys.modules['cryptography.hazmat.primitives.serialization'].Encoding.Raw,
            format=sys.modules['cryptography.hazmat.primitives.serialization'].PrivateFormat.Raw,
            encryption_algorithm=sys.modules['cryptography.hazmat.primitives.serialization'].NoEncryption()
        )
        # UniversalEncoder._normalize_key logic:
        static_author_hash = hashlib.sha256(private_bytes).digest().hex()
        
        print(f"[INFO] Clave cargada.")
        print(f"[INFO] ID (Static Hash): {static_author_hash[:16]}...")
        
        success = registry.register(
            static_author_hash, 
            args.name, 
            args.email, 
            args.org, 
            public_key="" # Opcional
        )
        
        if success:
            print(f"[OK] Identidad registrada: {args.name} ({args.email})")
        else:
            print("[ERROR] Error guardando en base de datos.")

    except Exception as e:
        print(f"[ERROR] Error procesando clave: {e}")


def cmd_verify(args, registry):
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"❌ Archivo no encontrado: {file_path}")
        return

    print(f"🔍 Analizando: {file_path.name} ...")
    verifier = UniversalVerifier()
    result = verifier.verify(file_path)

    if result.status == UniversalVerificationStatus.NOT_FOUND:
         print("[FAIL] No se encontró firma H-Bit.")
         return

    author_hash = result.decode_result.author_hash
    print(f"[INFO] Firma detectada.")
    print(f"   Hash: {author_hash}")
    
    # Buscar identidad
    identity = registry.lookup(author_hash)
    
    if identity:
        print("\n[OK] IDENTIDAD VERIFICADA (TRUSTED AUTHORITY)")
        print(f"   Nombre: {identity['name']}")
        print(f"   Email:  {identity['email']}")
        print(f"   Org:    {identity['organization']}")
        print(f"   Reg:    {identity['registered_at']}")
    else:
        print("\n[WARN] Identidad Desconocida (Hash válido, pero no registrado)")
        print("   Este autor no está en la base de datos de confianza.")

def cmd_list(registry):
    identities = registry.list_all()
    print(f"--- Identidades Registradas ({len(identities)}) ---")
    for ident in identities:
        print(f"[{ident['author_hash'][:8]}...] {ident['name']} <{ident['email']}>")

def main():
    parser = argparse.ArgumentParser(description="H-Bit Identity Tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Register
    reg_parser = subparsers.add_parser("register", help="Registrar nueva identidad")
    reg_parser.add_argument("--name", required=True, help="Nombre del autor")
    reg_parser.add_argument("--email", required=True, help="Email de contacto")
    reg_parser.add_argument("--org", default="Personal", help="Organización")
    reg_parser.add_argument("--key", required=True, help="Ruta a clave privada (.pem)")

    # Verify
    ver_parser = subparsers.add_parser("verify", help="Verificar archivo y buscar identidad")
    ver_parser.add_argument("file", help="Archivo a verificar")

    # List
    subparsers.add_parser("list", help="Listar identidades")

    args = parser.parse_args()
    
    # Init DB
    db_path = Path(__file__).parent / "data" / "identity.db"
    registry = IdentityRegistry(db_path)

    if args.command == "register":
        cmd_register(args, registry)
    elif args.command == "verify":
        cmd_verify(args, registry)
    elif args.command == "list":
        cmd_list(registry)

if __name__ == "__main__":
    main()
