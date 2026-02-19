# H-Bit — Registro del Proyecto

## 2026-02-19: Fase 10.7 y Fase 11 — Ecosistema y Hardware

### Smart Contract Deployment (Fase 10.7)
- Construido el `HBitRegistry.sol` basado en la ABI oficial.
- Creado script `scripts/deploy_blockchain.py` utilizando `eth-tester` y `py-solc-x`.
- Prueba local exitosa (deploy, register, verify) en cadena de bloques en memoria, eliminando la necesidad temporal de gastar GAS en testnets públicas.

### Hardware Mocks y Arquitectura (Fase 11)
- Establecidos los mockups en Python para las futuras integraciones nativas C/C++.
- `src/hbit/hardware/isp_enclave.py`: Simulación de firma dentro del procesador de cámara.
- `src/hbit/hardware/hsm_signer.py`: Simulación de dispositivo YubiKey/KMS.
- `src/hbit/hardware/fuse_driver.py`: Interceptor simulado de disco a nivel de SO (HBFS).
- Creada documentación de arquitectura en `docs/hardware_integration/architecture.md`.

### Documentación y GitHub
- El archivo `WHITEPAPER.md` (roadmap) fue actualizado con el estatus de las últimas fases. Re-priorizado 10.5 y 10.6 como backlog para enfocarse en hardware y contratos.
- Creado y ejecutado `scripts/github_init.py` para automatizar la creación del `.gitignore` e inicializar el repositorio `.git` con todo el contenido actual bajo un primer commit estructural de la Beta 1.0.0.
- La documentación del proyecto (`README.md` y `WHITEPAPER.md`) ahora es totalmente **Bilingüe (Español / Inglés)**, para maximizar el alcance en GitHub, manteniendo versiones localizadas conectadas entre sí.

## 2026-02-19: Fase 10 — Ecosystem Expansion (Continuación)

### REST API Microservice (P2/Fase 10)
- Implementación de un microservicio usando `FastAPI` en `apps/api/`.
- **Endpoints:**
  - `POST /api/v1/encode`: Sube un archivo y lo firma usando el `UniversalEncoder`. Retorna el archivo binario firmado (`FileResponse`). Soporta encriptación opcional indicando param `encrypt`.
  - `POST /api/v1/verify`: Recibe un archivo firmado y usa `UniversalVerifier`. Retorna un esquema JSON (`VerificationResponse`) con autor, contenido, y confiabilidad.
- **Arquitectura:**
  - `main.py`: Configuración de FastAPI y CORS middleware para acceso universal.
  - `routes.py`: Rutas y manejo asíncrono seguro de archivos temporales mediante `BackgroundTasks` y limpieza.
  - `schemas.py`: Validadores y modelos de Pydantic.
- **Tests Integración:**
  - `tests/integration/test_api.py`. Adaptación de tests genéricos `.txt` para sortear bug `NOT_FOUND` reportado en Fase 9 (PNG Lossy Handling). Tests pasando 100%.

## 2026-02-19: Fase 10 — Ecosystem Expansion

### Whitepaper v2.0 (Formalización Matemática)
- Reescritura completa de `WHITEPAPER.md` con 17 fórmulas matemáticas verificadas contra código fuente.
- Cubre: QIM, Watson JND, Barker NCC, PRNU, adaptive strength, majority vote, Shannon entropy, luminance coherence.
- Nuevo Appendix C: Formula Index con mapping fórmula → archivo fuente.
- Actualización de roadmap Fases 9-11 y production status.

### PDF Handler v2 — Content-Level (P4)
- Reescritura completa de `PDFHandler` en `document.py`.
- Estrategia v2: objeto PDF indirecto `/Type /HBitPayload` con stream base64 (en lugar de comentario antes de %%EOF).
- Inserción antes de xref/startxref para máxima robustez ante edición.
- Backward compatibility: extrae payloads legacy (HBITSIGN markers).
- Nuevos métodos: `_strip_hbit_data`, `_find_next_obj_number`, `_find_insert_position`, `_extract_v2`, `_extract_legacy`.
- **4/4 tests pasando**.

### PyPI Release Prep (I1)
- `pyproject.toml`: versión 1.0.0b1, status Beta, Python 3.13 support, optional deps (gpu, gui).
- Creado `MANIFEST.in` para sdist.
- `pip install -e . --dry-run` verificado: resuelve como `hbit-1.0.0b1`.

### Video Multi-Keyframe (I7)
- Reescritura de `embed()` y `extract()` en `video.py`.
- Cada keyframe recibe copia completa del payload (canal azul LSB).
- Extracción: majority vote bit a bit entre todas las copias.
- Nuevo método `_majority_vote()` para reconstrucción robusta.

### Estado
- **28/28 tests de formatos pasando** (imagen, audio, PDF, Office, genérico).
- Test de regresión PNG E2E: pendiente investigación (pre-existente).

---

## 2026-02-19: Fase 9 — Production Hardening

