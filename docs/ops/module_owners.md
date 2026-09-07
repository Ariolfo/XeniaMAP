# Module owners (bounded contexts)

**Fecha:** 2026-09-07 (H0–H1)  
**ADR:** [`adr-002-hexagonal-modular.md`](adr-002-hexagonal-modular.md)

Owners below are **code ownership for PRs and triage**, not org titles. Until named people are assigned, the default owner is the **module path** — reviewers should prefer that context’s maintainers.

## Contexts

| Context | Backend (primary) | Frontend (primary) | Celery / jobs | Notes |
|---------|-------------------|--------------------|---------------|--------|
| **Identity** | `api/v1/auth.py`, `api/deps.py`, `core/security.py`, `core/otp_store.py`, `core/mail.py`, middleware allowlist in `main.py` | `features/auth`, `hooks/useAuthSession.js`, `components/AuthPanel.jsx` | — | Authz policies → move to `domain/identity` in **H2** |
| **Agro** | `application/agro/*` (incl. `landing_markdown`), `api/v1/preprocess.py`, `rasters.py` (mapa), `rasters_admin.py` (browse/import), `soilplus.py`, `layers.py` (MVT), `projects.py` / `study_orders.py` | `features/agro`, hooks preprocess/workspace, `PreprocessPanel.jsx` | `tasks/jobs.py` (Agro tasks) | SoilPlus still fat; preprocess.py aún gordo |
| **Fire** | `application/fire/*`, `api/v1/fire_orders.py`, `modules/fire/*` (pipelines only) | `features/fire`, `hooks/useFireMap.js`, `components/fire/*` | `tasks/fire_jobs.py` (`tasks.fire_*` names stable) | Heavy logic in `modules/fire/process_dnbr.py` etc. |
| **Shared GIS** | `services/*` (raster, sentinel, clip, clustering algorithms), `infrastructure/raster/*`, `infrastructure/cdse/*`, `infrastructure/firms/*` | `shared/map`, `map/LayerStore.js`, paint/map hooks | Shared by Agro/Fire workers | Algorithms stay in `services/`; I/O adapters in `infrastructure/` |

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
