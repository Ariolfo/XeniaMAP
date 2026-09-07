# Database bootstrap (F3)

Single documented path for schema on new and existing environments.

## Source of truth

| Layer | Role |
|-------|------|
| `infrastructure/postgres/init.sql` | **Cold start only** — Docker `docker-entrypoint-initdb.d` / empty volume. Creates core tables including `projects.module` and full `fire_orders`. |
| `backend/alembic/versions/*` | **Ongoing schema** — additive migrations; must reach `head` on every deploy. Idempotent where they overlap with init. |
| ORM `backend/app/models/models.py` | Application mapping; not a DDL runner (`Base.metadata.create_all` is not used at startup). |

**Do not** use ad-hoc DDL scripts to create app tables. The former `ensure_fire_orders.py` SQL path is retired; the file is a thin wrapper around Alembic.

## Required steps

### Docker (empty volume)

```bash
docker volume create bioagromap_postgres_data   # legacy name — do not rename lightly
docker compose build
docker compose up -d
docker compose exec backend alembic upgrade head
```

1. Postgres runs `init.sql` once on first boot of an empty volume.
2. Backend runs **`alembic upgrade head`** (deps already in image `xeniamap-api:local` — see [`docker.md`](docker.md)).

### Docker (existing volume)

`init.sql` does **not** re-run. Only:

```bash
docker compose exec backend alembic upgrade head
```

### Local Postgres (no Docker)

```bash
# once
psql -d "$DB_NAME" -f infrastructure/postgres/init.sql
# always
cd backend && alembic upgrade head
```

See also `scripts/setup_postgis_local.sh`.

### Deploy hooks

`backend/scripts/render_start.sh` and `backend/scripts/railway_web.sh` already run `alembic upgrade head` before serving.

## Alembic head

Chain:

`20260714_landing_texts` → `20260904_fire_orders` → `20260905_fire_orders_pipeline` → `20260906_projects_module`

Fresh DBs that already have landing texts / fire_orders / `projects.module` from init still run these revisions; create steps no-op when objects exist.

## Deprecated

| Artifact | Status |
|----------|--------|
| `backend/scripts/ensure_fire_orders.py` | Deprecated wrapper → `alembic upgrade head` only |
| Manual `CREATE TABLE fire_orders` outside Alembic/init | Forbidden |

## Related

- Inventory: [`schema_inventory_p0.md`](schema_inventory_p0.md)
- Storage decision: [`adr-001-storage-hybrid.md`](adr-001-storage-hybrid.md)
- Legacy volume name: [`legacy_names.md`](legacy_names.md)
