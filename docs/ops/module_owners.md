# Module owners (bounded contexts)

**Fecha:** 2026-09-07 (H0–H1)  
**ADR:** [`adr-002-hexagonal-modular.md`](adr-002-hexagonal-modular.md)

Owners below are **code ownership for PRs and triage**, not org titles. Until named people are assigned, the default owner is the **module path** — reviewers should prefer that context’s maintainers.

## Contexts

| Context | Backend (primary) | Frontend (primary) | Celery / jobs | Notes |
|---------|-------------------|--------------------|---------------|--------|
| **Identity** | `domain/identity/*`, `api/v1/auth.py`, `api/deps.py` (glue), `core/security.py`, OTP/mail | `features/auth`, `hooks/useAuthSession.js`, `components/AuthPanel.jsx` | — | Políticas authz en dominio (H2); deps solo HTTP/DB |
| **Agro** | `domain/agro/*` (estados Project/StudyOrder), `application/agro/*`, `api/v1/preprocess.py`, `rasters.py` / `rasters_admin.py`, `soilplus.py`, `layers.py`, `projects.py` / `study_orders.py` | `features/agro`, hooks preprocess/workspace, `PreprocessPanel.jsx` | Cola **`agro`** · `tasks/jobs.py` · compose `worker-agro` | SoilPlus still fat; preprocess.py aún gordo |
| **Fire** | `domain/fire/*`, `application/fire/*` (incl. `pipeline_jobs`), `api/v1/fire_orders.py` (sin modules), `modules/fire/*` (pipelines only) | `features/fire`, `hooks/useFireMap.js`, `components/fire/*` | Cola **`fire`** · `tasks/fire_jobs.py` · compose `worker-fire` (`tasks.fire_*` stable) | dNBR/FIRMS viven en modules; entrada solo application |
| **Shared GIS** | `domain/shared/ports.py` (JobQueue/Storage/Tiles/Mail/Repo), `services/*` (algoritmos), `infrastructure/*` | `shared/map`, `map/LayerStore.js`, paint/map hooks | Shared by Agro/Fire workers | H3: I/O vía ports; algoritmos en `services/` |

## Cross-cutting (not a BC)

| Area | Paths | Rule |
|------|-------|------|
| Ops / docs | `docs/ops/*`, `docs/architecture.md`, compose, CI | Any BC may update when touching their surface |
| Metrics | `core/metrics.py`, worker `:9101`, Prometheus | Prefer Shared / Identity for HTTP; Fire for FIRMS labels |
| Task registry | `core/celery_task_registry.py` | Agro + Fire enqueue sites must register `task_id→tenant` |

## H0 checklist for owners

- [ ] New Agro feature → PR touches `application/agro` first, not only `preprocess.py`
- [ ] New Fire feature → PR touches `application/fire`; do not grow `modules/fire` with product rules
- [ ] Authz change → Identity (+ update [`permissions_cliente.md`](permissions_cliente.md))
- [ ] Map paint / LayerStore → Shared GIS

## Assigning people (optional)

When the team grows, add a column `Owner` (GitHub handle) per context in this table. Until then, path ownership is enough for H0 exit.
