# Arquitectura XeniaMAP (monolito modular + hexagonal)

El producto es un **monolito desplegable** (FastAPI + Celery + React).  
Estilo rector (**H0**): **Hexagonal-first + Clean-lite** *dentro* del monolito modular — ver ADR:

→ [`ops/adr-002-hexagonal-modular.md`](ops/adr-002-hexagonal-modular.md)

Owners por contexto: [`ops/module_owners.md`](ops/module_owners.md).  
Roadmap H0→B1: [`ops/hexagonal_modular_roadmap_checkpoint_2026-09-06.md`](ops/hexagonal_modular_roadmap_checkpoint_2026-09-06.md).

## Capas backend

```text
app/
  domain/           # Puertos e invariantes (sin FastAPI/SQLAlchemy)
  application/      # Casos de uso (orquestan puertos) — única orquestación nueva
  infrastructure/   # Adaptadores (NASA FIRMS, CDSE, disco, …)
  api/v1/           # Entrega HTTP (thin controllers)
  modules/fire/     # Pipelines legacy (dNBR/scripts) + facades de compat
  services/         # Algoritmos GIS compartidos (migrar I/O gradualmente)
  tasks/            # Celery → llama application/
```

### Regla de imports (código nuevo)

| Permitido | Evitar en código nuevo |
|-----------|-------------------------|
| `api` / `tasks` → `application` | `api` → `services` o `modules` (legado hasta H1/H4) |
| `application` → `domain` ports + GIS puro en `services/` | `domain` → FastAPI / SQLAlchemy / Celery |
| `infrastructure` implementa ports | `infrastructure` → `application` |
| | `modules/fire` → `api` |

Detalle y DoD de PR: **ADR-002**.

### Definition of Done (feature)

1. Flujo expuesto vía **use case** en `application/`.
2. Router/task **delgado** (auth, validar, llamar UC).
3. I/O externo nuevo → **port** + **adapter** (o justificación de legado).
4. Test de UC / mock de port si la lógica no es trivial.
5. Sin reglas de producto nuevas en `api/` ni `modules/fire/` (salvo mecánica de pipeline).

## Hexagonal ya cableado (ejemplos)

### Dominio mínimo authz / estados (H2)

1. `domain/identity/policies.py` — publicado, ownership/share, delete, fire access  
2. `domain/agro/{project,study_order}_status.py` — vocabulario + transiciones + efectos  
3. `domain/fire/order_status.py` — estados Fire + pipeline vs admin  
4. `api/deps.py` / patch status / enqueue Fire — solo glue; tests en `tests/test_domain_policies_h2.py`

### Puertos núcleo (H3)

1. `domain/shared/ports.py` — `ProjectRepository`, `RasterStoragePort`, `JobQueuePort`, `TileRenderPort`, `MailPort` (+ CDSE)  
2. Adapters en `infrastructure/{persistence,storage,jobs,mail,raster}/`  
3. `infrastructure/composition.py` — defaults; UC aceptan inyección  
4. Pilotos: landing MD, S2 download, Fire enqueue/tiles, MVT, notify mail  
5. Tests con mocks: `tests/test_h3_core_ports.py`

### Pipelines detrás de application (H4)

1. `application/fire/pipeline_jobs.py` — worker Fire (download/dNBR/FIRMS); `tasks/fire_jobs.py` solo dispatch  
2. Wrappers: `validate_firms`, `aoi`, `project_link`, `seed` — **api sin `modules.fire`**  
3. Agro pilotos: `RunSentinel2DownloadJob`, `RunLandingMarkdownJob`  
4. `modules.fire.process_dnbr` permanece (algoritmo); entrada única = UC  
5. Tests: `tests/test_h4_fire_pipelines.py`

### FIRMS live

1. `domain/fire/ports.py` → `FirmsHotspotPort`
2. `application/fire/firms_live.py` → `GetFirmsLiveHotspots`
3. `infrastructure/firms/nasa_firms_adapter.py` → `NasaFirmsAreaAdapter`
4. `infrastructure/firms/live_cache.py` → Redis/memoria TTL (`firms_live_cache_ttl_sec`, default 300s)
5. `api/v1/fire_orders.py` → use case + cache (`cached: true/false` en respuesta)

`modules/fire/firms_live.fetch_firms_live` permanece como facade.

