"""API Fire — thin HTTP sobre ``application.fire``."""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.application.fire.catalog import FIRE_RESULT_CATALOG  # noqa: F401 — re-export tests
from app.application.fire.firms_live import GetFirmsLiveHotspots
from app.application.fire.orders import (
    EnqueueFireDownloadS2,
    EnqueueFireProcessDnbr,
    EnqueueFireValidateFirms,
    GetFirePipelineStatus,
    celery_task_meta,
    normalize_geometry,
    parse_iso_date,
    project_name,
    require_fire_order_access,
    require_fire_order_admin,
)
from app.application.fire.results import (
    FireResultGeojson,
    FireResultPreview,
    FireResultStats,
    FireResultXyzTile,
    ListFireResultLayers,
)
from app.core.config import settings
from app.db.session import get_db
from app.infrastructure.firms.live_cache import (
    get_firms_live_cached,
    get_firms_live_stale,
    set_firms_live_cached,
)
from app.infrastructure.firms.nasa_firms_adapter import NasaFirmsAreaAdapter
from app.models.models import FireOrder, User
from app.modules.fire.project_link import (
    ensure_fire_order_project,
    materialize_fire_projects_for_applicant,
)
from app.modules.fire.seed import seed_tolima_fire_orders
from app.schemas.schemas import (
    FireOrderCreate,
    FireOrderDetail,
    FireOrderDownloadRequest,
    FireOrderFirmsRequest,
    FireOrderStatusPatch,
    FireOrderSummary,
)

router = APIRouter(prefix="/fire-orders", tags=["fire-orders"])
logger = logging.getLogger(__name__)


def _http_from_app(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc) or "No encontrado")
    if isinstance(exc, ValueError):
        msg = str(exc)
        code = 400 if "Primero debe" in msg or "FIRMS" in msg else 422
        return HTTPException(status_code=code, detail=msg)
    return HTTPException(status_code=500, detail=str(exc))


def _summary(order: FireOrder, db: Session | None = None) -> FireOrderSummary:
    return FireOrderSummary(
        id=order.id,
        request_name=order.request_name,
        department=order.department,
        applicant_name=order.applicant_name,
        applicant_email=order.applicant_email or "",
        status=order.status,
        pre_start=order.pre_start.isoformat(),
        pre_end=order.pre_end.isoformat(),
        post_start=order.post_start.isoformat(),
        post_end=order.post_end.isoformat(),
        max_cloud_cover=float(order.max_cloud_cover),
        created_at=order.created_at.isoformat() if order.created_at else "",
        source_key=order.source_key,
        project_id=getattr(order, "project_id", None),
        project_name=project_name(db, order) if db is not None else None,
    )


def _detail(order: FireOrder, db: Session | None = None) -> FireOrderDetail:
    return FireOrderDetail(
        id=order.id,
        request_name=order.request_name,
        department=order.department,
        applicant_name=order.applicant_name,
        applicant_email=order.applicant_email or "",
        applicant_phone=order.applicant_phone or "",
        company=order.company,
        geometry=order.geometry_geojson,
        pre_start=order.pre_start.isoformat(),
        pre_end=order.pre_end.isoformat(),
        post_start=order.post_start.isoformat(),
        post_end=order.post_end.isoformat(),
        max_cloud_cover=float(order.max_cloud_cover),
        status=order.status,
        download_task_id=order.download_task_id,
        download_message=order.download_message,
        download_manifest=order.download_manifest,
        data_root=order.data_root,
        results_root=getattr(order, "results_root", None),
        process_task_id=getattr(order, "process_task_id", None),
        process_message=getattr(order, "process_message", None),
        process_manifest=getattr(order, "process_manifest", None),
        firms_task_id=getattr(order, "firms_task_id", None),
        firms_message=getattr(order, "firms_message", None),
        firms_manifest=getattr(order, "firms_manifest", None),
        source_key=order.source_key,
        extra_notes=order.extra_notes,
        created_at=order.created_at.isoformat() if order.created_at else "",
        project_id=getattr(order, "project_id", None),
        project_name=project_name(db, order) if db is not None else None,
    )


