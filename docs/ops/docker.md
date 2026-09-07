# Imágenes Docker prebuilt

Deps de Python/Node se instalan en **`docker compose build`**, no en cada `up`.

Arranque completo del stack (env, volumen, Alembic): también en el [**README**](../../README.md#levantar-el-stack-docker).

## Imágenes

| Servicio | Dockerfile | Tag local |
|----------|------------|-----------|
| `backend`, `worker` | `backend/Dockerfile` | `xeniamap-backend:local` |
| `frontend` | `frontend/Dockerfile` | `xeniamap-frontend:local` |
| `ai_service` (perfil `ai`) | `ai_service/Dockerfile` | `xeniamap-ai:local` |

## Flujo diario

```bash
# Primera vez o tras cambiar requirements.txt / package-lock.json
docker compose build

docker compose up -d

# Schema (ya no hace falta pip install dentro del contenedor)
docker compose exec backend alembic upgrade head
```

Código Python/JS sigue montado desde el host (`./backend`, `./frontend`) con reload. Los paquetes viven en la imagen (site-packages) o en el volumen `frontend_node_modules`.

## Cuándo rebuild

| Cambio | Comando |
|--------|---------|
| `backend/requirements.txt` | `docker compose build backend worker` |
| `frontend/package-lock.json` | `docker compose build frontend` y, si hace falta, `docker volume rm xeniamap_frontend_node_modules` antes del próximo `up` |
| Solo `.py` / `.jsx` | nada — volumen + reload |

## Notas

- El worker SNAP (`docker-compose.snap.yml`) reutiliza la misma imagen `xeniamap-backend:local`.
- CI GitHub Actions sigue instalando deps en el runner (no usa estas imágenes); eso es independiente del stack local.
