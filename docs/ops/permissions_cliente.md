# Permisos cliente × ownership (matriz)

**Fecha:** 2026-09-06 (actualizado middleware `/raster`)  
**Capa 1:** middleware `_is_cliente_allowed_request` (`app/main.py`) — qué paths puede llamar `role=cliente`.  
**Capa 2:** deps en el endpoint — tenant / ownership / `publicado` / admin.

## Reglas de producto

| Rol | Lectura de mapa/capas (layers, rasters, preview) | Inventarios disco / browse externo | Fire |
|-----|---------------------------------------------------|--------------------------------------|------|
| **admin** | Cualquier proyecto del tenant | Sí | Todo el tenant |
| **cliente** | Solo proyectos **publicados** con vínculo: dueño **o** `StudyOrder` **o** `ProjectShare` | No (`require_admin` + middleware) | Solo órdenes propias (email / `created_by`) |

Helper: `require_project_dashboard_access` → `assert_cliente_can_view_published_dashboard` en `app/api/deps.py`.  
Fire: `require_fire_order_access` en `application/fire/orders.py`.

## Middleware (allowlist cliente)

| Method | Path | Notas |
|--------|------|--------|
| GET | `/projects`, `/layers`, `/preprocess/`, `/cluster-analysis/`, `/fire-orders` | Prefijos; ownership en endpoint |
| GET | `/raster/{project_id}` y `/raster/{project_id}/{raster_id}/preview` | **Solo** estos (regex dígitos); browse/inventory → 403 middleware |
| DELETE | `/projects/{id}` | Solo propios (`assert_user_can_delete_project`) |
| POST | `/preprocess/vegetation-time-series`, `/s1-sar-time-series` | Con dashboard access |
| resto | — | 403 middleware |

## Matriz GET (post-hardening)

| Prefijo / ruta | Endpoint | Cliente | Control |
|----------------|----------|---------|---------|
| `GET /projects` | list | SAFE | owner / StudyOrder / ProjectShare |
| `GET /layers/{pid}` | list | SAFE | dashboard access |
| `GET /layers/.../geojson` | geojson | SAFE | dashboard access |
| `GET /layers/.../tiles/...mvt` | MVT | SAFE | dashboard access |
| `GET /raster/{pid}` | list rasters | SAFE | dashboard + middleware allowlist |
| `GET /raster/.../preview` | preview PNG | SAFE | dashboard + middleware allowlist |
| `GET /raster/tenant-storage-browse` | browse tenant | ADMIN | middleware 403 cliente + `require_admin` |
| `GET /raster/external-data-*` | disco externo | ADMIN | idem |
| `GET /raster/project-*-inventory` / storage-browse / downloads | inventarios | ADMIN | idem |
| `GET /preprocess/*` (casi todos) | inventarios UI | SAFE | dashboard access |
| `GET /preprocess/task-status/{id}` | Celery poll | AUTH + tenant | registro `task_id→tenant`; mismatch → 404 |
| `GET /cluster-analysis/capabilities` | build info | AUTH | `get_current_user` |
| `GET /cluster-analysis/datasets\|gmm-results` | | SAFE | dashboard access |
| `GET /fire-orders*` | list/detail/results | SAFE | own / fire access |

## Mutaciones raster (admin)

`POST /upload-raster`, import/copy/local-folder y `DELETE /raster/...` llevan **`require_admin`** (además del bloqueo middleware para cliente).

## Residual

Ninguno abierto en esta matriz. Ampliaciones futuras: estrechar otros prefijos GET (`/preprocess/`) con allowlist fina si aparecen rutas solo-admin nuevas.
