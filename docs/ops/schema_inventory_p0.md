# Schema inventory P0 (2026-09-05)

Sources compared:

| Source | Path / method |
|--------|----------------|
| Live DB | `docker compose exec postgres psql` → `\dt`, `information_schema.columns`, `\d` |
| ORM | `backend/app/models/models.py` (`__tablename__` + `Column`) |
| Alembic | `backend/alembic/versions/*.py` (3 revisions) |
| Bootstrap SQL | `infrastructure/postgres/init.sql` |

**Alembic head (live):** `20260905_fire_orders_pipeline`  
(`alembic_version.version_num`)

**Revision chain:** `20260714_landing_texts` → `20260904_fire_orders` → `20260905_fire_orders_pipeline`

Scope: application tables in `public` only. PostGIS system relations (`spatial_ref_sys`, `geometry_columns`, …), `tiger.*`, and `topology.*` are out of scope.

---

## Summary table: Table | In init.sql | In Alembic | In ORM | In live DB | Notes

| Table | In init.sql | In Alembic | In ORM | In live DB | Notes |
|-------|:-----------:|:----------:|:------:|:----------:|-------|
| `tenants` | yes | no | yes | yes | Aligned; bootstrap-only DDL |
| `users` | yes | no | yes | yes | Aligned (`role`, `full_name`, `is_active` via CREATE + ADD IF NOT EXISTS) |
| `user_audit_log` | yes | no | yes | yes | Aligned |
| `study_orders` | yes | no | yes | yes | Aligned columns; init CREATE references `projects` before `projects` is defined (ordering hazard on cold start) |
| `projects` | yes | no | yes | yes | **`module` missing from init + Alembic**; present in ORM + live (`DEFAULT 'agro'`, index `ix_projects_module`) |
| `project_shares` | yes | no | yes | yes | Aligned |
| `project_processing_log` | yes | no | yes | yes | Aligned |
| `layers` | yes | no | yes | yes | Live/init have PostGIS `geom`; ORM maps `metadata` as `layer_metadata`, no `geom` attribute |
| `raster_layers` | yes | no | yes | yes | Live/init have PostGIS `rast`; ORM maps `metadata` as `raster_metadata`, no `rast` attribute |
| `ai_results` | yes | no | yes | yes | Aligned columns; ORM default `status='queued'` not expressed as DB server default in init |
| `project_landing_texts` | yes | **create** (`20260714`) | yes | yes | Duplicated in init + Alembic; live matches ORM |
| `fire_orders` | **no** | **create** (`20260904`) + **alter** (`20260905`) | yes | yes | Not in init; live matches ORM after pipeline migration |
| `alembic_version` | no | (runtime) | no | yes | Version tracking only |

---

## fire_orders detail (columns missing from 20260904 vs model vs live; note 20260905 migration)

### Created by `20260904_fire_orders`

`id`, `tenant_id`, `created_by_user_id`, `request_name`, `department`, `applicant_name`, `applicant_email`, `applicant_phone`, `company`, `geometry_geojson`, `pre_start`, `pre_end`, `post_start`, `post_end`, `max_cloud_cover`, `status`, `download_task_id`, `download_message`, `download_manifest`, `data_root`, `source_key`, `extra_notes`, `created_at`

Indexes: `ix_fire_orders_tenant_id`, `ix_fire_orders_status`, `ix_fire_orders_source_key`, `ix_fire_orders_created_by_user_id`  
Unique: `uq_fire_orders_source_key` (live shows constraint name `fire_orders_source_key_key` — equivalent uniqueness)

### Columns **not** in 20260904 but required by ORM `FireOrder` (and present on live)

| Column | Type (ORM / live) | Added by |
|--------|-------------------|----------|
| `project_id` | `Integer` FK → `projects.id`, nullable | `20260905_fire_orders_pipeline` |
| `results_root` | `String(1024)`, nullable | `20260905` |
| `process_task_id` | `String(255)`, nullable | `20260905` |
| `process_message` | `Text`, nullable | `20260905` |
| `process_manifest` | `JSON`, nullable | `20260905` |
| `firms_task_id` | `String(255)`, nullable | `20260905` |
| `firms_message` | `Text`, nullable | `20260905` |
| `firms_manifest` | `JSON`, nullable | `20260905` |

`20260905` also adds `ix_fire_orders_project_id` and FK `fire_orders_project_id_fkey` (idempotent if already present).

### Live vs ORM (2026-09-05)

**Match:** all 31 ORM columns exist on live `fire_orders`. No ORM columns missing from live after head `20260905_fire_orders_pipeline`.

### init.sql

`fire_orders` is **absent**. A volume that only runs `init.sql` (no Alembic) will not have this table.

---

## projects.module status

| Check | Result |
|-------|--------|
| ORM | `Project.module = Column(String(32), nullable=False, default="agro", index=True)` |
| Live DB | Present: `character varying(32) NOT NULL DEFAULT 'agro'`, index `ix_projects_module` |
| `init.sql` | **Absent** — CREATE/ALTER for `projects` never add `module` |
| Alembic | **Absent** — no revision creates or alters `projects.module` |

**Implication:** current live DB was patched outside versioned bootstrap (manual SQL / ad-hoc / ORM create path). Fresh installs from `init.sql` alone (and DBs that never got the manual column) will diverge from ORM until a migration (or init update) is added. Recommended next step is a dedicated Alembic revision + mirror in `init.sql` (not implemented in this inventory).

---

## Gaps / recommended next migrations (do not implement them here)

1. **`projects.module`** — Add nullable→NOT NULL with default `'agro'` (or straight NOT NULL DEFAULT), plus index `ix_projects_module`; mirror in `init.sql`. Highest priority for module routing (agro | fire | og | ch4).
2. **`fire_orders` in `init.sql`** — Optional but useful so new environments that rely on init before Alembic are not missing Fire; at minimum document that Alembic through `20260905` is required for Fire.
3. **Keep Alembic as source of truth for Fire pipeline columns** — Do not rewrite `20260904`; leave additive `20260905` as the alignment path for older DBs.
4. **init.sql ordering** — `study_orders` CREATE currently references `projects(id)` before `projects` exists; reorder or drop FK from CREATE and rely on later `ALTER` for safer cold starts.
5. **PostGIS columns vs ORM** — `layers.geom` / `raster_layers.rast` exist in init + live but are not mapped in ORM. Acceptable if access is raw SQL/GDAL only; if the app needs them via ORM, add mapped columns (or document intentional omission).
6. **Alembic coverage of core tables** — Most app schema lives only in `init.sql`. New environments need both init **and** `alembic upgrade head`. Long-term: either expand Alembic for all app DDL or keep a single documented bootstrap path.

---

## Explicit non-goals

- Did **not** rename Docker volume `bioagromap_postgres_data`.
- Did **not** rename or migrate host/path `/data_bioagro`.
- Did **not** implement the recommended migrations above.
- Did **not** inventory PostGIS `tiger` / `topology` catalogs beyond noting they exist from the PostGIS image.

---

## Quick reference: live public app tables

`ai_results`, `alembic_version`, `fire_orders`, `layers`, `project_landing_texts`, `project_processing_log`, `project_shares`, `projects`, `raster_layers`, `study_orders`, `tenants`, `user_audit_log`, `users`  
(+ PostGIS `spatial_ref_sys` and extension views)
