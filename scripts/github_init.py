import os
import subprocess
import sys

def run_cmd(cmd):
    """Ejecuta un comando en la terminal y retorna el resultado."""
    print(f"Ejecutando: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error ({result.returncode}): {result.stderr}")
    else:
        print(result.stdout)
    return result.returncode == 0

def main():
    print("--- Inicializador de Repositorio GitHub para H-Bit ---")
    
    # 1. Crear .gitignore si no existe
    gitignore_path = ".gitignore"
    if not os.path.exists(gitignore_path):
        print("Creando .gitignore base...")
        with open(gitignore_path, "w") as f:
            f.write("""# Entornos virtuales
venv/
env/
.env

# Pytest y cobertura
.pytest_cache/
htmlcov/
.coverage

# Archivos compilados Python
__pycache__/
*.py[cod]
*$py.class

# Archivos de SO
.DS_Store
Thumbs.db

# Claves criptograficas y temporales
*.pem
*.key
*.db
tmp/
temp/
""")

    # 2. Inicializar Git local
    if not os.path.exists(".git"):
        print("Inicializando repositorio Git local...")
        run_cmd("git init")
    else:
        print("Repositorio Git local ya inicializado.")

    # 3. Añadir archivos e intentar el primer commit
    run_cmd("git add .")
    
    # Verificar si hay cambios por hacer commit
    status = subprocess.run("git status --porcelain", shell=True, capture_output=True, text=True)
    if status.stdout.strip():
        run_cmd('git commit -m "feat: H-Bit Protocol Beta 1.0.0 (API, Blockchain, Architecture completados)"')
        print("Commit inicial completado localmente.")
    else:
        print("No hay cambios nuevos para commit.")

    print("\n" + "="*50)
    print("El repositorio local esta listo.")
    print("Para subir a tu cuenta de GitHub, sigue estos pasos desde la terminal:")
    print("1. Si tienes GitHub CLI instalado, ejecuta:")
    print("   gh repo create H-Bit --public --source=. --remote=origin --push")
    print("2. Si lo haces via web (github.com):")
    print("   - Crea un repositorio vacio llamado 'H-Bit'")
    print("   - Luego ejecuta estos comandos:")
    print("     git remote add origin https://github.com/TU_USUARIO/H-Bit.git")
    print("     git branch -M main")
    print("     git push -u origin main")
    print("="*50)

if __name__ == "__main__":
    main()
