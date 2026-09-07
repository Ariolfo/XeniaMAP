# Imágenes Docker prebuilt (H5: API slim vs worker GIS)

Deps de Python/Node se instalan en **`docker compose build`**, no en cada `up`.

Arranque completo del stack (env, volumen, Alembic): también en el [**README**](../../README.md#levantar-el-stack-docker).

## Imágenes

| Servicio | Dockerfile | Tag local | Requirements |
|----------|------------|-----------|--------------|
| `backend` (API) | `backend/Dockerfile` | `xeniamap-api:local` | `requirements-api.txt` → `-r requirements.txt` |
| `worker` | `backend/Dockerfile.worker` | `xeniamap-worker:local` | `requirements-worker.txt` → `-r requirements.txt` (+ extras GIS/SNAP futuros) |
| `frontend` | `frontend/Dockerfile` | `xeniamap-frontend:local` | npm |
| `ai_service` (perfil `ai`) | `ai_service/Dockerfile` | `xeniamap-ai:local` | — |

Alias legacy: documentación antigua mencionaba `xeniamap-backend:local` (API+worker una sola imagen). Desde H5 son **dos tags**.

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
| `backend/requirements.txt` o `requirements-api.txt` | `docker compose build backend` |
| `backend/requirements-worker.txt` | `docker compose build worker` |
| `frontend/package-lock.json` | `docker compose build frontend` y, si hace falta, `docker volume rm xeniamap_frontend_node_modules` antes del próximo `up` |
| Solo `.py` / `.jsx` | nada — volumen + reload |

## Notas

- Hoy API y worker comparten el mismo set de wheels Python; la **separación de Dockerfiles/tags** permite añadir SNAP/GDAL **solo** al worker sin engordar la API.
- El worker SNAP (`docker-compose.snap.yml`) usa `xeniamap-worker:local`.
- CI GitHub Actions sigue instalando deps en el runner (no usa estas imágenes); eso es independiente del stack local.
- `XENIAMAP_ROLE=api|worker` queda en la imagen para diagnóstico.