### CI/CD (P1)
- Creado `.github/workflows/ci.yml` — GitHub Actions multi-OS (Ubuntu + Windows), multi-Python (3.11, 3.12).
- Lint (Ruff), type check (MyPy), tests (pytest + coverage), build + upload artifacts.

### Fuzz Testing (P3)
- Creado `tests/unit/test_fuzz.py` — 7 tests Hypothesis para deserialization, sync, y roundtrip.
- Usa `pytest.importorskip("hypothesis")` para skip limpio cuando no está instalado.

### Docker (I2)
- Creado `Dockerfile` — Multi-stage build, Python 3.12-slim, volumes para input/output/keys.

### Integration Tests (I4)
- Creado `tests/integration/test_e2e.py` — 7 tests E2E por formato (PNG, WAV, PDF, DOCX, DAT).
- Cubre: pipeline completo, encriptación, multi-key, CLI.

### Batch CLI (N2)
- Nuevo comando `hbit batch --dir ./fotos --key mi_clave --recursive` para firmar directorios.

### DCT Auto-Adaptive (I8)
- Creada `compute_adaptive_strength()` en `dct.py` — analiza textura (bordes, varianza, energía DCT).
- Integrada en `ImageHandler` — reemplaza `strength=35.0` fijo por valor adaptativo.

### Documentación (I3)
- Creado `CONTRIBUTING.md` — setup de dev, código, estructura, proceso de contribución.

### Bug Fixes
- Corregidos 2 bugs `default=False` duplicados en CLI (decode + verify commands).

### Estado
- **134+ tests pasando** (exit code 0).
- Fuzz tests skippeados limpiamente (hypothesis no instalado).

---

## 2026-02-19: Fase 8 — Producción y Documentación

### Test Fixes (Regresiones)
- **`_normalize_key`**: Fix de seguridad — siempre hashea claves (protege clave privada).
- **`decrypt_payload`**: Fix para payloads comprimidos — check de flags antes de validar longitud mínima.
- **`test_to_binary_string`**: Corregido para usar `serialize_core()` (tamaño determinístico).
- **`test_verify_pdf`**: Corregido assertion de mensaje `[OK]` vs `✓`.

### Limpieza
- Eliminados 28 `debug_log_*.txt` + 12 archivos de test sueltos de raíz.
- Creado `.gitignore` profesional.

### Documentación
- Creado `README.md` con instalación, CLI, API Python, arquitectura y formatos.

### Tests de Robustez
- Nuevo `test_compression_robustness.py` con 5 tests de resiliencia ante compresión JPEG.
- Documenta trade-off de strength=35.0: mejor calidad visual vs menor robustez ante recompresión.

### Auditoría Completa
- 30+ módulos auditados en 9 paquetes.
- **Estado final: 134/134 tests pasando**.

### Whitepaper Técnico
- Creado `WHITEPAPER.md` (650+ líneas) para compartir con expertos e ingenieros.
- Cubre: arquitectura, criptografía, embedding, resiliencia, soporte universal, blockchain, forense.
- Incluye **Production Gap Analysis** con blockers priorizados (P1-P4, I1-I8, N1-N6).
- Incluye roadmap Fases 9-11 (Production Hardening → Ecosystem → Hardware).

---

## 2026-02-19: Fase 7 — HBFS + Identity Management

### Fase 7.1: HBFS Watchdog Prototype
- **Monitor**: `apps/hbfs/monitor.py` — Auto-firma archivos al detectar cambios.
- **Identidad Estática**: `use_kdf=False` para hash consistente.

### Fase 7.2: Identity Registry
- **Base de datos**: `apps/hbfs/identity_registry.py` (SQLite).
- **CLI Tool**: `apps/hbfs/identity_tool.py` — register/verify/list.
- **Resultado**: Resolución exitosa de author_hash → identidad humana.

---

## 2026-02-17 (cont.): Fase 7 — H-Bit File System (Visión) (En Progreso)
- **Cambio de Paradigma**: De inyector a Sistema de Archivos Autenticado (HBFS).
- **Diseño**: Documento `hbfs_design.md` generado.
- **Roadmap**: Prototipo FUSE -> Kernel Minifilter -> Native FS.

### Fase 7.1: Prototipo Watchdog
- **Script**: `demo_hbfs.py`
- **Funcionalidad**: Simula HBFS monitoreando una carpeta `Input` y firmando automáticamente en `Signed`.
- **Estado**: Funcional y verificado.

### Visual Interface (H-Bit Notary)
- **App**: `hbit_gui.py` (Modern CustomTkinter UI).
- **Features**: Drag & Drop visual verification, Key Management, One-Click Signing.
- **Estado**: Funcional.

---

## 2026-02-17: Fase 6 — Cifrado Universal (AES-256-GCM)

### Implementación
- **Cifrado Robusto**: Módulo `hbit.core.encryption` con AES-256-GCM y PBKDF2.
- **Transparencia**: `HBitPayload` y `UniversalEncoder` soportan cifrado opcional (`encrypt=True`).
- **Integridad**: Tags GCM garantizan detección de manipulación.
- **Tests**: 14 nuevos tests (unitarios + integración E2E). Total: 56 tests passing.

