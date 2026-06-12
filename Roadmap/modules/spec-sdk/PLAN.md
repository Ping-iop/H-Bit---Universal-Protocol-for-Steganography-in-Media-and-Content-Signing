# Spec & SDK — Module Plan

## Objective
Crear el documento técnico oficial (Spec v1.0) y el SDK en C/Rust que cualquier fabricante o desarrollador puede integrar.

## Architecture
- **Spec v1.0:** Documento abierto con formato de payload, algoritmos criptográficos, API de firmware FTL
- **SDK Core (Rust):** Firma, verificación, esteganografía QIM/LSB, resistencia a compresión JPEG
- **SDK FTL (C):** API ligera para integrar en controladores flash de SSDs, USBs, tarjetas SD
- **Tests:** Suite de resistencia (compresión, recorte, redimensionado, re-encodificación)

## Tasks

### Phase 1.1: Spec v1.0 Draft
- [ ] Definir estructura del payload JSON (origin, author_hash, timestamp, device_id, integrity_chain)
- [ ] Definir algoritmos: Ed25519 signatures, AES-256-GCM encryption, HKDF key derivation
- [ ] Definir esteganografía: QIM (Quantization Index Modulation) + DCT para JPEG
- [ ] Definir API de firmware FTL: `hbit_sign(data, key)`, `hbit_verify(data, signature)`
- [ ] Escribir whitepaper técnico (10-15 páginas)
- [ ] Revisión por pares (comunidad + advisors)

### Phase 1.2: SDK Core (Rust)
- [ ] Crear repo público `hbit-sdk` con estructura Cargo
- [ ] Implementar `hbit::sign()` — firma contenido con Ed25519
- [ ] Implementar `hbit::verify()` — verifica firma + integridad
- [ ] Implementar `hbit::embed()` — esteganografía en imagen/audio/video
- [ ] Implementar `hbit::extract()` — extracción + verificación
- [ ] Implementar resistencia JPEG (DCT-based)
- [ ] Tests unitarios (target: 95% coverage)
- [ ] Benchmarks de rendimiento

### Phase 1.3: SDK FTL (C)
- [ ] API minimal: `hbit_flt_sign()`, `hbit_flt_verify()`
- [ ] Headers públicos + docs
- [ ] Ejemplo de integración en driver de flash genérico
- [ ] Compatibilidad: Linux kernel module, Windows WDF, Android HAL

### Phase 1.4: Publicación
- [ ] Publicar Spec v1.0 en GitHub (repo pública)
- [ ] Publicar SDK v0.1.0 en crates.io (Rust) + npm (bindings)
- [ ] Documentación: docs.rs + README + ejemplos
- [ ] Blog post + announcement

## Observations
- [2026-04-24] El Spec debe ser abierto y libre de royalties para adopción masiva.
- [2026-04-24] Rust para SDK Core por seguridad memory + performance. C para FTL por compatibilidad con drivers existentes.
- [2026-04-24] Necesitamos advisors: experto en criptografía, experto en flash storage, experto en industria fotográfica.

## Completed
- [2026-04-24] Module plan creado
