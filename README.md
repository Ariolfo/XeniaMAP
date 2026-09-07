# XeniaMAP

Portal geoespacial agrícola multi-tenant (Agro + Fire).

- Backend: **FastAPI** + **Celery** + **Redis**
- Frontend: **React + Vite + MapLibre GL** (no Mapbox)
- BD: **PostgreSQL + PostGIS** (geometría de app mayormente GeoJSON/disco; PostGIS disponible)
- Disco de datos grandes: **Data_XeniaMap** (`EXTERNAL_DATA_HOST_PATH`)
- Arquitectura: monolito modular + hexagonal → [`docs/architecture.md`](docs/architecture.md)
- ADR estilo (H0): Hexagonal-first + Clean-lite → [`docs/ops/adr-002-hexagonal-modular.md`](docs/ops/adr-002-hexagonal-modular.md)
- Owners por contexto → [`docs/ops/module_owners.md`](docs/ops/module_owners.md)
- Bootstrap BD (init + Alembic) → [`docs/ops/bootstrap.md`](docs/ops/bootstrap.md)
- Imágenes Docker (build, sin pip/npm en cada up) → [`docs/ops/docker.md`](docs/ops/docker.md)
- Roadmap Hexagonal + Modular (checkpoint) → [`docs/ops/hexagonal_modular_roadmap_checkpoint_2026-09-06.md`](docs/ops/hexagonal_modular_roadmap_checkpoint_2026-09-06.md)
- Storage espacial (híbrido) → [`docs/ops/adr-001-storage-hybrid.md`](docs/ops/adr-001-storage-hybrid.md)
- Permisos cliente × ownership → [`docs/ops/permissions_cliente.md`](docs/ops/permissions_cliente.md)
- Nombres legacy BioAgro → [`docs/ops/legacy_names.md`](docs/ops/legacy_names.md)

## Estructura

```text
/backend          # FastAPI, Celery, domain/application/infrastructure
/frontend         # React + MapLibre
/ai_service       # Stub opcional (perfil Docker ``ai``); no requerido para Agro/Fire
/infrastructure   # Postgres init, Prometheus, K8s
/scripts
/docs             # ops + architecture
/data             # storage local (gitignored)
```

## Requisitos

- Docker + Docker Compose
- (Opcional) ngrok con dominio reservado `xeniamap.ngrok.app`
- (Opcional) carpeta host `Data_XeniaMap` (p. ej. `/mnt/disco3tb/Data_XeniaMap`)

## Levantar el stack (Docker)

Guía de imágenes prebuilt (sin pip/npm en cada `up`): **[`docs/ops/docker.md`](docs/ops/docker.md)**.  
Bootstrap de esquema (init + Alembic): [`docs/ops/bootstrap.md`](docs/ops/bootstrap.md).

```bash
cd /path/to/XeniaMAP

cp -n .env.example .env
# Obligatorio: SECRET_KEY
# Local sin SMTP: OTP_SIMULATE=1
# Bootstrap admin (opcional): ADMIN_EMAILS=tu@correo
# Datos: EXTERNAL_DATA_HOST_PATH=/mnt/disco3tb/Data_XeniaMap
# Fire: FIRMS_MAP_KEY=...

# Volumen Postgres (nombre legacy intencional — no renombrar sin plan dual)
docker volume inspect bioagromap_postgres_data >/dev/null 2>&1 || \
  docker volume create bioagromap_postgres_data

# Primera vez o tras cambiar requirements.txt / package-lock.json
docker compose build
docker compose up -d

# Obligatorio tras up: Alembic (init.sql solo en volumen vacío)
docker compose exec backend alembic upgrade head

docker compose ps
```

| Cambio | Rebuild |
|--------|---------|
| Solo `.py` / `.jsx` | no hace falta |
| `backend/requirements.txt` | `docker compose build backend worker-agro worker-fire` |
| `frontend/package-lock.json` | `docker compose build frontend` (ver [`docker.md`](docs/ops/docker.md) si hay que resetear `node_modules`) |

Stub IA (opcional): `docker compose --profile ai up -d --build ai_service`

### URLs locales