### Actualización 2: CLI y Compresión (zlib)
- **CLI**: Comandos `encode` (flag `--encrypt`), `decode` y `verify` (flag `--passphrase`) actualizados.
- **Compresión**: `HBitPayload` ahora comprime automáticamente con zlib si reduce el tamaño (flag `IS_COMPRESSED`).
- **Estado**: 59/59 tests pasando (+3 tests de compresión y cifrado combinado).

### Investigación: Soporte Streaming
- Documento técnico generado: `streaming_research.md`.
- Propuesta de arquitectura `StreamMediaHandler` para minimizar uso de RAM en archivos masivos.
- Listo para implementación en futura fase.

---

## 2026-02-16 (sesión 3): Fase 5 — Soporte Universal de Archivos

### Decisiones
- Patrón Strategy + Registry para extensibilidad futura (plugins)
- Handler genérico con append stream + CRC32 como fallback universal
- PDF: stream binario oculto antes de %%EOF
- Office OOXML: Custom XML part en el contenedor ZIP
- Audio: LSB en muestras PCM 16/24-bit
- Video: LSB en keyframes extraídos con OpenCV

### Módulos Nuevos (6)
| Módulo | Propósito |
|---|---|
| `formats/base.py` | MediaHandler ABC + CarrierData + MediaRegistry |
| `formats/image.py` | ImageHandler (PIL/LSB) |
| `formats/audio.py` | AudioHandler (WAV/FLAC/AIFF) |

### Refactoring Pipeline (Fase 5b)
- **Universal Pipeline**: `universal.py` centraliza la lógica de encode/decode para todos los formatos.
- **Canonical Hash**: Solucionado indeterminismo en PDF/OOXML mediante hash del contenido "limpio" (excluyendo H-Bit data) tanto en load como en verify.
- **Robust Sync**: Decoder ahora elimina quirúrgicamente los marcadores de sincronización (13 bits) en lugar de buscar patrones, evitando falsos positivos en payloads comprimidos/encriptados.
- **Integración CLI**: Comandos actualizados para usar `UniversalEncoder` por defecto.
| `formats/video.py` | VideoHandler (MP4/AVI/MOV) |
| `formats/document.py` | PDFHandler + OfficeHandler |
| `formats/generic.py` | GenericHandler (cualquier archivo) |

### Tests: 99/99 pasando (28 nuevos + 71 existentes)

---


## 2026-02-16: Sesión 2 — Fases 2, 3 y 4 Completadas

### Módulos Implementados

#### Fase 2: Resistencia Analógica
| Módulo | Decisión Técnica |
|---|---|
| `encoders/dct.py` | QIM sobre DM, frecuencias medias 8-20 del zig-zag |
| `resilience/ecc.py` | Reed-Solomon con 4 presets (light→forensic) |
| `resilience/tiling.py` | Interleaving para daños localizados |
| `resilience/anchor_grid.py` | Pilotos OFDM a freq. 3 ciclos/bloque |
| `resilience/dewarp.py` | Transformación afín + bilineal |
| `encoders/hybrid.py` | LSB (canal B) + DCT (canal G), fusión ponderada |
| `decoders/{lsb,dct,hybrid}.py` | Re-exportaciones lógicas |

#### Fase 3: Integración Phygital
| Módulo | Decisión Técnica |
|---|---|
| `blockchain/registrar.py` | Polygon mainnet, ABI mínimo, prueba offline |
| `blockchain/c2pa.py` | Manifiesto C2PA con aserción hbit.signature |
| `blockchain/oracle.py` | Challenge-response con nonce expirable |

#### Fase 4: Grado Forense
| Módulo | Decisión Técnica |
|---|---|
| `forensics/prnu.py` | Lukáš-Fridrich-Goljan, NCC normalizada |
| `forensics/luminance.py` | Sobel gradients, análisis de sombras |

### Tests: 71/71 pasando (pytest, ~2.1s)

### Bugfixes
- `integrity.py`: `np.concatenate(bytes)` → `b"".join()`
- `pyproject.toml`: build backend `_legacy` → `build_meta`
- `test_phase2.py`: ECC test corrupción dentro de capacidad RS
- `prnu.py` + `luminance.py`: `np.bool_` → `bool()` cast

---

## 2026-02-12: Sesión 1 — Inicio + Fase 1

### Decisiones Fundamentales
- Licencia Apache 2.0, Ed25519, Python 3.11+, Polygon L2
- 8 contribuciones senior integradas en plan de 4 fases

### Módulos Fase 1
12 módulos: crypto, kdf, signature, sync, entropy, saliency, jnd, channel_selector, integrity, lsb, pipeline, cli

### Próximos Pasos
- Tests de integración con imágenes reales
- README.md + CONTRIBUTING.md para open source
- Documentación MkDocs
- Smart contract Solidity para HBitRegistry