### Fire map UX (sprint YA + COG/tiles)

- **Lazy GeoJSON / preview**: stubs en catálogo; hidratar al activar / `default_on`.
- **Preview por URL**: `format=png|meta` (evitar `png_base64` en React).
- **XYZ tiles**: `GET .../results/tiles/{z}/{x}/{y}.png` (`infrastructure/raster/xyz_tiles.py`).
  MapLibre `raster` source + Bearer vía `transformRequest`.
- **Basemap sin `setStyle`**: `applyBasemap()` en `frontend/src/utils/geo.js`.
- **FIRMS live**: cache Redis/memoria TTL + **stale** 24h si NASA falla (`stale: true`).

### F6 GIS

- **LayerStore**: `frontend/src/map/LayerStore.js` + `useMapLayers` (descriptores únicos).
- **COG**: `infrastructure/raster/cog.py` — dNBR/severity a COG al final de `process_dnbr`;
  ensure bajo demanda al servir XYZ (órdenes antiguas).
- **FIRMS estable**: `get_firms_live_stale` / respuesta degradada en API.

### Auth (F0) / Limpieza (F1) / Frontend (F5)

- F0: `ADMIN_EMAILS`, OTP SMTP o `OTP_SIMULATE`, `SECRET_KEY` en CI.
- F1: sin session/events `bioagromap_*`; sin `logo-bioagro` / Mapbox token;
  `ai_service` solo con `--profile ai`; volumen Postgres legacy documentado
  en [`ops/legacy_names.md`](ops/legacy_names.md).
- F5: `App.jsx` orquesta; lógica en hooks:
  - `hooks/useAuthSession.js` — login/OTP/logout/restore
  - `hooks/useFireMap.js` — lazy layers Fire + toggles
  - `hooks/useProjectWorkspace.js` — proyectos Agro en mapa
  - `hooks/usePreprocessJobs.js` — descarga / recorte / stacks / clusters (+ polls Celery)
  - `hooks/usePaintLayerOnMap.js` — paint GeoJSON compartido
  - `utils/userRole.js` — `normalizeUserRole` / legado S2 bands

### CDSE (Copernicus)

1. `domain/shared/ports.py` → `CdseAuthPort`
2. `infrastructure/cdse/client.py` → helpers OData/STAC + `CdseAuthAdapter`
3. `services/cdse_client.py` → facade de reexport
4. DI: `sentinel2.get_copernicus_*` / `search_and_download_monthly(..., auth=)` y
   `modules.fire.download_s2` / `DownloadFireS2` aceptan `CdseAuthPort` (default adapter)

### Fire download / dNBR

1. `application/fire/download_s2.py` → `DownloadFireS2` (inyecta `CdseAuthPort`)
2. `application/fire/process_dnbr.py` → `ProcessDnbrPipeline`
3. `tasks/fire_jobs.py` → llama use cases (nombres Celery `tasks.fire_*` estables)

La lógica pesada sigue en `modules/fire/*`; los use cases son el punto de entrada hexagonal.

### Agro (extracción gradual desde preprocess)

1. `application/agro/agroclimate.py` → Open-Meteo diario / medias mensuales
2. `application/agro/download.py` → S2/S1 download + stub + poll de status
3. `application/agro/indices.py` → índice simple + enqueue stacks S2
4. `application/agro/crop_recortes.py` → crop centro + enqueue recortes S1/S2
5. `application/agro/ps_planet.py` → ZIP extract, inventario TIF, recorte clip, ST cluster
6. `application/agro/time_series.py` → vegetación, SAR S1, agroclima de proyecto
7. `application/agro/s1_inventory.py` → inventarios/previews preproceso + s1indices
8. `application/agro/optical_inventory.py` → inventarios/previews stacks ópticos (indices/indecesPS)
9. `application/agro/recortes_inventory.py` → inventarios/previews recortes/recortesPS
10. `api/v1/soilplus.py` → SoilPlus + dashboard IA Planet (router dedicado)
11. `api/v1/preprocess.py` → wrappers HTTP restantes (landing markdown aún inline)
12. Celery: `core/celery_task_registry.py` registra `task_id→tenant` al encolar; `GET /preprocess/task-status/{id}` exige match de tenant

### Frontend hooks preprocess

