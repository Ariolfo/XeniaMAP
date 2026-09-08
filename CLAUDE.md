# CLAUDE.md — XeniaMAP

Guía para agentes (y humanos) que trabajan en este repo. Complementa, no reemplaza,
[`README.md`](README.md) y [`docs/architecture.md`](docs/architecture.md).

---

## 1. Objetivo del repositorio

**XeniaMAP es un portal geoespacial agrícola multi-tenant** que convierte un polígono
dibujado o subido por el usuario en datos derivados de teledetección.

Flujo de valor:

1. El usuario carga un lote (GeoJSON / vector) sobre un mapa web.
2. El backend toma esa geometría (WKT) y **descarga imágenes multiespectrales / SAR**
   de Copernicus (Sentinel-2 L2A, Sentinel-1 GRD) y otras fuentes (Planet, Open-Meteo).
3. Un **gestor de colas (Celery + Redis)** procesa esas imágenes fuera del request:
   recortes al AOI, stacks de índices de vegetación, clustering espacio-temporal,
   dNBR de incendios, SoilPlus, etc.
4. Los resultados se sirven al mapa como **XYZ tiles** (COG) y **vectores MVT**, más
   dashboards e informes (Markdown).

Dos *bounded contexts*: **Agro** (vegetación, suelos, SAR) y **Fire** (dNBR + NASA FIRMS).

### Stack

| Capa | Tecnología |
|------|------------|
| Frontend | React 18 + Vite 5 + MapLibre GL (sin Mapbox) |
| API | FastAPI + Uvicorn/Gunicorn, SQLAlchemy 2, Alembic, JWT en cookies HttpOnly |
| Workers | Celery 5 (colas `agro` / `fire`), rasterio, geopandas, scikit-learn, ESA SNAP (SAR) |
| Cola / cache | Redis 7 (broker Celery, result backend, rate-limit, cache FIRMS, registro task→tenant) |
| BD | PostgreSQL 14 + PostGIS 3.4 (metadata + vectores MVT; storage espacial híbrido JSON/disco) |
| Datos grandes | Disco externo `Data_XeniaMap` (`EXTERNAL_DATA_ROOT` → `/data_xeniamap`) |
| Fuentes externas | Copernicus Data Space (CDSE), NASA FIRMS, Open-Meteo, Planet, HIBP |
| Observabilidad | Prometheus + Grafana; `/metrics` API + workers `:9101`/`:9102` |

Arquitectura: monolito modular + hexagonal (puertos/adaptadores). Reglas de import
forzadas por `import-linter` en CI. Detalle en
[`docs/architecture.md`](docs/architecture.md) y
[`docs/ops/adr-002-hexagonal-modular.md`](docs/ops/adr-002-hexagonal-modular.md).

### Punto clave sobre backend vs workers

**API y workers comparten el mismo `backend/app/`.** No es "código aparte": el worker
corre `celery -A app.tasks.celery_app.celery_app worker` sobre el mismo paquete
(`application/`, `services/`, `modules/`). Un cambio en `backend/app/**` afecta a
**ambas** imágenes (`Dockerfile` = API, `Dockerfile.worker` = worker) y ambas deben
redesplegarse. Se comunican **solo por Redis (broker) y Postgres (estado compartido)**.

---

## 2. Estado de despliegue

| Entorno | Estado | Descripción |
|---------|--------|-------------|
| Dev local | Vigente | `docker-compose.yml` levanta todo (build local). Ver README. |
| Render + Vercel | Histórico | `render.yaml` (API+Celery en un servicio, Redis/Postgres free). Referencia. |
| ngrok | Local/privado | Túnel ad-hoc del frontend, [`docs/ops/ngrok.md`](docs/ops/ngrok.md). |
| **VPS + Cloudflare + workers local** | **Plan objetivo** | Ver sección 3. Aún no implementado. |

---

## 3. Plan de despliegue objetivo — VPS + Cloudflare + local

