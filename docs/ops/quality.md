# Calidad (F7) — CI, lint, métricas, docs

Workflow: [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml)

## CI jobs

| Job | Qué hace |
|-----|----------|
| `backend-lint` | `ruff check app tests` |
| `backend-tests` | PostGIS + `init.sql` + Alembic + `pytest` con **coverage `app.application` ≥ 18%** |
| `frontend-lint` | ESLint de todo `src/**/*.{js,jsx}` (`--max-warnings 50`) |
| `frontend-build` | `npm ci && npm run build` |
| `docs-check` | Docs obligatorias + menciones F7 /metrics |

`SECRET_KEY` y `OTP_SIMULATE=1` se inyectan en el workflow (nunca defaults inseguros de settings).

## Local

```bash
# Backend
cd backend
pip install -r requirements.txt -r requirements-dev.txt
export SECRET_KEY=dev-local-xeniamap-change-me OTP_SIMULATE=1
ruff check app tests
lint-imports
pytest -q --cov=app.application --cov-config=.coveragerc --cov-fail-under=18

# Frontend
cd frontend
npm ci
npm run lint
npm run build
```

## Coverage (`application/`)

- Config: [`backend/.coveragerc`](../../backend/.coveragerc) — mide `app/application`.
- Umbral CI actual: **18%** (H5; subir hacia 25%+ con inventarios S1/PS).
- **import-linter** (`backend/pyproject.toml`): `domain` sin FastAPI/SQLAlchemy/pandas/…; `application` sin `fastapi`/`app.api`. CI: `lint-imports`.
- Módulos aún fríos (0% o casi): `soilplus`, `time_series`, `s1_inventory`, `ps_planet`, pipelines Fire `process_dnbr` / `download_s2`.

## ESLint

- Flat config: [`frontend/eslint.config.js`](../../frontend/eslint.config.js).
- Ámbito: **todo `src/`** (antes solo mapa / Fire lazy / geo).
- `eslint-plugin-react` (`jsx-uses-vars`) para que JSX cuente usos.
- `react-hooks/exhaustive-deps` en **warn** (polls Celery / galerías); tope 50 warnings en CI.

## Métricas

- FastAPI expone **Prometheus** en `GET /metrics` (`prometheus_fastapi_instrumentator` en `app/main.py`).
- Health: `GET /health` → `{"status":"ok"}`.
- Compose: servicio `prometheus` scrapea API y worker — ver [`infrastructure/prometheus.yml`](../../infrastructure/prometheus.yml).
- Grafana (compose) puede apuntar a Prometheus; dashboards de producto no están versionados aún.

### Métricas de producto

| Métrica | Dónde | Labels |
|---------|--------|--------|
| `xeniamap_firms_live_cache_total` | API (`live_cache`) | `result`=`hit`\|`miss`\|`stale_hit`\|`stale_miss`\|`disabled` |
| `xeniamap_celery_tasks_enqueued_total` | API (`celery_task_registry`) | `task` |
| `xeniamap_celery_tasks_total` | Worker (signals Celery) | `task`, `state` |
| `xeniamap_celery_task_duration_seconds` | Worker | `task` (histogram) |

Worker: HTTP metrics en `:9101` (`CELERY_METRICS_PORT`). Rate de hit FIRMS:

```promql
sum(rate(xeniamap_firms_live_cache_total{result="hit"}[5m]))
/
sum(rate(xeniamap_firms_live_cache_total{result=~"hit|miss"}[5m]))
```

### Scrapes recomendados

| Target | Path | Notas |
|--------|------|--------|
| backend:8000 | `/metrics` | HTTP + FIRMS cache + Celery enqueue |
| worker:9101 | `/metrics` | duración / estado tareas Celery |
| backend:8000 | `/health` | liveness (no Prometheus; probe k8s/compose) |

## Docs de arquitectura

Fuente: [`docs/architecture.md`](../architecture.md) — capas hexagonal, fases F0–F7, bootstrap BD, thin routers, GIS.

Ops relacionados:

- [`bootstrap.md`](bootstrap.md) — init + Alembic
- [`docker.md`](docker.md) — imágenes prebuilt (sin pip/npm en cada up)
- [`adr-001-storage-hybrid.md`](adr-001-storage-hybrid.md) — PostGIS vs disco/COG
- [`adr-002-hexagonal-modular.md`](adr-002-hexagonal-modular.md) — Hexagonal-first + Clean-lite (H0)
- [`module_owners.md`](module_owners.md) — owners Identity / Agro / Fire / Shared GIS
- [`legacy_names.md`](legacy_names.md) — volumen Postgres legacy
- [`permissions_cliente.md`](permissions_cliente.md) — matriz cliente/admin
- [`hexagonal_modular_roadmap_checkpoint_2026-09-06.md`](hexagonal_modular_roadmap_checkpoint_2026-09-06.md) — fases H0→B1

## Ampliaciones futuras (fuera del gate actual)

1. `ruff format --check` en todo `app/` (hoy varios archivos divergen).
2. Subir umbral coverage `application/` (p. ej. 25%+) y cubrir inventarios S1/PS.
3. Bajar `max-warnings` ESLint hacia 0 (exhaustivo deps).
4. Dashboards Grafana para FIRMS hit-rate y Celery p95.

## Middleware cliente `/raster`

Allowlist: solo `GET /api/v1/raster/{digits}` y `.../{digits}/preview`. Browse/inventory → **403** en middleware. Detalle: [`permissions_cliente.md`](permissions_cliente.md).

## MVT / PostGIS (vectores Agro)

- UC: `app/application/agro/layer_mvt.py`
- Endpoints: upload sync, `POST .../sync-geom`, `GET .../tiles/{z}/{x}/{y}.mvt`
- Frontend: `layerMvt.js` + `usePaintLayerOnMap` (`type: "vector"`) cuando `mvt_ready`
- Detalle ADR: [`adr-001-storage-hybrid.md`](adr-001-storage-hybrid.md)
