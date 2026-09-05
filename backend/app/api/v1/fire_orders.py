"""API independiente del módulo Fire (severidad de incendios)."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path

import geopandas as gpd
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.core.config import settings
from app.db.session import get_db
from app.models.models import FireOrder, Project, User
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


def _parse_date(value: str, field: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"{field} inválida (YYYY-MM-DD)") from exc


def _normalize_geometry(raw: dict) -> dict:
    try:
        t = raw.get("type")
        if t == "FeatureCollection":
            gdf = gpd.GeoDataFrame.from_features(raw["features"], crs="EPSG:4326")
        elif t == "Feature":
            gdf = gpd.GeoDataFrame.from_features([raw], crs="EPSG:4326")
        elif t in ("Polygon", "MultiPolygon"):
            gdf = gpd.GeoDataFrame.from_features(
                [{"type": "Feature", "properties": {}, "geometry": raw}],
                crs="EPSG:4326",
            )
        else:
            raise ValueError(f"tipo GeoJSON no soportado: {t}")
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("GeoJSON inválido: %s", e)
        raise HTTPException(status_code=422, detail="GeoJSON inválido o no compatible") from e
    if gdf.empty:
        raise HTTPException(status_code=422, detail="Sin geometrías")
    try:
        if gdf.crs is not None:
            gdf = gdf.to_crs(4326)
    except Exception:
        pass
    for geom in gdf.geometry:
        if geom is None or geom.is_empty:
            raise HTTPException(status_code=422, detail="Geometría vacía")
        if geom.geom_type not in ("Polygon", "MultiPolygon"):
            raise HTTPException(status_code=422, detail="Solo se permiten polígonos o multipolígonos")
    return json.loads(gdf.to_json())


def _project_name(db: Session, order: FireOrder) -> str | None:
    if not order.project_id:
        return None
    p = db.query(Project).filter(Project.id == order.project_id).first()
    return p.name if p else None


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
        project_name=_project_name(db, order) if db is not None else None,
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
        project_name=_project_name(db, order) if db is not None else None,
    )


def _fire_storage_root(order_id: int) -> Path:
    root = Path(settings.storage_path) / "fire" / f"order_{order_id}" / "s2"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _fire_results_root(order_id: int) -> Path:
    root = Path(settings.storage_path) / "fire" / f"order_{order_id}" / "results"
    root.mkdir(parents=True, exist_ok=True)
    return root


@router.post("/seed-tolima")
def seed_tolima(
    applicant_email: str = "ariolfoc@gmail.com",
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Precarga una solicitud por municipio desde Incendios_Tolima.shp.

    Por defecto las asigna al solicitante ``ariolfoc@gmail.com`` y crea
    proyectos visibles para ese cliente.
    """
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
    """Crea/vincula Project + polígono para las solicitudes Fire del solicitante."""
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
        # Cliente: solo sus solicitudes (email case-insensitive)
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
    geom = _normalize_geometry(payload.geometry)
    pre_start = _parse_date(payload.pre_start, "pre_start")
    pre_end = _parse_date(payload.pre_end, "pre_end")
    post_start = _parse_date(payload.post_start, "post_start")
    post_end = _parse_date(payload.post_end, "post_end") if payload.post_end else date.today()
    if pre_end < pre_start:
        raise HTTPException(status_code=422, detail="pre_end debe ser >= pre_start")
    if post_end < post_start:
        raise HTTPException(status_code=422, detail="post_end debe ser >= post_start")

    applicant_email = payload.applicant_email.strip()
    applicant = (
        db.query(User)
        .filter(User.email.ilike(applicant_email))
        .first()
    )
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
    order = db.query(FireOrder).filter(FireOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Solicitud Fire no encontrada")
    role = str(user.role or "").lower()
    if role == "admin":
        if order.tenant_id != user.tenant_id:
            raise HTTPException(status_code=404, detail="Solicitud Fire no encontrada")
    else:
        email = str(user.email or "").strip().lower()
        order_email = str(order.applicant_email or "").strip().lower()
        if order_email != email and order.created_by_user_id != user.id:
            raise HTTPException(status_code=404, detail="Solicitud Fire no encontrada")
    return _detail(order, db)


@router.patch("/{order_id}", response_model=FireOrderDetail)
def patch_fire_order(
    order_id: int,
    payload: FireOrderStatusPatch,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    order = (
        db.query(FireOrder)
        .filter(FireOrder.id == order_id, FireOrder.tenant_id == admin.tenant_id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Solicitud Fire no encontrada")
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
    """
    Lanza descarga parcial Sentinel-2 L2A (metodología script 01 Tolima).
    Fechas y MAX_CLOUD_COVER editables; default cloud = 95%.
    """
    order = (
        db.query(FireOrder)
        .filter(FireOrder.id == order_id, FireOrder.tenant_id == admin.tenant_id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Solicitud Fire no encontrada")

    body = payload or FireOrderDownloadRequest()
    if body.pre_start:
        order.pre_start = _parse_date(body.pre_start, "pre_start")
    if body.pre_end:
        order.pre_end = _parse_date(body.pre_end, "pre_end")
    if body.post_start:
        order.post_start = _parse_date(body.post_start, "post_start")
    if body.post_end:
        order.post_end = _parse_date(body.post_end, "post_end")
    if body.max_cloud_cover is not None:
        order.max_cloud_cover = int(round(float(body.max_cloud_cover)))
    else:
        order.max_cloud_cover = int(order.max_cloud_cover or 95)

    if order.pre_end < order.pre_start:
        raise HTTPException(status_code=422, detail="pre_end debe ser >= pre_start")
    if order.post_end < order.post_start:
        raise HTTPException(status_code=422, detail="post_end debe ser >= post_start")

    data_root = _fire_storage_root(order.id)
    order.data_root = str(data_root)
    order.status = "en_descarga"
    order.download_message = "Encolando descarga Sentinel-2..."
    order.download_manifest = None
    db.commit()

    from app.tasks.jobs import fire_download_s2

    async_result = fire_download_s2.delay(
        order.id,
        settings.database_url,
    )
    order.download_task_id = async_result.id
    order.download_message = f"Descarga iniciada (task {async_result.id})"
    db.commit()
    db.refresh(order)
    return {
        "ok": True,
        "task_id": async_result.id,
        "order": _detail(order, db),
    }


@router.get("/{order_id}/download-status")
def fire_download_status(
    order_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    order = (
        db.query(FireOrder)
        .filter(FireOrder.id == order_id, FireOrder.tenant_id == admin.tenant_id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Solicitud Fire no encontrada")

    task_meta = None
    if order.download_task_id:
        try:
            from app.tasks.celery_app import celery_app

            res = celery_app.AsyncResult(order.download_task_id)
            task_meta = {
                "task_id": order.download_task_id,
                "state": res.state,
                "info": res.info if isinstance(res.info, dict) else {"raw": str(res.info)},
            }
        except Exception as exc:
            task_meta = {"task_id": order.download_task_id, "error": str(exc)}

    return {
        "order": _detail(order, db),
        "task": task_meta,
    }


@router.post("/{order_id}/process-dnbr")
def start_fire_process_dnbr(
    order_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Lanza script 02 (dNBR / severidad / candidatos) sobre la solicitud."""
    order = (
        db.query(FireOrder)
        .filter(FireOrder.id == order_id, FireOrder.tenant_id == admin.tenant_id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Solicitud Fire no encontrada")
    if not order.data_root:
        raise HTTPException(
            status_code=400,
            detail="Primero debe descargar Sentinel-2 (paso 01) para esta solicitud.",
        )

    results_root = _fire_results_root(order.id)
    order.results_root = str(results_root)
    order.status = "procesando"
    order.process_message = "Encolando procesamiento dNBR..."
    order.process_manifest = None
    db.commit()

    from app.tasks.jobs import fire_process_dnbr

    async_result = fire_process_dnbr.delay(order.id, settings.database_url)
    order.process_task_id = async_result.id
    order.process_message = f"Procesamiento dNBR iniciado (task {async_result.id})"
    db.commit()
    db.refresh(order)
    return {"ok": True, "task_id": async_result.id, "order": _detail(order, db)}


@router.post("/{order_id}/validate-firms")
def start_fire_validate_firms(
    order_id: int,
    payload: FireOrderFirmsRequest | None = None,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Lanza script 03 (validación FIRMS/VIIRS) sobre candidatos dNBR."""
    order = (
        db.query(FireOrder)
        .filter(FireOrder.id == order_id, FireOrder.tenant_id == admin.tenant_id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Solicitud Fire no encontrada")
    if not order.results_root:
        raise HTTPException(
            status_code=400,
            detail="Primero debe ejecutar el procesamiento dNBR (paso 02).",
        )

    body = payload or FireOrderFirmsRequest()
    # Default FIRMS window: day after PRE end .. POST end
    fire_start = body.fire_start or (order.pre_end.isoformat() if order.pre_end else order.post_start.isoformat())
    fire_end = body.fire_end or order.post_end.isoformat()

    order.status = "validando"
    order.firms_message = "Encolando validación FIRMS..."
    order.firms_manifest = None
    db.commit()

    from app.tasks.jobs import fire_validate_firms

    async_result = fire_validate_firms.delay(
        order.id,
        settings.database_url,
        fire_start,
        fire_end,
    )
    order.firms_task_id = async_result.id
    order.firms_message = f"Validación FIRMS iniciada (task {async_result.id})"
    db.commit()
    db.refresh(order)
    return {
        "ok": True,
        "task_id": async_result.id,
        "fire_start": fire_start,
        "fire_end": fire_end,
        "order": _detail(order, db),
    }


@router.get("/{order_id}/pipeline-status")
def fire_pipeline_status(
    order_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = db.query(FireOrder).filter(FireOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Solicitud Fire no encontrada")
    role = str(user.role or "").lower()
    if role == "admin":
        if order.tenant_id != user.tenant_id:
            raise HTTPException(status_code=404, detail="Solicitud Fire no encontrada")
    else:
        email = str(user.email or "").strip().lower()
        order_email = str(order.applicant_email or "").strip().lower()
        if order_email != email and order.created_by_user_id != user.id:
            raise HTTPException(status_code=404, detail="Solicitud Fire no encontrada")

    def _task_meta(task_id: str | None):
        if not task_id:
            return None
        try:
            from app.tasks.celery_app import celery_app

            res = celery_app.AsyncResult(task_id)
            return {
                "task_id": task_id,
                "state": res.state,
                "info": res.info if isinstance(res.info, dict) else {"raw": str(res.info)},
            }
        except Exception as exc:
            return {"task_id": task_id, "error": str(exc)}

    return {
        "order": _detail(order, db),
        "download_task": _task_meta(order.download_task_id),
        "process_task": _task_meta(getattr(order, "process_task_id", None)),
        "firms_task": _task_meta(getattr(order, "firms_task_id", None)),
    }
