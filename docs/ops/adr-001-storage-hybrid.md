# ADR-001: Hybrid spatial storage

**Status:** Accepted (F3)  
**Date:** 2026-09-06

## Context

XeniaMAP runs PostgreSQL with PostGIS (`init.sql` enables `postgis` + `postgis_raster`). Application geometry today is mostly **GeoJSON in JSON/JSONB columns** and **rasters on disk** (COG / GeoTIFF under `EXTERNAL_DATA_ROOT`), served via API and MapLibre. `layers.geom` and `raster_layers.rast` exist in SQL but are **not** mapped in the ORM.

We needed a clear choice: push everything into PostGIS now, stay JSON/disk-only, or hybrid.

## Decision

**Hybrid storage:**

| Kind | Where | Notes |
|------|--------|--------|
| Request / AOI polygons | JSON(B) on `study_orders` / `fire_orders` | Keep; simple CRUD and Celery payloads |
| Published map vectors | PostGIS `layers.geom` + MVT | Upload syncs geom; `GET .../tiles/{z}/{x}/{y}.mvt` (`ST_AsMVT`); MapLibre `type: "vector"` when `mvt_ready` |
| Analysis rasters (S2, dNBR, severity, SoilPlus) | Disk COG + path metadata in DB | GDAL/rasterio; XYZ PNG tiles from file, not `raster` type |
| Optional `layers.geom` / `raster_layers.rast` | SQL present, ORM unmapped | Intentional until a product path uses them |

## Consequences

- Bootstrap stays Postgres+PostGIS image even while most app I/O is file + JSON.
- Do not block product work on migrating all AOIs into `geometry` columns.
- Next storage work: done for published Agro vectors — see `application/agro/layer_mvt.py`
  (`SyncLayerGeom`, `RenderLayerMvtTile`). AOI JSON and disk COG rasters unchanged.
  Fire dNBR/severity are rewritten as COG in `process_dnbr` (+ on-demand ensure for tiles).
- ORM still does **not** map `geom`/`rast` (raw SQL / PostGIS functions only).

## Non-goals

- Renaming Docker volume `bioagromap_postgres_data`.
- Rewriting historical AOI rows into PostGIS in this ADR.
