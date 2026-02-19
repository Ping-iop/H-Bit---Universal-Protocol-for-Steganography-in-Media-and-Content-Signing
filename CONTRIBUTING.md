# Contribuyendo a H-Bit

¡Gracias por tu interés en contribuir al Protocolo H-Bit! Este documento te guiará en el proceso.

## Configuración del Entorno de Desarrollo

```bash
# 1. Clonar el repositorio
git clone https://github.com/hbit-protocol/hbit.git
cd hbit

# 2. Crear un entorno virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# o: .\venv\Scripts\activate  # Windows

# 3. Instalar dependencias de desarrollo
pip install -e ".[dev]"

# 4. Verificar que los tests pasan
pytest
```

### GPU (opcional)

Para habilitar la aceleración GPU:

```bash
pip install cupy-cuda12x  # Ajustar a tu versión de CUDA
```

## Estilo de Código

- **Linter:** [Ruff](https://docs.astral.sh/ruff/) (configurado en `pyproject.toml`)
- **Type checker:** [MyPy](https://mypy-lang.org/)
- **Line length:** 100 caracteres
- **Python mínimo:** 3.11

```bash
# Ejecutar linter
ruff check src/

# Ejecutar type checker
mypy src/hbit/
```

## Estructura del Proyecto

```
src/hbit/
├── core/        # Criptografía, KDF, sync, encryption
├── encoders/    # LSB, DCT, Hybrid
├── formats/     # Handlers por tipo de archivo
├── resilience/  # ECC, Tiling, Anchors, Dewarp
├── blockchain/  # Registrar, C2PA, Oracle
├── forensics/   # PRNU, Luminance
├── analysis/    # Entropy, Saliency, JND
├── universal.py # Pipeline universal
├── pipeline.py  # Pipeline legacy (imágenes)
└── cli.py       # CLI (Click)
```

## Proceso de Contribución

1. **Crea un Issue** describiendo el cambio propuesto
2. **Fork** el repositorio
3. **Crea una rama** desde `main`: `git checkout -b feature/mi-mejora`
4. **Implementa** los cambios siguiendo el estilo del proyecto
5. **Añade tests** para cualquier funcionalidad nueva
6. **Ejecuta el linter y los tests:**
   ```bash
   ruff check src/
   pytest
   ```
7. **Crea un Pull Request** con una descripción clara

## Tests

- Los tests unitarios están en `tests/unit/`
- Los tests de integración están en `tests/integration/`
- Las fixtures (imágenes de prueba) están en `tests/fixtures/`

```bash
# Ejecutar todos los tests
pytest

# Con cobertura
pytest --cov=hbit --cov-report=html

# Un test específico
pytest tests/unit/test_core.py::TestCrypto::test_sign_and_verify -v
```

## Áreas Prioritarias de Contribución

- **Mejorar robustez DCT** ante compresión JPEG agresiva
- **PDF handler** más robusto (content-level embedding)
- **Tests de integración** E2E para el pipeline completo
- **Documentación** técnica (MkDocs)
- **Mobile SDK** (iOS/Android)

## Licencia

Al contribuir, aceptas que tu contribución se licenciará bajo Apache 2.0.
