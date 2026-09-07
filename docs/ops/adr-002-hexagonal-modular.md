# ADR-002: Hexagonal-first + Clean-lite on modular monolith

**Status:** Accepted (H0)  
**Date:** 2026-09-07  
**Supersedes:** informal “hexagonal by domain” notes in architecture (now formalized)

## Context

XeniaMAP is a **deployable monolith** (FastAPI + Celery + React + PostGIS) already mid-migration toward ports/adapters (FIRMS, CDSE, `application/*`). Audit backlog F0–F7 is done. Remaining structural debt: fat routers/pipelines, thin domain, and mixed `services/` + `modules/fire` entry points.

We need a single team rule for:

1. How far to push hexagonal / Clean Architecture.
2. Whether to stay a modular monolith or split into microservices now.
3. What “done” means for a feature PR.

Related roadmap: [`hexagonal_modular_roadmap_checkpoint_2026-09-06.md`](hexagonal_modular_roadmap_checkpoint_2026-09-06.md) (phases H0→B1).

## Decision

### Primary style

**Hexagonal (ports & adapters) on a modular monolith** — hexagonal *inside* one deploy, not instead of the modular monolith.

| Layer | Role |
|-------|------|
| `domain/` | Ports (Protocols) + minimal invariants (authz, order/project states) |
| `application/` | Use cases — **only** orchestration for new/changed flows |
| `infrastructure/` | Adapters (DB, disk, NASA, CDSE, tiles, mail, Celery) |
| `api/v1/`, `tasks/` | Delivery (HTTP / workers) — thin |
| `services/` | GIS algorithms (libraries); migrate I/O out gradually |
| `modules/fire/` | Legacy Fire pipelines; no new product features here |

### Clean-lite (adopt only these three)

1. **Use cases as sole orchestration** for business flows (routers/tasks call UC).
2. **Dependency rule inward** — delivery and infrastructure depend on application/domain; not the reverse.
3. **Minimal domain** for authz and project/order states (not a full entity model for every GIS path).

### Explicitly out of scope (not required)

- Entities / presenters / mappers on every GIS endpoint.
- Full Clean Architecture ceremony for SoilPlus, dNBR, SNAP, rasterio paths.
- Microservices as the default next step.

### Modular path A → B

| Stage | Meaning | When |
|-------|---------|------|
| **A — Modular monolith** | One deploy; clear internal module APIs (Identity, Agro, Fire, Shared GIS) | **Now** (H0–H5) |
| **B — Modular + extractable** | Stable contracts (ports + queues) so a BC can be extracted | After Hex-in-monolith (H5); only with a real trigger (SNAP/dNBR load, SoilPlus GPU, separate CDSE ingest) |

### Definition of Done (feature / PR)

A change that adds or materially changes a product flow **must**:

1. Expose behavior via an **`application/` use case** (`execute` or equivalent).
2. Keep **HTTP/Celery handlers thin** (auth, validate input, call UC, map errors).
3. If the flow talks to an **external system or new I/O boundary**, define or reuse a **port in `domain/`** and an **adapter in `infrastructure/`** (or document why a temporary `services/` call is legacy).
4. Include at least one **test** at use-case or port-mock level when logic is non-trivial.
5. **Not** add new business rules in `api/`, `main.py` middleware (except path allowlists), or `modules/fire/` unless it is pure pipeline mechanics.

GIS-heavy algorithms may remain in `services/` as pure functions called by the UC — that is allowed under Clean-lite.

### Import rules (new code)

| From → To | Allowed? |
|-----------|----------|
| `api` → `application` | Yes |
| `api` → `domain` | Prefer no; use application |
| `api` → `services` / `modules` | **No for new code** (legacy callers only until H1/H4) |
| `tasks` → `application` | Yes |
| `application` → `domain` ports | Yes |
| `application` → `infrastructure` | Prefer injection/default adapter at edge; avoid hard-wiring new adapters deep in UC when a port exists |
| `application` → `services` (pure GIS) | Yes (temporary / algorithm libraries) |
| `domain` → FastAPI / SQLAlchemy / Celery | **No** |
| `infrastructure` → `application` | No |
| `modules/fire` → `api` | **No** |

Owners per context: [`module_owners.md`](module_owners.md).

## Consequences

- Team has a single vocabulary: Modular A now, Hexagonal-first, Clean-lite, B later.
- PRs can be reviewed against DoD and import rules without debating microservices.
- Phases H1–H5 of the roadmap implement this ADR; **B1** adds extractable contracts (Celery queues `agro`/`fire` + docs) without requiring microservices.
- Existing fat files (`preprocess.py`, `process_dnbr.py`, SoilPlus, FE panels) are **debt scheduled in H1/H4**, not blockers for accepting this ADR.

## Non-goals

- Renaming Docker volume `bioagromap_postgres_data`.
- Renaming Celery task names `tasks.fire_*`.
- Extracting microservices in H0–H5.
- Rewriting all `services/` into domain entities.
