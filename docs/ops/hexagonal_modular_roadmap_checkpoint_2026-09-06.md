# Checkpoint — Roadmap Hexagonal + Modular

**Fecha:** 2026-09-07  
**Estado:** **H0–H5 + B1 + H6 hechos.** Extracción de microservicio: solo con trigger.

## Dónde está el canvas

| Copia | Ruta |
|-------|------|
| **Canvas vivo (Cursor)** | `~/.cursor/projects/home-deep-Documentos-Personal-AC-fontagro-Yarqua-ws-yarqua/canvases/xeniamap-hexagonal-modular-roadmap.canvas.tsx` |
| **Backup en repo** | [`docs/ops/canvases/xeniamap-hexagonal-modular-roadmap.canvas.tsx`](canvases/xeniamap-hexagonal-modular-roadmap.canvas.tsx) |

## Secuencia

`H0 ✓ → … → H5 ✓ → B1 ✓ → H6 ✓` · extracción BC con trigger

## H6 + residual + deuda fina entregado

| Ítem | Qué |
|------|-----|
| UoW / repos piloto H6 | Fire enqueue, Layer/RasterLayer get, boto3 solo worker |
| Residual Session→repos | downloads S1/S2/stub, MVT sync/meta/tiles, upload/delete raster |
| GIS API | lazy-import SoilPlus / cluster / preprocess rasterio |
| Deuda fina | Fire seed/project_link vía UoW; `recortes_inventory` → RasterLayerRepo; SoilPlus execute-save → Celery + FE poll |

### Aún fuera (no bloquea)

- Reescritura total de `modules.fire` seed/project_link sin Session (hoy envueltos por UoW)
- Extracción BC microservicio (solo con trigger SNAP/GPU/CDSE)
- Calidad: ruff format amplio, cov↑, ESLint max-warnings→0

## Relacionado

- B1 contratos: [`bounded_context_contracts.md`](bounded_context_contracts.md)  
- Datos: [`data_bounds.md`](data_bounds.md)  
- Docker: [`docker.md`](docker.md)
