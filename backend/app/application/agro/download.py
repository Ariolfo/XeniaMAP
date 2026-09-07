"""Casos de uso Agro: descarga de rasters de proyecto (S2 + stub)."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from sqlalchemy.orm import Session

from app.core.storage_paths import _tenant_storage, ensure_external_sensor_download_dirs
from app.domain.shared.ports import JobQueuePort
from app.infrastructure.composition import default_job_queue
from app.models.models import RasterLayer


class StartSentinel2ProjectDownload:
    """
    Valida destino/credenciales, crea RasterLayer en estado downloading
    y encola ``tasks.download_sentinel2`` vía ``JobQueuePort``.
    """

    def __init__(self, jobs: JobQueuePort | None = None) -> None:
        self._jobs = jobs or default_job_queue()

    def execute(
        self,
        *,
        db: Session,
        tenant_id: int,
        project_id: int,
        start_date: str | None,
        end_date: str | None,
        download_subpath: str | None,
        wkt: str | None,
        copernicus_configured: bool,
        database_url: str,
    ) -> dict[str, Any]:
        if not copernicus_configured:
            raise RuntimeError("Copernicus credentials not configured")
        if not start_date or not end_date:
            raise ValueError("start_date and end_date are required for Sentinel-2")
        if not download_subpath or not str(download_subpath).strip().startswith("ext:"):
            raise ValueError(
                "Indica la carpeta de destino en el disco externo (download_subpath ext:…)."
            )
        if not wkt:
            raise ValueError(
                "No vector layer found in project to define download area. Upload a lote first."
            )

        try:
            out_dir, _s1_parent, encoded_dest = ensure_external_sensor_download_dirs(
                download_subpath, "s2"
            )
        except ValueError:
            raise

        raster = RasterLayer(
            project_id=project_id,
            tenant_id=tenant_id,
            name=f"Sentinel-2 ({start_date} a {end_date})",
            file_path=str(out_dir),
            cog_path=None,
            raster_metadata={
                "source": "sentinel-2",
                "type": "download",
                "status": "downloading",
                "start_date": start_date,
                "end_date": end_date,
                "download_subpath": encoded_dest,
                "download_root": str(out_dir),
            },
        )
        db.add(raster)
        db.commit()
        db.refresh(raster)

        from app.tasks.jobs import download_sentinel2

        task_id = self._jobs.enqueue(
            download_sentinel2,
            wkt,
            start_date,
            end_date,
            str(out_dir),
            raster.id,
            database_url,
            tenant_id=tenant_id,
            project_id=project_id,
            task_name="download_sentinel2",
        )

        raster.raster_metadata = {
            **(raster.raster_metadata or {}),
            "celery_task_id": task_id,
        }
        db.commit()

        return {
            "status": "downloading",
            "raster_layer_id": raster.id,
            "task_id": task_id,
            "output_dir": str(out_dir),
            "download_subpath": encoded_dest,
        }


class WriteStubProjectDownload:
    """Descarga stub (fuente no Sentinel-2): escribe un GeoTIFF sintético."""

    def execute(
        self,
        *,
        db: Session,
        tenant_id: int,
        project_id: int,
        source: str,
    ) -> dict[str, Any]:
        out_dir = _tenant_storage(tenant_id, project_id, "rasters")
        out_path = out_dir / f"download_{source}_{uuid.uuid4().hex}.tif"

        width, height = 256, 256
        data = (np.random.rand(height, width) * 255).astype("uint8")
        transform = rasterio.transform.from_origin(-74.2, 4.9, 0.0005, 0.0005)
        with rasterio.open(
            out_path,
            "w",
            driver="GTiff",
            height=height,
            width=width,
            count=1,
            dtype=data.dtype,
            crs="EPSG:4326",
            transform=transform,
        ) as dst:
            dst.write(data, 1)

        raster = RasterLayer(
            project_id=project_id,
            tenant_id=tenant_id,
            name=f"{source}.tif",
            file_path=str(out_path),
            cog_path=str(out_path),
            raster_metadata={"source": source, "type": "download"},
        )
        db.add(raster)
        db.commit()
        db.refresh(raster)
        return {"status": "ok", "raster_layer_id": raster.id}


def parse_sentinel1_layer_id(layer_id: str | int | None) -> int | None:
    """Normaliza layer_id de Form; ValueError si inválido."""
    if layer_id is None or str(layer_id).strip() == "":
        return None
    try:
        lid = int(layer_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("layer_id inválido") from exc
    if lid < 1:
        raise ValueError("layer_id inválido")
    return lid


# Alias genérico (S1 / PS / etc.)
parse_optional_layer_id = parse_sentinel1_layer_id


class StartSentinel1ProjectDownload:
    """
    Valida AOI/fechas/destino, crea RasterLayer downloading y encola ``tasks.download_sentinel1``.
    El WKT ya debe venir resuelto (capa o archivo AOI) desde el controller.
    """

    def execute(
        self,
        *,
        db: Session,
        tenant_id: int,
        project_id: int,
        start_date: str,
        end_date: str,
        download_subpath: str | None,
        wkt: str | None,
        layer_id: int | None,
        images_per_month: int,
        copernicus_configured: bool,
        database_url: str,
    ) -> dict[str, Any]:
        from datetime import date as date_cls

        if not copernicus_configured:
            raise RuntimeError("Copernicus credentials not configured")
        if not download_subpath or not str(download_subpath).strip().startswith("ext:"):
            raise ValueError(
                "Indica la carpeta de destino en el disco externo (download_subpath ext:…)."
            )
        if not wkt:
            raise ValueError("AOI vacío o inválido.")

        try:
            d0 = date_cls.fromisoformat(str(start_date).strip())
            d1 = date_cls.fromisoformat(str(end_date).strip())
        except ValueError as exc:
            raise ValueError("Fechas inválidas; use YYYY-MM-DD") from exc
        if d1 < d0:
            raise ValueError("La fecha final debe ser >= fecha inicial")
        if images_per_month not in {0, 1, 2, 3}:
            raise ValueError("images_per_month debe ser 0 (todas), 1, 2 o 3")

        try:
            sensor_dir, s1_parent, encoded_dest = ensure_external_sensor_download_dirs(
                str(download_subpath).strip(), "s1"
            )
        except ValueError:
            raise

        raster = RasterLayer(
            project_id=project_id,
            tenant_id=tenant_id,
            name=f"Sentinel-1 GRD IW ({start_date} a {end_date})",
            file_path=str(sensor_dir),
            cog_path=None,
            raster_metadata={
                "source": "sentinel-1",
                "type": "download",
                "status": "downloading",
                "start_date": start_date,
                "end_date": end_date,
                "layer_id": layer_id,
                "images_per_month": images_per_month,
                "download_subpath": encoded_dest,
                "download_root": str(sensor_dir),
            },
        )
        db.add(raster)
        db.commit()
        db.refresh(raster)

        from app.tasks.jobs import download_sentinel1

        try:
            async_result = download_sentinel1.delay(
                wkt,
                str(start_date).strip(),
                str(end_date).strip(),
                str(s1_parent),
                raster.id,
                database_url,
                images_per_month,
            )
        except Exception as exc:
            raise RuntimeError(
                f"No se pudo encolar la descarga Sentinel-1. ¿Redis y worker activos? {exc!s}"
            ) from exc

        raster.raster_metadata = {
            **(raster.raster_metadata or {}),
            "celery_task_id": async_result.id,
        }
        db.commit()
        register_celery_task(
            async_result.id,
            tenant_id=tenant_id,
            project_id=project_id,
            task_name="download_sentinel1",
        )

        return {
            "status": "downloading",
            "raster_layer_id": raster.id,
            "task_id": async_result.id,
            "output_dir": str(sensor_dir),
            "download_subpath": encoded_dest,
            "sentinel1_subdir": str(sensor_dir),
        }


class GetSentinelDownloadStatus:
    """Estado de descarga S1/S2 desde metadata DB + Celery AsyncResult."""

    def execute(
        self,
        *,
        db: Session,
        tenant_id: int,
        project_id: int,
        raster_id: int,
    ) -> dict[str, Any]:
        from celery.result import AsyncResult

        from app.tasks.celery_app import celery_app

        raster = (
            db.query(RasterLayer)
            .filter(
                RasterLayer.id == raster_id,
                RasterLayer.project_id == project_id,
                RasterLayer.tenant_id == tenant_id,
            )
            .first()
        )
        if not raster:
            raise LookupError("Raster not found")

        meta = raster.raster_metadata or {}
        db_status = meta.get("status")
        progress = int(meta.get("progress", 0) or 0)
        message = meta.get("progress_message") or "Preparando descarga..."

        def _s1_extra(target: dict[str, Any]) -> None:
            if meta.get("source") == "sentinel-1":
                target["selected_relative_orbit"] = meta.get("selected_relative_orbit")
                target["selected_orbit_direction"] = meta.get("selected_orbit_direction")
                target["selected_pass_short"] = meta.get("selected_pass_short")
                target["date_range_start"] = meta.get("date_range_start")
                target["date_range_end"] = meta.get("date_range_end")
                target["csv_path"] = meta.get("csv_path")

        if db_status == "completed":
            done = {
                "ui_status": "completed",
                "progress": 100,
                "message": meta.get("progress_message") or "Descarga terminada",
                "total_downloaded": meta.get("total_downloaded"),
                "total_size_mb": meta.get("total_size_mb"),
                "skipped_low_coverage": meta.get("skipped_low_coverage"),
                "skipped_high_cloud": meta.get("skipped_high_cloud"),
            }
            _s1_extra(done)
            return done

        if db_status == "failed":
            return {
                "ui_status": "failed",
                "progress": 0,
                "message": meta.get("error") or meta.get("progress_message") or "Error en descarga",
            }

        task_id = meta.get("celery_task_id")
        celery_state = None
        if task_id:
            ar = AsyncResult(task_id, app=celery_app)
            celery_state = ar.state

            if celery_state == "PROGRESS" and isinstance(ar.info, dict):
                cp = int(ar.info.get("progress", 0) or 0)
                cm = ar.info.get("message")
                progress = max(progress, cp)
                if cm:
                    message = str(cm)

            if celery_state == "SUCCESS" or (ar.ready() and ar.successful()):
                done = {
                    "ui_status": "completed",
                    "progress": 100,
                    "message": meta.get("progress_message") or "Descarga terminada",
                    "total_downloaded": meta.get("total_downloaded"),
                    "total_size_mb": meta.get("total_size_mb"),
                    "skipped_low_coverage": meta.get("skipped_low_coverage"),
                    "skipped_high_cloud": meta.get("skipped_high_cloud"),
                    "celery_state": celery_state,
                }
                _s1_extra(done)
                return done

            if celery_state == "FAILURE" or (ar.ready() and ar.failed()):
                err = str(ar.result) if ar.result else "Error en la tarea"
                return {
                    "ui_status": "failed",
                    "progress": 0,
                    "message": err,
                    "celery_state": celery_state,
                }

        return {
            "ui_status": "downloading",
            "progress": progress,
            "message": message,
            "celery_state": celery_state,
        }

