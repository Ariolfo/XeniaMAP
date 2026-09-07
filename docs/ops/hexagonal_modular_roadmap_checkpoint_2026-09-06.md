# Checkpoint — Roadmap Hexagonal + Modular

**Fecha:** 2026-09-07  
**Estado:** **H0–H5 hechos.** Siguiente: **B1** solo con trigger operativo (extraer BC).

## Dónde está el canvas

| Copia | Ruta |
|-------|------|
| **Canvas vivo (Cursor)** | `~/.cursor/projects/home-deep-Documentos-Personal-AC-fontagro-Yarqua-ws-yarqua/canvases/xeniamap-hexagonal-modular-roadmap.canvas.tsx` |
| **Backup en repo** | [`docs/ops/canvases/xeniamap-hexagonal-modular-roadmap.canvas.tsx`](canvases/xeniamap-hexagonal-modular-roadmap.canvas.tsx) |

## Secuencia

`H0 ✓ → H1 ✓ → H2 ✓ → H3 ✓ → H4 ✓ → H5 ✓ → B1`

## H5 entregado

| Ítem | Qué |
|------|-----|
| DTOs FIRMS | `FirmsHotspotRecord` en `domain/fire/ports.py`; adapter convierte DataFrame → records |
| TileRenderPort | `db: Any` opaco (sin Session en firma de puerto) |
| UoW / repos piloto | `domain/shared/uow.py`, `FireOrderRepository`; acceso Fire + `project_name` vía repos |
| import-linter | `backend/pyproject.toml` (`[tool.importlinter]`); CI `lint-imports` |
| Coverage | umbral `application/` **≥18%** |
| Docker | `Dockerfile` → `xeniamap-api:local`; `Dockerfile.worker` → `xeniamap-worker:local` |

### Residual H5 (documentado)

- Muchos UC aún reciben `Session` (download, rasters, MVT, pipeline_jobs, seed).
- `requirements-api.txt` / `requirements-worker.txt` aún delegan a `requirements.txt` compartido.

### Tests

`tests/test_h5_hex_total.py` (+ suites H3/H4 / FIRMS).

## Siguiente: B1 (solo con trigger)

Contratos extractables / colas agro·fire / límites de datos — **no** abrir sin necesidad operativa (SNAP, GPU SoilPlus, ingest CDSE).

## Relacionado

- Arquitectura: [`docs/architecture.md`](../architecture.md)  
- ADR: [`adr-002-hexagonal-modular.md`](adr-002-hexagonal-modular.md)  
- Calidad: [`quality.md`](quality.md) · Docker: [`docker.md`](docker.md)
