"""Casos de uso: CRUD / acceso / encolado de pipeline Fire."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Any

import geopandas as gpd
from sqlalchemy.orm import Session

from app.application.fire.results import fire_results_root, fire_storage_root
from app.core.config import settings
from app.models.models import FireOrder, Project, User

logger = logging.getLogger(__name__)


def parse_iso_date(value: str, field: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except Exception as exc:
        raise ValueError(f"{field} inválida (YYYY-MM-DD)") from exc


def normalize_geometry(raw: dict) -> dict:
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
    except ValueError:
        raise
    except Exception as e:
        logger.warning("GeoJSON inválido: %s", e)
        raise ValueError("GeoJSON inválido o no compatible") from e
    if gdf.empty:
        raise ValueError("Sin geometrías")
    try:
        if gdf.crs is not None:
            gdf = gdf.to_crs(4326)
    except Exception:
        pass
    for geom in gdf.geometry:
        if geom is None or geom.is_empty:
            raise ValueError("Geometría vacía")
        if geom.geom_type not in ("Polygon", "MultiPolygon"):
            raise ValueError("Solo se permiten polígonos o multipolígonos")
    return json.loads(gdf.to_json())


def project_name(db: Session, order: FireOrder) -> str | None:
    if not order.project_id:
        return None
    p = db.query(Project).filter(Project.id == order.project_id).first()
    return p.name if p else None


def require_fire_order_access(order_id: int, user: User, db: Session) -> FireOrder:
    """Admin: mismo tenant. Cliente: applicant_email o created_by. Raises LookupError."""
    order = db.query(FireOrder).filter(FireOrder.id == order_id).first()
    if not order:
        raise LookupError("Solicitud Fire no encontrada")
    role = str(user.role or "").lower()
    if role == "admin":
        if order.tenant_id != user.tenant_id:
            raise LookupError("Solicitud Fire no encontrada")
    else:
        email = str(user.email or "").strip().lower()
        order_email = str(order.applicant_email or "").strip().lower()
        if order_email != email and order.created_by_user_id != user.id:
            raise LookupError("Solicitud Fire no encontrada")
    return order


def require_fire_order_admin(order_id: int, admin: User, db: Session) -> FireOrder:
    order = (
        db.query(FireOrder)
        .filter(FireOrder.id == order_id, FireOrder.tenant_id == admin.tenant_id)
        .first()
    )
    if not order:
        raise LookupError("Solicitud Fire no encontrada")
    return order


def celery_task_meta(task_id: str | None) -> dict[str, Any] | None:
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


class EnqueueFireDownloadS2:
    def execute(
        self,
        *,
        order: FireOrder,
        db: Session,
        pre_start: str | None = None,
        pre_end: str | None = None,
        post_start: str | None = None,
        post_end: str | None = None,
        max_cloud_cover: float | None = None,
    ) -> dict[str, Any]:
        if pre_start:
            order.pre_start = parse_iso_date(pre_start, "pre_start")
        if pre_end:
            order.pre_end = parse_iso_date(pre_end, "pre_end")
        if post_start:
            order.post_start = parse_iso_date(post_start, "post_start")
        if post_end:
            order.post_end = parse_iso_date(post_end, "post_end")
        if max_cloud_cover is not None:
            order.max_cloud_cover = int(round(float(max_cloud_cover)))
        else:
            order.max_cloud_cover = int(order.max_cloud_cover or 95)

        if order.pre_end < order.pre_start:
            raise ValueError("pre_end debe ser >= pre_start")
        if order.post_end < order.post_start:
            raise ValueError("post_end debe ser >= post_start")

        data_root = fire_storage_root(order.id)
        order.data_root = str(data_root)
        order.status = "en_descarga"
        order.download_message = "Encolando descarga Sentinel-2..."
        order.download_manifest = None
        db.commit()

        from app.core.celery_task_registry import register_celery_task
        from app.tasks.fire_jobs import fire_download_s2

        async_result = fire_download_s2.delay(order.id, settings.database_url)
        order.download_task_id = async_result.id
        order.download_message = f"Descarga iniciada (task {async_result.id})"
        db.commit()
        register_celery_task(
            async_result.id,
            tenant_id=int(order.tenant_id),
            project_id=None,
            task_name="fire_download_s2",
        )
        db.refresh(order)
        return {"ok": True, "task_id": async_result.id, "order": order}


class EnqueueFireProcessDnbr:
    def execute(self, *, order: FireOrder, db: Session) -> dict[str, Any]:
        if not order.data_root:
            raise ValueError("Primero debe descargar Sentinel-2 (paso 01) para esta solicitud.")
        results_root = fire_results_root(order.id)
        order.results_root = str(results_root)
        order.status = "procesando"
        order.process_message = "Encolando procesamiento dNBR..."
        order.process_manifest = None
        db.commit()

        from app.core.celery_task_registry import register_celery_task
        from app.tasks.fire_jobs import fire_process_dnbr

        async_result = fire_process_dnbr.delay(order.id, settings.database_url)
        order.process_task_id = async_result.id
        order.process_message = f"Procesamiento dNBR iniciado (task {async_result.id})"
        db.commit()
        register_celery_task(
            async_result.id,
            tenant_id=int(order.tenant_id),
            project_id=None,
            task_name="fire_process_dnbr",
        )
        db.refresh(order)
        return {"ok": True, "task_id": async_result.id, "order": order}


class EnqueueFireValidateFirms:
    def execute(
        self,
        *,
        order: FireOrder,
        db: Session,
        fire_start: str | None = None,
        fire_end: str | None = None,
    ) -> dict[str, Any]:
        if not order.results_root:
            raise ValueError("Primero debe ejecutar el procesamiento dNBR (paso 02).")
        start = fire_start or (
            order.pre_end.isoformat() if order.pre_end else order.post_start.isoformat()
        )
        end = fire_end or order.post_end.isoformat()

        order.status = "validando"
        order.firms_message = "Encolando validación FIRMS..."
        order.firms_manifest = None
        db.commit()

        from app.core.celery_task_registry import register_celery_task
        from app.tasks.fire_jobs import fire_validate_firms

        async_result = fire_validate_firms.delay(
            order.id, settings.database_url, start, end
        )
        order.firms_task_id = async_result.id
        order.firms_message = f"Validación FIRMS iniciada (task {async_result.id})"
        db.commit()
        register_celery_task(
            async_result.id,
            tenant_id=int(order.tenant_id),
            project_id=None,
            task_name="fire_validate_firms",
        )
        db.refresh(order)
        return {
            "ok": True,
            "task_id": async_result.id,
            "fire_start": start,
            "fire_end": end,
            "order": order,
        }


class GetFirePipelineStatus:
    def execute(self, *, order: FireOrder) -> dict[str, Any]:
        return {
            "download_task": celery_task_meta(order.download_task_id),
            "process_task": celery_task_meta(getattr(order, "process_task_id", None)),
            "firms_task": celery_task_meta(getattr(order, "firms_task_id", None)),
        }