- `usePreprocessJobs.js` — composer
- `useSentinelDownloads.js` — S1/S2 download + poll
- `usePreprocessCeleryJobs.js` — recortes / stacks / PS extract + poll
- `useClusterAnalysisJobs.js` — elbow / GMM / persistidos

## Disco externo

Host: `/mnt/disco3tb/Data_XeniaMap` → contenedor `/data_xeniamap` (`EXTERNAL_DATA_ROOT`).

El volumen Docker de Postgres conserva el nombre legacy `bioagromap_postgres_data` para no perder datos.

## Base de datos (F3 bootstrap)

- Cold start: `infrastructure/postgres/init.sql` (incluye `projects.module` + `fire_orders`).
- Siempre: `alembic upgrade head` — ver [`ops/bootstrap.md`](ops/bootstrap.md).
- Storage espacial: híbrido JSON/disco + PostGIS para vectores de mapa — [`ops/adr-001-storage-hybrid.md`](ops/adr-001-storage-hybrid.md).

## Thin routers (F2)

| Router | Application / modules |
|--------|------------------------|
| `api/v1/fire_orders.py` | `application/fire/*` + `modules/fire` |
| `api/v1/soilplus.py` | `application/agro/soilplus.py` (thin HTTP) |
| `api/v1/rasters.py` | `application/agro/rasters.py` (paths, scans, delete, **upload-raster**) |
| `api/v1/preprocess.py` | `application/agro/*` (ya cableado; no partir más a ciegas) |

Fronteras de módulo: `modules/{agro,fire,shared}` (Fire con pipelines; Agro/Shared como marcadores de dominio).

Permisos cliente (dashboard / admin browse): [`ops/permissions_cliente.md`](ops/permissions_cliente.md).

## Calidad (F7)

- CI: `.github/workflows/ci.yml` — ruff, pytest, eslint (núcleo mapa), vite build, docs-check.
- Guía: [`ops/quality.md`](ops/quality.md).
- Métricas: `GET /metrics` (HTTP + FIRMS cache + Celery enqueue) y worker `:9101` (duración/estado Celery); scrape en `infrastructure/prometheus.yml`.

## Roadmap de fases (audit F0–F7)

| Fase | Estado |
|------|--------|
| F0 Seguridad | Hecho |
| F1 Limpieza | Hecho |
| F2 Thin routers | Hecho |
| F3 Bootstrap BD | Hecho |
| F5 Frontend hooks | Hecho |
| F6 GIS LayerStore/COG/FIRMS | Hecho |
| F7 Calidad CI/lint/métricas/docs | Hecho (ESLint `src/` + cov `application/` ≥18% + import-linter) |

## Roadmap hexagonal / modular (H0–B1)

| Fase | Estado |
|------|--------|
| **H0** Gobierno ADR-002 + DoD + owners | **Hecho** |
| **H1** Modular A (routers/FE legibles) | **Hecho** |
| **H2** Clean-lite dominio authz/estados | **Hecho** |
| **H3** Puertos núcleo (Repo, Storage, JobQueue, Tiles) | **Hecho** |
| **H4** Adelgazar pipelines/GIS | **Hecho** |
| **H5** Hex total en monolito (+ API/worker images) | **Hecho** (piloto Session→repos; deps API/worker aún compartidas) |
| B1 Extractable (contratos; solo con trigger) | Pendiente |

### Post-H5 residual (calidad / deuda)

1. `ruff format --check` en todo `app/`
2. Subir umbral coverage `application/` (hoy ≥18%; meta 25%+) y cubrir inventarios S1/PS
3. Bajar `max-warnings` ESLint hacia 0
4. Dashboards Grafana (FIRMS hit-rate / Celery p95)
5. Migrar UC residuales que aún reciben `Session` → `UnitOfWork` / repos (piloto Fire acceso ya en H5)
6. Separar deps reales en `requirements-api.txt` vs `requirements-worker.txt` (hoy ambos `-r requirements.txt`)

### Vectores publicados (MVT)

- Upload / `POST .../sync-geom` escribe `layers.geom` (EPSG:4326).
- `GET /api/v1/layers/{project_id}/{layer_id}/tiles/{z}/{x}/{y}.mvt` — `ST_AsMVT`, source-layer `published`.
- Catálogo `GET /layers/{project_id}` incluye `mvt_ready` + `bbox`; el mapa Agro usa tiles si están listos, GeoJSON si no.
