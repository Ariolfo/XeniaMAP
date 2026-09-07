# Checkpoint — Roadmap Hexagonal + Modular

**Fecha:** 2026-09-07  
**Estado:** **H0 + H1 hechos.** Siguiente: **H2** (Clean-lite — dominio authz/estados).

## Dónde está el canvas

| Copia | Ruta |
|-------|------|
| **Canvas vivo (Cursor)** | `~/.cursor/projects/home-deep-Documentos-Personal-AC-fontagro-Yarqua-ws-yarqua/canvases/xeniamap-hexagonal-modular-roadmap.canvas.tsx` |
| **Backup en repo** | [`docs/ops/canvases/xeniamap-hexagonal-modular-roadmap.canvas.tsx`](canvases/xeniamap-hexagonal-modular-roadmap.canvas.tsx) |

## Decisión (recordatorio)

- **Hexagonal-first** sobre **monolito modular** (= hexagonal *dentro de* el monolito modular).
- **Clean-lite:** (1) UC como única orquestación, (2) dependencia hacia adentro, (3) dominio mínimo authz/estados.
- **No** entities/presenters/mappers en cada endpoint GIS.
- Camino: **A** (modular monolito) → Hex total (H5) → **B** (extractable) solo con trigger.

Formalizado en: [`adr-002-hexagonal-modular.md`](adr-002-hexagonal-modular.md).  
Owners: [`module_owners.md`](module_owners.md).

## Secuencia

`H0 ✓ → H1 ✓ → H2 → H3 → H4 → H5 → B1`

## H0 entregado

1. ~~ADR-002~~ → `docs/ops/adr-002-hexagonal-modular.md`
2. ~~DoD + regla imports en architecture~~ → `docs/architecture.md`
3. ~~Inventario owners~~ → `docs/ops/module_owners.md`

## H1 entregado

1. ~~Landing markdown → application~~ → `application/agro/landing_markdown.py` + thin routes en `preprocess.py`
2. ~~Rasters partidos~~ → `api/v1/rasters.py` (mapa ~214 LOC) + `api/v1/rasters_admin.py` (browse/import ~596 LOC)
3. ~~FE espejo~~ → `frontend/src/features/{auth,agro,fire}` + `shared/map` (barrels; `App.jsx` importa desde features)
4. Tests UC landing + smoke routers rasters → `tests/test_landing_markdown_uc.py`

## Siguiente: H2

1. `domain/identity`: políticas publicado + ownership/share  
2. `domain/agro` + `domain/fire`: estados Project / FireOrder / StudyOrder + transiciones  
3. Routers sin `if role/status` de producto (delegar a dominio)  
4. Tests de políticas sin FastAPI  

## Relacionado

- Auditoría: canvas `xeniamap-architecture-audit.canvas.tsx`  
- Arquitectura: [`docs/architecture.md`](../architecture.md)  
- Docker: [`docker.md`](docker.md)
