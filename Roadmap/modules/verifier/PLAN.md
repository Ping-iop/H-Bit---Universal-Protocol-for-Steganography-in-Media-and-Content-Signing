# Verifier Universal — Module Plan

## Objective
Crear herramientas de verificación accesibles para cualquier usuario, en cualquier plataforma.

## Architecture
- **CLI:** `hbit-check` — terminal para desarrolladores y profesionales
- **Web:** Verifier embebible en cualquier sitio web (WASM)
- **Mobile:** SDK nativo iOS/Android para apps
- **Browser Extension:** Verificación automática al cargar imágenes/videos
- **API REST:** Endpoint para verificación masiva (enterprise)

## Tasks

### Phase 2.1: CLI `hbit-check`
- [ ] CLI multi-OS (Linux/Windows/macOS) en Go o Rust
- [ ] Comandos: `hbit-check file.jpg`, `hbit-check --verbose`, `hbit-check --export-report`
- [ ] Output: origen, firma, timestamp, dispositivo, estado de integridad
- [ ] Integración con Trust Anchor (Polygon/Arweave)
- [ ] Tests + packaging (apt, brew, winget)

### Phase 2.2: Web Verifier (WASM)
- [ ] Portar SDK Core a WebAssembly
- [ ] Web app: drag & drop para verificar archivos
- [ ] API JavaScript: `HBit.verify(file)`
- [ ] Embeddable widget para sites de portfolios, agencias, marketplaces
- [ ] Tests en Chrome/Firefox/Safari/Edge

### Phase 2.3: Mobile SDK
- [ ] iOS SDK (Swift) — verificar fotos de cámara, exportar reportes
- [ ] Android SDK (Kotlin) — verificar fotos de cámara, exportar reportes
- [ ] React Native bindings
- [ ] Flutter bindings
- [ ] Ejemplo: app de cámara con firma automática

### Phase 2.4: Browser Extension
- [ ] Chrome extension: detecta imágenes en página, verifica automáticamente
- [ ] Firefox addon: mismo comportamiento
- [ ] Popup con resultado: ✓ Auténtico / ⚠ Modificado / ✗ No firmado
- [ ] Right-click context menu: "Verify with H-Bit"

### Phase 2.5: API REST + Dashboard
- [ ] API endpoint: `POST /verify` con file upload
- [ ] Batch verification: `POST /verify/batch` con array de files
- [ ] Dashboard web: historial de verificaciones, reportes, analytics
- [ ] Auth: API keys para enterprise

## Observations
- [2026-04-24] WASM es clave: permite ejecutar verificación en el browser sin server.
- [2026-04-24] La extension de browser es el vector de adopción más rápido para el público general.
- [2026-04-24] Mobile SDK debe integrarse con cámara nativa para firma al momento de capturar.

## Completed
- [2026-04-24] Module plan creado
