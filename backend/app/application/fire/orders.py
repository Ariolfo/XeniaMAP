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
from app.domain.fire.repositories import FireOrderRepository
from app.domain.shared.ports import JobQueuePort, ProjectRepository
from app.infrastructure.composition import default_job_queue
from app.infrastructure.persistence.sqlalchemy_project_repository import (
    SqlAlchemyProjectRepository,
)
from app.infrastructure.persistence.sqlalchemy_uow import SqlAlchemyFireOrderRepository
from app.models.models import FireOrder, User

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


def project_name(
    order: FireOrder,
    *,
    projects: ProjectRepository,
) -> str | None:
    if not order.project_id:
        return None
    return projects.get_name(int(order.project_id))


def require_fire_order_access(
    order_id: int,
    user: User,
    *,
    fire_orders: FireOrderRepository,
) -> FireOrder:
    """Admin: mismo tenant. Cliente: applicant_email o created_by. Raises LookupError."""
    from app.domain.errors import AuthorizationError
    from app.domain.identity.policies import assert_can_access_fire_order

    order = fire_orders.get_by_id(order_id)
    if not order:
        raise LookupError("Solicitud Fire no encontrada")
    try:
        assert_can_access_fire_order(
            role=user.role,
            user_id=int(user.id),
            user_email=getattr(user, "email", None),
            user_tenant_id=int(user.tenant_id),
            order_tenant_id=int(order.tenant_id),
            applicant_email=getattr(order, "applicant_email", None),
            created_by_user_id=getattr(order, "created_by_user_id", None),
        )
    except AuthorizationError as exc:
        raise LookupError(exc.message) from exc
    return order


def require_fire_order_admin(
    order_id: int,
    admin: User,
    *,
    fire_orders: FireOrderRepository,
) -> FireOrder:
    order = fire_orders.get_by_id_for_tenant(order_id, tenant_id=int(admin.tenant_id))
    if not order:
        raise LookupError("Solicitud Fire no encontrada")
    return order


def fire_orders_repo(db: Session) -> FireOrderRepository:
    """Glue delivery→repo (API/tasks). Prefer ``SqlAlchemyUnitOfWork`` en código nuevo."""
    return SqlAlchemyFireOrderRepository(db)


def projects_repo(db: Session) -> ProjectRepository:
    return SqlAlchemyProjectRepository(db)


def unit_of_work_from_session(db: Session):
    """UoW tipado (H6) — repos Fire/Agro sin Session en UC."""
    from app.infrastructure.persistence.sqlalchemy_uow import unit_of_work

    return unit_of_work(db)


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
    def __init__(self, jobs: JobQueuePort | None = None) -> None:
        self._jobs = jobs or default_job_queue()

    def execute(
        self,
        *,
        order: FireOrder,
        fire_orders: FireOrderRepository,
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
        from app.domain.fire.order_status import FIRE_STATUS_EN_DESCARGA, assert_fire_order_transition

        order.status = assert_fire_order_transition(
            order.status, FIRE_STATUS_EN_DESCARGA, mode="pipeline"
        )
        order.download_message = "Encolando descarga Sentinel-2..."
        order.download_manifest = None
        fire_orders.save(order)

        from app.tasks.fire_jobs import fire_download_s2

        task_id = self._jobs.enqueue(
            fire_download_s2,
            order.id,
            settings.database_url,
            tenant_id=int(order.tenant_id),
            project_id=None,
            task_name="fire_download_s2",
        )
        order.download_task_id = task_id
        order.download_message = f"Descarga iniciada (task {task_id})"
        fire_orders.save(order)
        return {"ok": True, "task_id": task_id, "order": order}


class EnqueueFireProcessDnbr:
    def __init__(self, jobs: JobQueuePort | None = None) -> None:
        self._jobs = jobs or default_job_queue()

    def execute(self, *, order: FireOrder, fire_orders: FireOrderRepository) -> dict[str, Any]:
        if not order.data_root:
            raise ValueError("Primero debe descargar Sentinel-2 (paso 01) para esta solicitud.")
        results_root = fire_results_root(order.id)
        order.results_root = str(results_root)
        from app.domain.fire.order_status import FIRE_STATUS_PROCESANDO, assert_fire_order_transition

        order.status = assert_fire_order_transition(
            order.status, FIRE_STATUS_PROCESANDO, mode="pipeline"
        )
        order.process_message = "Encolando procesamiento dNBR..."
        order.process_manifest = None
        fire_orders.save(order)

        from app.tasks.fire_jobs import fire_process_dnbr

        task_id = self._jobs.enqueue(
            fire_process_dnbr,
            order.id,
            settings.database_url,
            tenant_id=int(order.tenant_id),
            project_id=None,
            task_name="fire_process_dnbr",
        )
        order.process_task_id = task_id
        order.process_message = f"Procesamiento dNBR iniciado (task {task_id})"
        fire_orders.save(order)
        return {"ok": True, "task_id": task_id, "order": order}


class EnqueueFireValidateFirms:
    def __init__(self, jobs: JobQueuePort | None = None) -> None:
        self._jobs = jobs or default_job_queue()

    def execute(
        self,
        *,
        order: FireOrder,
        fire_orders: FireOrderRepository,
        fire_start: str | None = None,
        fire_end: str | None = None,
    ) -> dict[str, Any]:
        if not order.results_root:
            raise ValueError("Primero debe ejecutar el procesamiento dNBR (paso 02).")
        start = fire_start or (
            order.pre_end.isoformat() if order.pre_end else order.post_start.isoformat()
        )
        end = fire_end or order.post_end.isoformat()

        from app.domain.fire.order_status import FIRE_STATUS_VALIDANDO, assert_fire_order_transition

        order.status = assert_fire_order_transition(
            order.status, FIRE_STATUS_VALIDANDO, mode="pipeline"
        )
        order.firms_message = "Encolando validación FIRMS..."
        order.firms_manifest = None
        fire_orders.save(order)

        from app.tasks.fire_jobs import fire_validate_firms

        task_id = self._jobs.enqueue(
            fire_validate_firms,
            order.id,
            settings.database_url,
            start,
            end,
            tenant_id=int(order.tenant_id),
            project_id=None,
            task_name="fire_validate_firms",
        )
        order.firms_task_id = task_id
        order.firms_message = f"Validación FIRMS iniciada (task {task_id})"
        fire_orders.save(order)
        return {
            "ok": True,
            "task_id": task_id,
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