@router.post("/seed-tolima")
def seed_tolima(
    applicant_email: str = "ariolfoc@gmail.com",
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Precarga solicitudes desde Incendios_Tolima.shp."""
    try:
        result = seed_tolima_fire_orders(
            db,
            admin,
            applicant_email=(applicant_email or "").strip() or None,
        )
        if applicant_email:
            linked = materialize_fire_projects_for_applicant(
                db, applicant_email=applicant_email.strip()
            )
            result["projects"] = linked
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Fire seed failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return result


@router.post("/materialize-projects")
def materialize_projects(
    applicant_email: str = "ariolfoc@gmail.com",
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        return materialize_fire_projects_for_applicant(db, applicant_email=applicant_email)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Fire materialize failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("", response_model=list[FireOrderSummary])
def list_fire_orders(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    role = str(user.role or "").lower()
    q = db.query(FireOrder)
    if role == "admin":
        q = q.filter(FireOrder.tenant_id == user.tenant_id)
    else:
        email = str(user.email or "").strip().lower()
        q = q.filter(
            (FireOrder.applicant_email.ilike(email))
            | (FireOrder.created_by_user_id == user.id)
        )
    rows = q.order_by(FireOrder.request_name.asc(), FireOrder.id.asc()).all()
    return [_summary(r, db) for r in rows]


@router.post("", response_model=FireOrderDetail)
def create_fire_order(
    payload: FireOrderCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        geom = normalize_geometry(payload.geometry)
        pre_start = parse_iso_date(payload.pre_start, "pre_start")
        pre_end = parse_iso_date(payload.pre_end, "pre_end")
        post_start = parse_iso_date(payload.post_start, "post_start")
        post_end = (
            parse_iso_date(payload.post_end, "post_end") if payload.post_end else date.today()
        )
    except ValueError as exc:
        raise _http_from_app(exc) from exc
    if pre_end < pre_start:
        raise HTTPException(status_code=422, detail="pre_end debe ser >= pre_start")
    if post_end < post_start:
        raise HTTPException(status_code=422, detail="post_end debe ser >= post_start")

    applicant_email = payload.applicant_email.strip()
    applicant = db.query(User).filter(User.email.ilike(applicant_email)).first()
    order = FireOrder(
        tenant_id=(applicant.tenant_id if applicant else admin.tenant_id),
        created_by_user_id=admin.id,
        request_name=payload.request_name.strip(),
        department=(payload.department or None),
        applicant_name=payload.applicant_name.strip(),
        applicant_email=applicant_email,
        applicant_phone=(payload.applicant_phone or "").strip(),
        company=payload.company,
        geometry_geojson=geom,
        pre_start=pre_start,
        pre_end=pre_end,
        post_start=post_start,
        post_end=post_end,
        max_cloud_cover=int(round(float(payload.max_cloud_cover))),
        status="pendiente",
        extra_notes=payload.extra_notes,
    )
    db.add(order)
    db.flush()
    if applicant is not None:
        ensure_fire_order_project(db, order, applicant)
    db.commit()
    db.refresh(order)
    return _detail(order, db)


@router.get("/{order_id}", response_model=FireOrderDetail)
def get_fire_order(order_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        order = require_fire_order_access(order_id, user, db)
    except LookupError as exc:
        raise _http_from_app(exc) from exc
    return _detail(order, db)


@router.patch("/{order_id}", response_model=FireOrderDetail)
def patch_fire_order(
    order_id: int,
    payload: FireOrderStatusPatch,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        order = require_fire_order_admin(order_id, admin, db)
    except LookupError as exc:
        raise _http_from_app(exc) from exc
    order.status = payload.status
    db.commit()
    db.refresh(order)
    return _detail(order, db)


@router.post("/{order_id}/download-s2")
def start_fire_download(
    order_id: int,
    payload: FireOrderDownloadRequest | None = None,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        order = require_fire_order_admin(order_id, admin, db)
        body = payload or FireOrderDownloadRequest()
        out = EnqueueFireDownloadS2().execute(
            order=order,
            db=db,
            pre_start=body.pre_start,
            pre_end=body.pre_end,
            post_start=body.post_start,
            post_end=body.post_end,
            max_cloud_cover=body.max_cloud_cover,
        )
    except (LookupError, ValueError) as exc:
        raise _http_from_app(exc) from exc
    return {"ok": True, "task_id": out["task_id"], "order": _detail(out["order"], db)}


@router.get("/{order_id}/download-status")
def fire_download_status(
    order_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        order = require_fire_order_admin(order_id, admin, db)
    except LookupError as exc:
        raise _http_from_app(exc) from exc
    return {"order": _detail(order, db), "task": celery_task_meta(order.download_task_id)}


@router.post("/{order_id}/process-dnbr")
def start_fire_process_dnbr(
    order_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        order = require_fire_order_admin(order_id, admin, db)
        out = EnqueueFireProcessDnbr().execute(order=order, db=db)
    except (LookupError, ValueError) as exc:
        raise _http_from_app(exc) from exc
    return {"ok": True, "task_id": out["task_id"], "order": _detail(out["order"], db)}


@router.post("/{order_id}/validate-firms")
def start_fire_validate_firms(
    order_id: int,
    payload: FireOrderFirmsRequest | None = None,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        order = require_fire_order_admin(order_id, admin, db)
        body = payload or FireOrderFirmsRequest()
        out = EnqueueFireValidateFirms().execute(
            order=order, db=db, fire_start=body.fire_start, fire_end=body.fire_end
        )
    except (LookupError, ValueError) as exc:
        raise _http_from_app(exc) from exc
    return {
        "ok": True,
        "task_id": out["task_id"],
        "fire_start": out["fire_start"],
        "fire_end": out["fire_end"],
        "order": _detail(out["order"], db),
    }


@router.get("/{order_id}/pipeline-status")
def fire_pipeline_status(
    order_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        order = require_fire_order_access(order_id, user, db)
    except LookupError as exc:
        raise _http_from_app(exc) from exc
    tasks = GetFirePipelineStatus().execute(order=order)
    return {"order": _detail(order, db), **tasks}


@router.get("/{order_id}/results")
def list_fire_results(
    order_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        order = require_fire_order_access(order_id, user, db)
        return ListFireResultLayers().execute(
            order_id=order.id, request_name=order.request_name
        )
    except LookupError as exc:
        raise _http_from_app(exc) from exc


@router.get("/{order_id}/results/stats")
def fire_result_stats(
    order_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        order = require_fire_order_access(order_id, user, db)
        return FireResultStats().execute(order_id=order.id, request_name=order.request_name)
    except LookupError as exc:
        raise _http_from_app(exc) from exc


@router.get("/{order_id}/firms-live")
def fire_firms_live(
    order_id: int,
    hours: int = 48,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        order = require_fire_order_access(order_id, user, db)
    except LookupError as exc:
        raise _http_from_app(exc) from exc
    if hours not in (24, 48):
        raise HTTPException(status_code=422, detail="hours debe ser 24 o 48")

    map_key = (settings.firms_map_key or "").strip()
    if not map_key:
        import os

        map_key = (os.environ.get("FIRMS_MAP_KEY") or "").strip()
    if not map_key:
        raise HTTPException(
            status_code=503,
            detail=(
                "FIRMS_MAP_KEY no configurada. "
                "Solicite una clave en https://firms.modaps.eosdis.nasa.gov/api/map_key/"
            ),
        )
    if not order.geometry_geojson:
        raise HTTPException(status_code=400, detail="La solicitud no tiene geometría AOI")

    cached = get_firms_live_cached(order.id, hours)
    if cached is not None:
        return {
            "order_id": order.id,
            "request_name": order.request_name,
            "cached": True,
            "stale": False,
            **cached,
        }

    try:
        payload = GetFirmsLiveHotspots(NasaFirmsAreaAdapter()).execute(
            geometry_geojson=order.geometry_geojson,
            map_key=map_key,
            hours=hours,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        # Sin clave / config: no hay stale útil
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        stale = get_firms_live_stale(order.id, hours)
        if stale is not None:
            logger.warning("firms-live order %s failed; serving stale: %s", order_id, exc)
            return {
                "order_id": order.id,
                "request_name": order.request_name,
                "cached": True,
                "stale": True,
                "stale_reason": str(exc)[:240],
                **stale,
            }
        logger.exception("firms-live order %s", order_id)
        raise HTTPException(status_code=502, detail=f"Error consultando FIRMS: {exc}") from exc

    set_firms_live_cached(order.id, hours, payload)
    return {
        "order_id": order.id,
        "request_name": order.request_name,
        "cached": False,
        "stale": False,
        **payload,
    }


@router.get("/{order_id}/results/geojson")
def fire_result_geojson(
    order_id: int,
    name: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        require_fire_order_access(order_id, user, db)
        return FireResultGeojson().execute(order_id=order_id, filename=name)
    except LookupError as exc:
        raise _http_from_app(exc) from exc
    except ValueError as exc:
        raise _http_from_app(exc) from exc
    except Exception as exc:
        logger.exception("fire result geojson")
        raise HTTPException(status_code=500, detail=f"No se pudo leer GPKG: {exc}") from exc


@router.get("/{order_id}/results/preview")
def fire_result_preview(
    order_id: int,
    name: str,
    severity_class: int | None = None,
    format: str = Query(
        "json",
        description="json (bounds + opcional png_base64) | meta (solo bounds) | png (imagen binaria)",
    ),
    include_png: bool = Query(
        False,
        description="Si format=json, incluir png_base64 (pesado; preferir format=png).",
    ),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        require_fire_order_access(order_id, user, db)
        kind, payload = FireResultPreview().execute(
            order_id=order_id,
            filename=name,
            severity_class=severity_class,
            format=format,
            include_png=include_png,
        )
    except LookupError as exc:
        raise _http_from_app(exc) from exc
    except ValueError as exc:
        raise _http_from_app(exc) from exc
    except Exception as exc:
        logger.exception("fire result preview")
        raise HTTPException(status_code=500, detail=f"No se pudo generar preview: {exc}") from exc

    if kind == "png":
        bounds_list = payload["bounds"]
        return Response(
            content=payload["content"],
            media_type="image/png",
            headers={
                "X-Fire-Bounds": ",".join(str(x) for x in bounds_list),
                "X-Fire-Filename": payload["filename"],
                "Cache-Control": "private, max-age=120",
            },
        )
    return payload


@router.get("/{order_id}/results/tiles/{z}/{x}/{y}.png")
def fire_result_xyz_tile(
    order_id: int,
    z: int,
    x: int,
    y: int,
    name: str,
    severity_class: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        require_fire_order_access(order_id, user, db)
        png = FireResultXyzTile().execute(
            order_id=order_id,
            filename=name,
            z=z,
            x=x,
            y=y,
            severity_class=severity_class,
        )
    except LookupError as exc:
        raise _http_from_app(exc) from exc
    except ValueError as exc:
        raise _http_from_app(exc) from exc
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=300"},
    )
