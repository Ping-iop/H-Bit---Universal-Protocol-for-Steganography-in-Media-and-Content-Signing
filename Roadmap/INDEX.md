# H-Bit — Universal Protocol for Content Authenticity

## Objective
Establecer H-Bit como el estándar global de autenticidad digital: un formato universal de firma criptográfica + esteganografía que funcione en cualquier dispositivo (PC, USB, tarjeta de memoria, chip de fabricante) y verifique el origen del contenido (humano vs. IA) sin intervención manual.

## Modules
- [Spec & SDK](modules/spec-sdk/PLAN.md) — Whitepaper técnico + SDK en C/Rust para fabricantes
- [Verifier](modules/verifier/PLAN.md) — Verificador universal (CLI, Web, Mobile, Browser Extension)
- [Pilot](modules/pilot/PLAN.md) — Producto piloto con partners de hardware (cámaras/USBs)
- [Ecosystem](modules/ecosystem/PLAN.md) — Adopción, estandarización, partnerships industriales

## Current Status
- **Phase:** Phase 0 — Planning & Architecture
- **Last Update:** 2026-04-24
- **Next:** Definir Spec v1.0 y SDK architecture

## Key Decisions
- No reemplazar NTFS directamente: H-Bit se integra como capa overlay + spec de firmware.
- Formato universal: compatible con exFAT/FAT32/NTFS/SDCARD, no dependiente de un OS.
- Firma desde el fabricante: SDK para FTL (Flash Translation Layer) de controladores flash.
- Privacy-preserving: firmas zero-knowledge para no exponer identidad del creador.
- Stack criptográfico actual: Ed25519 + AES-256-GCM + HKDF + DCT (resistente a JPEG).
