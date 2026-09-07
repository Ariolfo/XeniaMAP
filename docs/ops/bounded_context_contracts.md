# Bounded context contracts (B1 — extractable readiness)

**Fecha:** 2026-09-07  
**Estado:** Contratos listos en monolito; **extracción de proceso/servicio solo con trigger** (SNAP/dNBR load, SoilPlus GPU, ingest CDSE).  
**ADR:** [`adr-002-hexagonal-modular.md`](adr-002-hexagonal-modular.md)

No renombrar: Celery `tasks.fire_*`, volumen Postgres `bioagromap_postgres_data`.

## Colas Celery (evento asíncrono)

| Cola | Worker compose | Puerto métricas | Tareas |
|------|----------------|-----------------|--------|
| `agro` | `worker-agro` | `:9101` | Todo `tasks/*` en `jobs.py` (default) |
| `fire` | `worker-fire` | `:9102` | `tasks.fire_download_s2`, `tasks.fire_process_dnbr`, `tasks.fire_validate_firms` |

Código: [`backend/app/tasks/queue_routing.py`](../../backend/app/tasks/queue_routing.py) + `celery_app.conf.task_routes`.

Payload de encolado (vía `JobQueuePort` / `.delay`):

| Campo | Notas |
|-------|--------|
| `task` name | Estable (`tasks.fire_*` / `tasks.download_sentinel2`, …) |
| args | IDs de orden/proyecto + parámetros de pipeline |
| registry | `task_id → tenant_id` (`celery_task_registry`) |

## Contrato HTTP por BC (API interna del monolito)

| BC | Superficie HTTP (v1) | Orquestación | Side-effects async |
|----|----------------------|--------------|--------------------|
| **Identity** | `/auth/*` | `domain/identity` + deps glue | — |
| **Agro** | `/projects`, `/study-orders`, `/rasters*`, `/preprocess`, `/soilplus`, `/layers` | `application/agro/*` | cola `agro` |
| **Fire** | `/fire-orders/*` | `application/fire/*` | cola `fire` |
| **Shared GIS** | tiles MVT/XYZ, storage paths | ports en `domain/shared` | workers comparten disco |

Regla de extracción futura: el **mapa cliente** solo habla HTTP; los workers consumen colas. Sacar Fire GIS = mover consumidor de cola `fire` + `modules.fire` + paths Fire; el FE no cambia nombres de API.

## Disparadores para extracción real

| Trigger | Qué sacar primero |
|---------|-------------------|
| SNAP tumba p95 API / OOM Agro | Ya aislado en `worker-agro` + overlay SNAP; siguiente: imagen GIS dedicada |
| dNBR / FIRMS satura CPU | Proceso/imagen solo cola `fire` |
| SoilPlus GPU | Job SoilPlus en cola `agro` (o subcola) + host GPU |
| Ingest CDSE con ciclo distinto | Worker CDSE + contrato JobQueue |

## Relacionado

- Límites de datos: [`data_bounds.md`](data_bounds.md)  
- Docker: [`docker.md`](docker.md)  
- Owners: [`module_owners.md`](module_owners.md)
