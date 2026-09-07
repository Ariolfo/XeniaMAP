# Checkpoint — Roadmap Hexagonal + Modular

**Fecha:** 2026-09-06  
**Estado:** Guardado para retomar. **Sin implementación de H0–B1 aún.**

## Dónde está el canvas

| Copia | Ruta |
|-------|------|
| **Canvas vivo (Cursor)** | `~/.cursor/projects/home-deep-Documentos-Personal-AC-fontagro-Yarqua-ws-yarqua/canvases/xeniamap-hexagonal-modular-roadmap.canvas.tsx` |
| **Backup en repo** | [`docs/ops/canvases/xeniamap-hexagonal-modular-roadmap.canvas.tsx`](canvases/xeniamap-hexagonal-modular-roadmap.canvas.tsx) |

Abrir en Cursor: canvas **XeniaMAP — Roadmap Hexagonal + Modular**.

## Decisión (recordatorio)

- **Hexagonal-first** sobre **monolito modular** (= hexagonal *dentro de* el monolito modular, no en su lugar).
- **Clean-lite:** (1) UC como única orquestación, (2) dependencia hacia adentro, (3) dominio mínimo authz/estados.
- **No** entities/presenters/mappers en cada endpoint GIS.
- Camino: **A** (modular monolito) → Hex total (H5) → **B** (extractable) solo con trigger.

## Secuencia

`H0 → H1 → H2 → H3 → H4 → H5 → B1`

## Mañana: arrancar en H0

1. Redactar ADR-002 Hexagonal-first + Clean-lite + Modular A/B  
2. Actualizar `docs/architecture.md` (DoD + regla de imports)  
3. Inventario owners Identity / Agro / Fire / Shared GIS  

## Relacionado

- Auditoría previa: canvas `xeniamap-architecture-audit.canvas.tsx`  
- Arquitectura actual: [`docs/architecture.md`](../architecture.md)  
- Docker prebuilt: [`docs/ops/docker.md`](docker.md)
