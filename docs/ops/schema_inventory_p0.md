# Schema inventory P0

**Updated:** 2026-09-06 (F3 bootstrap close)  
**Original compare:** 2026-09-05

Sources:

| Source | Path / method |
|--------|----------------|
| Live DB | `docker compose exec postgres psql` (as of original inventory) |
| ORM | `backend/app/models/models.py` |
| Alembic | `backend/alembic/versions/*.py` |
| Bootstrap SQL | `infrastructure/postgres/init.sql` |

**Alembic head:** `20260906_projects_module`  
**Chain:** `20260714_landing_texts` → `20260904_fire_orders` → `20260905_fire_orders_pipeline` → `20260906_projects_module`

**Bootstrap path:** [`bootstrap.md`](bootstrap.md) — `init.sql` (cold start) + always `alembic upgrade head`.

Scope: application tables in `public` only. PostGIS system catalogs out of scope.

---

## Summary table

| Table | In init.sql | In Alembic | In ORM | Notes |
|-------|:-----------:|:----------:|:------:|-------|
| `tenants` | yes | no | yes | Bootstrap DDL |
| `users` | yes | no | yes | |
| `user_audit_log` | yes | no | yes | |
| `projects` | yes | `module` via `20260906` | yes | `module` + `ix_projects_module` in init |
| `study_orders` | yes | no | yes | Created **after** `projects` (FK order fixed) |
| `fire_orders` | **yes** (full pipeline) | `20260904` + `20260905` | yes | Init + Alembic overlap; creates are idempotent |
| `project_shares` | yes | no | yes | |
| `project_processing_log` | yes | no | yes | |
| `layers` | yes | no | yes | PostGIS `geom` in SQL; not in ORM |
| `raster_layers` | yes | no | yes | PostGIS `rast` in SQL; not in ORM |
| `ai_results` | yes | no | yes | |
| `project_landing_texts` | yes | `20260714` (idempotent) | yes | |
| `alembic_version` | no | runtime | no | |

---

## F3 bootstrap status (2026-09-06)

| Gap (original inventory) | Resolution |
|--------------------------|------------|
| `projects.module` missing from init + Alembic | Alembic `20260906` + mirrored in `init.sql` |
| `fire_orders` absent from init | Added full table to `init.sql` |
| `study_orders` before `projects` | Reordered in `init.sql` |
| Triple path `ensure_fire_orders.py` | Script deprecated → wraps `alembic upgrade head` |
| PostGIS vs JSON decision | [`adr-001-storage-hybrid.md`](adr-001-storage-hybrid.md) |

---

## fire_orders

Init ships the full ORM shape (including pipeline columns from `20260905`).  
`20260904` no-ops if the table exists; `20260905` adds any missing columns/FK/index.

---

## PostGIS columns vs ORM

`layers.geom` is populated by `SyncLayerGeom` (raw SQL) and served as MVT; still **not** mapped on the SQLAlchemy `Layer` model. `raster_layers.rast` remains unused.

---

## Explicit non-goals (unchanged)

- Did **not** rename Docker volume `bioagromap_postgres_data`.
- Did **not** migrate host paths `/data_bioagro` → rename-only docs elsewhere.
- Did **not** inventory PostGIS `tiger` / `topology` beyond noting image defaults.

---

## Quick reference: public app tables

`ai_results`, `alembic_version`, `fire_orders`, `layers`, `project_landing_texts`, `project_processing_log`, `project_shares`, `projects`, `raster_layers`, `study_orders`, `tenants`, `user_audit_log`, `users`
