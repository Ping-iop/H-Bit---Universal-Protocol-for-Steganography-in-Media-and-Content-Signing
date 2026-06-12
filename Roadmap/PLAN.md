# H-Bit — Roadmap Maestro

## Objective
Evolucionar H-Bit de librería Python a estándar industrial universal de autenticidad digital, integrado en hardware, firmware, OS y software.

## Architecture Overview
```
┌─────────────────────────────────────────────────────┐
│                  H-Bit Spec v1.0                    │
│  (Formato payload, algoritmos, API firmware)        │
├──────────┬──────────┬──────────┬────────────────────┤
│  SDK     │ Verifier │  Pilot   │    Ecosystem       │
│  (C/Rust)│ (Multi-  │ (HW      │ (Standa-           │
│          │  OS)     │  Partner)│  rización)          │
├──────────┴──────────┴──────────┴────────────────────┤
│         H-Bit Overlay FS (FUSE / Kernel)            │
│         └─ Compatible con exFAT / FAT32 / NTFS      │
├─────────────────────────────────────────────────────┤
│  Trust Anchor: Polygon/Arweave + Merkle Trees       │
└─────────────────────────────────────────────────────┘
```

## Phases

### Phase 0: Planning & Architecture (CURRENT)
- [x] Definir visión y alcance global
- [x] Validar viabilidad técnica (FTL, FUSE, drivers)
- [ ] Escribir Spec v1.0 draft (documento técnico)
- [ ] Definir estructura del SDK en C/Rust
- [ ] Definir arquitectura del Verifier universal

### Phase 1: Spec & SDK (6-8 semanas)
- [ ] Whitepaper técnico: formato de payload, algoritmos, API
- [ ] SDK Core en Rust: firma, verificación, esteganografía
- [ ] SDK FTL: API para controladores flash de fabricantes
- [ ] Tests de resistencia: compresión, recorte, redimensionado
- [ ] Publicar Spec v1.0 en GitHub (repo pública)
- [ ] Documentación para desarrolladores

### Phase 2: Verifier Universal (4-6 semanas)
- [ ] CLI `hbit-check` (Linux/Windows/macOS)
- [ ] Web Verifier (browser-based, WebAssembly)
- [ ] Mobile SDK (iOS/Android)
- [ ] Browser Extension (Chrome/Firefox) para verificación en web
- [ ] API REST para verificación masiva
- [ ] Dashboard web de verificación

### Phase 3: Pilot con Hardware (8-12 semanas)
- [ ] Identificar 2-3 partners potenciales (cámaras, USBs, tarjetas)
- [ ] Integrar SDK en firmware de dispositivo piloto
- [ ] Implementar chain of trust: firma al capturar → firma al escribir → verificación al leer
- [ ] Testing en campo con fotógrafos/productoras
- [ ] Feedback loop y ajustes al Spec
- [ ] Producto "H-Bit Ready" certificado

### Phase 4: Ecosystem & Adoption (ongoing)
- [ ] Presentar Spec a C2PA, W3C, ISO para estandarización
- [ ] SDK oficial para Samsung, SanDisk, Kingston, Lexar
- [ ] Integración con cámaras (Sony, Canon, Fujifilm)
- [ ] Plugin para Adobe Creative Cloud
- [ ] Browser native API (Chrome/Firefox/Safari)
- [ ] Comunidad: Discord, newsletter, eventos
- [ ] Modelo de negocio: SDK licensing, certification, enterprise

## Observations
- [2026-04-24] Visión del usuario: formato global pre-instalado en chips de fabricante, no solo software.
- [2026-04-24] No es un proyecto de código solo: requiere estandarización, partnerships y ecosistema.
- [2026-04-24] Privacidad es crítica: GDPR, anonimato, zero-knowledge proofs necesarios.
- [2026-04-24] Rendimiento: cada firma añade latencia. En firmware flash, <1ms es el objetivo.
- [2026-04-24] Industria primero: fotógrafos y productoras son los early adopters naturales.

## Completed
- [2026-04-24] Roadmap maestro creado con 4 fases y estructura de módulos
- [2026-04-24] Arquitectura validada: FTL SDK + Overlay FS + Universal Verifier
- [2026-04-24] Repositorio H-Bit Beta 1.0.0 validado (129/129 tests pasando)
