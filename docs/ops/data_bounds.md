# Data bounds por bounded context (B1)

**Fecha:** 2026-09-07  
**Objetivo:** documentar tablas + paths que un contexto **posee** o **comparte**, para poder extraer un BC sin adivinar el disco.

Host típico: `EXTERNAL_DATA_HOST_PATH` → contenedor `/data_xeniamap` (`EXTERNAL_DATA_ROOT`).  
Storage app: `STORAGE_PATH` → `/data/storage` en compose.

## Identity

| Recurso | Tipo | Notas |
|---------|------|--------|
| `tenants`, `users`, `user_audit_log` | Postgres | Auth / tenancy |
| — | Disco | Sin rasters propios |

## Agro

| Recurso | Tipo | Notas |
|---------|------|--------|
| `projects` (`module` agro / shared), `study_orders` | Postgres | Órdenes de estudio |
| `project_shares`, `project_processing_log` | Postgres | Compartido con mapa |
| `layers`, `raster_layers`, `ai_results`, `project_landing_texts` | Postgres | Capas / landing |
| `{EXTERNAL_DATA_ROOT}/…` proyectos Agro (S1/S2/PS, recortes, índices) | Disco | Layout bajo raíz externa por proyecto |
| `{STORAGE_PATH}/…` uploads / temporales | Disco | Compose `./data` |

Cola Celery: **`agro`**.

## Fire

| Recurso | Tipo | Notas |
|---------|------|--------|
| `fire_orders` | Postgres | FK opcional `project_id` → `projects` |
| `projects` con módulo Fire (enlace) | Postgres | Creación vía `application/fire/project_link` |
| `{STORAGE_PATH}/fire/…` (ver `fire_storage_root` / `fire_results_root`) | Disco | Resultados dNBR / tiles por `order_id` |
| AOI / productos S2 Fire bajo EXTERNAL_DATA según pipeline | Disco | `modules.fire` + UC `aoi` |

Cola Celery: **`fire`** (`tasks.fire_*` estables).

## Shared GIS

| Recurso | Tipo | Notas |
|---------|------|--------|
| PostGIS `layers.geom` (MVT) | Postgres | Tiles mapa |
| Ports: Storage / Tiles / JobQueue / Mail / Repo | Código | `domain/shared/ports.py` |
| Ambos workers montan EXTERNAL_DATA + STORAGE | Disco | Compartido hasta extracción |

## Reglas al extraer

1. **No** mover tablas Identity sin contrato de auth (JWT/tenant).
2. Fire puede vivir con réplica de lectura de `projects` o API interna; escribir `fire_orders` + su árbol de disco.
3. Agro retiene SNAP/S1 en su worker; Fire no monta gpt por defecto.
4. Volumen Postgres legacy `bioagromap_postgres_data` **no** se renombra.

## Relacionado

- Contratos: [`bounded_context_contracts.md`](bounded_context_contracts.md)  
- Storage híbrido: [`adr-001-storage-hybrid.md`](adr-001-storage-hybrid.md)
