# Pilot — Module Plan

## Objective
Validar H-Bit en productos reales de hardware con partners de la industria fotográfica y almacenamiento.

## Architecture
- **Hardware piloto:** 2-3 dispositivos (cámara + USB/tarjeta) con firmware H-Bit integrado
- **Chain of Trust:** firma al capturar → firma al escribir → verificación al leer
- **Testing en campo:** fotógrafos profesionales, productoras, agencias
- **Certificación:** sello "H-Bit Ready" para dispositivos compatibles

## Tasks

### Phase 3.1: Identificar Partners
- [ ] Lista de 10+ potenciales partners (cámaras, USBs, tarjetas)
- [ ] Priorizar: empresa de gama media con flexibilidad para pilot (no Samsung/Canon directo al inicio)
- [ ] Contactar: email + LinkedIn + eventos de industria
- [ ] Propuesta de valor: diferenciación de producto, seguridad de contenido, mercado premium
- [ ] NDA + acuerdo de pilot (3 meses)

### Phase 3.2: Integración Firmware
- [ ] Adaptar SDK FTL al hardware seleccionado
- [ ] Implementar `hbit_sign()` en momento de captura (cámara) y escritura (USB/tarjeta)
- [ ] Implementar chain of trust: metadatos EXIF + firma H-Bit
- [ ] Testing de rendimiento: latencia de firma <1ms
- [ ] Testing de resistencia: firma sobrevive compresión JPEG, redimensionado, transferencia

### Phase 3.3: Testing en Campo
- [ ] Seleccionar 5-10 fotógrafos/productoras beta testers
- [ ] Distribuir dispositivos piloto + guía de uso
- [ ] Recopilar feedback: usabilidad, rendimiento, confiabilidad
- [ ] Iterar Spec + SDK basado en feedback
- [ ] Casos de uso documentados: periodismo, moda, arquitectura, eventos

### Phase 3.4: Certificación "H-Bit Ready"
- [ ] Definir criterios de certificación (Spec compliance, rendimiento, seguridad)
- [ ] Crear sello/logo "H-Bit Ready"
- [ ] Documentación para fabricantes: cómo certificar su producto
- [ ] Lanzamiento público del producto certificado
- [ ] Press release + artículo en medios de industria

## Observations
- [2026-04-24] El pilot es el momento de verdad: si el hardware no soporta la latencia de firma, hay que optimizar.
- [2026-04-24] Fotógrafos profesionales son los early adopters perfectos: valoran la autenticidad y tienen presupuesto.
- [2026-04-24] Periodismo y documentales son el segundo mercado natural: necesitan prueba de procedencia.

## Completed
- [2026-04-24] Module plan creado
