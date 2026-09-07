# Imágenes Docker prebuilt (H5: API slim vs worker GIS; B1: dos workers por cola)

Deps de Python/Node se instalan en **`docker compose build`**, no en cada `up`.

Arranque completo del stack (env, volumen, Alembic): también en el [**README**](../../README.md#levantar-el-stack-docker).

## Imágenes

| Servicio | Dockerfile | Tag local | Requirements |
|----------|------------|-----------|--------------|
| `backend` (API) | `backend/Dockerfile` | `xeniamap-api:local` | `requirements-api.txt` → `-r requirements-common.txt` (**sin boto3**) |
| `worker-agro` / `worker-fire` | `backend/Dockerfile.worker` | `xeniamap-worker:local` | `requirements-worker.txt` → common + **boto3** (+ SNAP/GDAL futuros) |
| `frontend` | `frontend/Dockerfile` | `xeniamap-frontend:local` | npm |
| `ai_service` (perfil `ai`) | `ai_service/Dockerfile` | `xeniamap-ai:local` | — |

Alias legacy: documentación antigua mencionaba `xeniamap-backend:local` (API+worker una sola imagen) y un único servicio `worker`. Desde H5 son **dos tags** de imagen; desde B1 hay **dos servicios worker** (`-Q agro` / `-Q fire`).

## Colas Celery (B1)

| Servicio | Cola | Métricas |
|----------|------|----------|
| `worker-agro` | `agro` | `:9101` |
| `worker-fire` | `fire` | `:9102` |

Contratos: [`bounded_context_contracts.md`](bounded_context_contracts.md).

## Flujo diario

```bash
# Primera vez o tras cambiar requirements*.txt / package-lock.json
docker compose build

docker compose up -d

# Schema (ya no hace falta pip install dentro del contenedor)
docker compose exec backend alembic upgrade head
```

Código Python/JS sigue montado desde el host (`./backend`, `./frontend`) con reload. Los paquetes viven en la imagen (site-packages) o en el volumen `frontend_node_modules`.

## Cuándo rebuild

| Cambio | Comando |
|--------|---------|
| `backend/requirements.txt` o `requirements-common.txt` / `requirements-api.txt` | `docker compose build backend` |
| `backend/requirements-worker.txt` | `docker compose build worker-agro` (misma imagen que `worker-fire`) |
| `frontend/package-lock.json` | `docker compose build frontend` y, si hace falta, `docker volume rm xeniamap_frontend_node_modules` antes del próximo `up` |
| Solo `.py` / `.jsx` | nada — volumen + reload |

## Notas

- Hoy la API **no** instala `boto3` (solo worker Fire S2/S3). Rasterio/geopandas/sklearn siguen en API por SoilPlus/preview (H6 residual).
- El overlay SNAP (`docker-compose.snap.yml`) monta gpt en **`worker-agro`** (S1).
- CI GitHub Actions sigue instalando deps en el runner (no usa estas imágenes); eso es independiente del stack local.
- `XENIAMAP_ROLE=api|worker` queda en la imagen para diagnóstico.