| Servicio   | URL |
|------------|-----|
| Frontend   | http://localhost:5173 |
| API docs   | http://localhost:8000/docs |
| Health     | http://localhost:8000/health |
| Prometheus | http://localhost:9090 |
| Grafana    | http://localhost:3000 |
| Postgres   | 127.0.0.1:5433 (solo loopback) |
| Redis      | 127.0.0.1:6379 + `REDIS_PASSWORD` |

### Auth (F0 / F6)

- Producción: `OTP_SIMULATE=0` + `SMTP_*` (código por correo; **nunca** `debug_otp` en API)
- Desarrollo: `OTP_SIMULATE=1` almacena el OTP en servidor; opcional `LOG_OTP=1` solo en logs del backend (no en JSON)
- `APP_ENV=production` + `OTP_SIMULATE=1` → la app no arranca / request-otp responde 503
- Admins bootstrap: `ADMIN_EMAILS` (coma-separados); el rol en DB manda para usuarios existentes
- Rate limit auth (F6): `AUTH_RATE_LIMIT_MAX_REQUESTS` / `AUTH_RATE_LIMIT_WINDOW_SECONDS` (p. ej. 10/60s) sobre login, OTP y check-email; **fail-closed** si Redis no responde (503). El límite global (`RATE_LIMIT_*`) sigue fail-open para no tumbar galerías/tiles.
- Contraseñas (F9): mínimo 10 caracteres con letra+dígito; `POST /auth/change-password` consulta HIBP (k-anonymity). Vars: `HIBP_ENABLED`, `HIBP_FAIL_OPEN`.
- Ops local (F11): Postgres/Redis/Prometheus/Grafana/métricas workers en `127.0.0.1`; Redis con `--requirepass` (`REDIS_PASSWORD`). Tras cambiar Redis: `docker compose up -d redis backend worker-agro worker-fire --force-recreate`.

### Disco externo Data_XeniaMap

```bash
# Host: /mnt/disco3tb/Data_XeniaMap  (o symlink desde Data_Bioagro)
# Compose: EXTERNAL_DATA_HOST_PATH → /data_xeniamap
```

### Comandos útiles

```bash
docker compose logs -f backend worker-agro worker-fire frontend
docker compose restart backend worker-agro worker-fire
docker compose -f docker-compose.yml -f docker-compose.snap.yml up -d worker-agro   # SNAP S1
docker compose down
```

## Túnel ngrok

Runbook: [`docs/ops/ngrok.md`](docs/ops/ngrok.md).

```bash
ngrok http --url=xeniamap.ngrok.app 5173
```

## Backend local (venv)

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=postgresql+psycopg2://postgres:postgres@127.0.0.1:5433/xeniamap
export REDIS_URL=redis://:xeniamap-local-redis@127.0.0.1:6379/0
export SECRET_KEY=dev-local-xeniamap-change-me
export OTP_SIMULATE=1
export EXTERNAL_DATA_ROOT=/mnt/disco3tb/Data_XeniaMap
uvicorn app.main:app --reload --port 8000
```

## Despliegue: Vercel + Render

Ver secciones en este README histórico / `render.yaml`. Variables clave: `SECRET_KEY`, `CORS_ORIGINS`, `SMTP_*`, `ADMIN_EMAILS`, `FIRMS_MAP_KEY`, `VITE_API_URL`.

## Endpoints útiles (`/api/v1`)

- Auth: `POST /auth/check-email`, `/auth/request-otp`, `/auth/verify-otp`, `/auth/login`
- Fire: `GET /fire-orders/{id}/results`, `.../preview`, `.../tiles/{z}/{x}/{y}.png`, `.../firms-live`
- Agro: projects, preprocess, rasters, soilplus

## Mapa Fire

- Capas lazy (GeoJSON/preview bajo demanda)
- Rasters vía **XYZ tiles** (COG RGB / severity / dNBR) + FIRMS cache
- Basemap sin `setStyle` completo (`applyBasemap`)

## Testing / CI

```bash
cd backend
export SECRET_KEY=test-secret-key-for-ci OTP_SIMULATE=1
PYTHONPATH=. pytest -q
```

CI (`.github/workflows/ci.yml`): ruff + pytest + eslint (mapa) + frontend build + docs-check.
Detalle: [`docs/ops/quality.md`](docs/ops/quality.md).