> **Registro de decisión.** Diseñado en la sesión de Claude Code del 2026-09-08
> (https://claude.ai/code/session_0129p2ZCHN5GZtVdSjVRMpza). Marca la intención;
> los detalles finos se ajustan al implementar. Nada de esta sección está en
> producción todavía.

### 3.1. Motivación

- El procesamiento pesado (Sentinel-2, SNAP/GDAL) y el disco de datos (~3 TB) son
  **caros de llevar a la nube**. Se quedan en una PC local.
- El resto (mapa, login, browse, dashboards) debe **seguir disponible aunque la PC
  esté apagada** → va a un VPS barato.
- Frontend estático → CDN gratis.
- Objetivo de costo del lado nube: **~5–15 USD/mes**.

### 3.2. Topología

```
┌─ Cloudflare ─────────────────────────────────────────────┐
│  Pages: frontend estático (build de frontend/)           │
│  Proxy same-origin /api/* → VPS (cookies sin CORS)       │
│  Tunnel (cloudflared): api./grafana./prometheus.<dominio>│
│  Edge cache de XYZ tiles                                  │
└────────────────────────┬─────────────────────────────────┘
                         │ (cloudflared, saliente desde el VPS)
┌─ VPS (~5 USD/mes, p.ej. Hetzner CX22) ───────────────────┐
│  docker-compose.vps.yml:                                 │
│    api (gunicorn -k uvicorn.workers.UvicornWorker, sin --reload) │
│    postgres (PostGIS)                                    │
│    redis (--requirepass, bind tailscale0)               │
│    prometheus + grafana                                  │
│  Sin puertos públicos: solo cloudflared marca afuera.    │
└────────────────────────┬─────────────────────────────────┘
                         │ Tailscale (malla privada)
                         │ workers → Redis:6379 y Postgres:5432 (SALIENTE)
                         │ Prometheus VPS → workers :9101/:9102
┌─ PC local + disco 3 TB ─────────────────────────────────┐
│  docker-compose.local.yml:                               │
│    worker-agro  (celery -Q agro,  --concurrency=1)      │
│    worker-fire  (celery -Q fire,  --concurrency=1)      │
│    watchtower   (auto-pull de la imagen worker)         │
│  Monta /mnt/disco3tb/Data_XeniaMap → /data_xeniamap     │
│  Sin exposición entrante. Todo saliente.                 │
└─────────────────────────────────────────────────────────┘

Object storage: Cloudflare R2 (egress gratis)
  workers publican COG derivados (dNBR/severity/RGB/stacks) al final del pipeline
  la API los lee por URL (rasterio + GDAL vsicurl, solo byte-ranges del tile)
  el raw .SAFE (~3 TB) NO va a R2, se queda en el disco local
```

### 3.3. Decisiones y porqués

| Decisión | Porqué |
|----------|--------|
| **No dividir el repo** (frontend/back/workers) | API y workers comparten `app/`; separar obliga a lib compartida versionada + PRs cross-repo. Los límites ya los da `import-linter` + `modules/{agro,fire,shared}`. Ownership futuro → `CODEOWNERS` por carpeta, no repos aparte. |
| **Workers local, no nube** | Disco 3 TB (~45 USD/mes en R2) + cómputo GIS/SNAP. |
| **Tailscale, no túnel entrante a casa** | Celery es *pull-based*: el worker marca al broker (BRPOP saliente). La malla privada evita exponer Redis/Postgres. Redis expuesto a internet es vector de RCE aunque tenga password. |
| **NO exponer Redis por túnel público** | Protocolo TCP (ngrok TCP es de pago), `requirepass` viaja en claro sin TLS, dirección equivocada (polling nube→casa). |
| **cloudflared, no ngrok** | Hostname fijo gratis en dominio propio, sin cuota de banda, y **edge-cache de tiles** (ngrok con dominio reservado ~10 USD/mes y toda la banda por la subida de casa). |
| **cloudflared hace el routing, no nginx** | Cloudflare termina TLS en el edge; `ingress:` del tunnel enruta por subdominio. Un reverse proxy en el VPS sería redundante. |
| **gunicorn + UvicornWorker en prod** | Reinicio graceful, `--timeout` mata renders GIS colgados. Nunca `--reload` en prod. |
| **COG derivados → R2** | La API en la nube no puede leer el disco local. Empujar archivos (PUT HTTPS saliente) **no es un túnel**. COG + vsicurl = la API lee solo los bytes del tile. Requiere adaptador nuevo de `RasterStoragePort`. |
| **VPS con compose, no Azure managed** | Redis/Postgres/API managed en Azure ~70–90 USD/mes (servicios 24/7) vs ~5 USD/mes el VPS con el mismo compose. Middle ground si se quiere managed sin idle: Upstash Redis + Neon Postgres. |

### 3.4. CI/CD

Monorepo, **un pipeline por componente con path filters** (`dorny/paths-filter`):

| Cambio en | Reconstruye | Despliegue |
|-----------|-------------|------------|
| `frontend/**` | — | Cloudflare Pages (GitHub App + "Build watch paths" = `frontend/*`) |
| `backend/app/**`, `requirements-{common,api}.txt`, `Dockerfile`, `alembic/**` | imagen `api` | Action → **SSH al VPS** → `pull` + `alembic upgrade head` + `up -d api` (push) |
| `backend/app/**`, `requirements-{common,worker}.txt`, `Dockerfile.worker` | imagen `worker` | **Watchtower** en la PC hace polling al registry (pull; CI no tiene ruta a casa) |

- **Registry:** GHCR. Package **público** = storage + egress gratis (las imágenes
  GIS/SNAP pesan 1–3 GB; en privado el egress a VPS+PC cuesta). Alternativas:
  base image pesada aparte + podar tags, o self-host `registry:2` en el VPS.
- **Tags:** `:<sha>` + `:latest`. `:latest` lo siguen Watchtower y `compose pull`;
  `:<sha>` para rollback.
- **Migraciones Alembic backward-compatible** (expand/contract): entre el deploy del
  API y el pull del worker (~2 min) corren versiones distintas de `app/`. Nunca un
  `DROP` en el mismo release que introduce el código que deja de usar la columna.

### 3.5. Ficheros por entorno

Un `Dockerfile` por imagen (en el repo, los usa **solo el CI**). Un **compose por
entorno** (en el repo). Un `.env` **por máquina** (fuera de git).

```
backend/Dockerfile          # imagen api        ─┐ build en CI
backend/Dockerfile.worker   # imagen worker     ─┘
docker-compose.yml          # dev local (build:)
docker-compose.vps.yml      # VPS  (image: ghcr.io/.../api:latest)      [pendiente]
docker-compose.local.yml    # PC   (image: ghcr.io/.../worker:latest)   [pendiente]
```

Diferencia dev→prod en el compose: `build:` → `image:`.

### 3.6. Tiles y cache (pendiente de código)

Hoy los tiles responden `Cache-Control: private` + auth por cookie → **no** los
cachea Cloudflare. Para habilitar edge-cache, una de:

- **URLs firmadas** (patrón Mapbox): endpoint autenticado devuelve plantilla de
  tiles con firma HMAC de vida corta; MapLibre la usa sin cookie; respuesta
  `Cache-Control: public`. La firma autoriza *y* es la cache key. Firmar
  `{order_id, layer, hora_redondeada}` para compartir cache entre usuarios del tenant.
- **Cache LRU en R2**: en un miss, renderiza del COG → escribe el PNG en R2 → sirve.

Trade-off: una vez cacheado en el edge, `require_*_access` no corre en los hits;
para rasters derivados (dNBR/NDVI sobre un lote) suele ser aceptable si el catálogo
y la metadata siguen protegidos estricto.

### 3.7. Pendientes antes de producción

- [ ] `docker-compose.vps.yml` y `docker-compose.local.yml`
- [ ] Adaptador `RasterStoragePort` → R2 (subir COG al final del pipeline; abrir URL al servir)
- [ ] URLs firmadas o cache LRU para tiles
- [ ] Workflow CI con path filters + push a GHCR + SSH deploy al VPS
- [ ] Watchtower en la PC local (auth GHCR vía `~/.docker/config.json`)
- [ ] Tailscale en VPS y PC; Redis/Postgres bind a `tailscale0`
- [ ] `cloudflared` en el VPS con `ingress:` para api/grafana/prometheus
- [ ] `pg_dump` nocturno a R2 (cron)
- [ ] Cambiar arranque API a `gunicorn -k uvicorn.workers.UvicornWorker` sin `--reload`
- [ ] SMTP por relay (587) para OTP en producción — ISP residencial bloquea :25

---

## 4. Convenciones al contribuir

- **Definition of Done** de feature: flujo vía *use case* en `application/`, router/task
  delgado, I/O externo nuevo → port + adapter, test de UC. Detalle en ADR-002.
- Nombres de tarea Celery `tasks.*` y colas `agro`/`fire` son **contrato** — no renombrar.
- El volumen Postgres se llama `bioagromap_postgres_data` (legacy intencional).
- CI: ruff, pytest, eslint (núcleo mapa), vite build, import-linter, docs-check.
- Idioma de docs y comentarios: español.
