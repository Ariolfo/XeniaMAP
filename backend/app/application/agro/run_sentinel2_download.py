"""Caso de uso Agro: ejecución worker de descarga Sentinel-2 (H4)."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Callable

logger = logging.getLogger(__name__)

ProgressFn = Callable[..., None]


class RunSentinel2DownloadJob:
    """Worker: search+download mensual vía ``services.sentinel2`` (algoritmo GIS)."""

    def execute(
        self,
        *,
        wkt: str,
        start_date_str: str,
        end_date_str: str,
        output_dir: str,
        raster_layer_id: int,
        db_url: str,
        update_state: ProgressFn | None = None,
    ) -> dict[str, Any]:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.orm.attributes import flag_modified

        from app.models.models import RasterLayer
        from app.services.sentinel2 import get_copernicus_credentials, search_and_download_monthly
        from app.tasks.jobs import _update_raster_sentinel_status

        copernicus_user, copernicus_password = get_copernicus_credentials()

        def progress_cb(current: int, total: int, message: str) -> None:
            pct = int((current / max(total, 1)) * 100)
            if update_state:
                update_state(
                    state="PROGRESS",
                    meta={"progress": pct, "message": message, "phase": "downloading"},
                )
            _update_raster_sentinel_status(
                db_url,
                raster_layer_id,
                {"progress": pct, "progress_message": message, "status": "downloading"},
            )

        if update_state:
            update_state(
                state="PROGRESS",
                meta={"progress": 0, "message": "Iniciando...", "phase": "downloading"},
            )
        start = date.fromisoformat(start_date_str)
        end = date.fromisoformat(end_date_str)

        try:
            result = search_and_download_monthly(
                wkt,
                start,
                end,
                output_dir,
                copernicus_user,
                copernicus_password,
                progress_callback=progress_cb,
            )
        except Exception as exc:
            logger.exception("Sentinel-2 download failed")
            _update_raster_sentinel_status(
                db_url,
                raster_layer_id,
                {
                    "status": "failed",
                    "error": str(exc),
                    "progress": 0,
                    "progress_message": f"Error: {exc}",
                },
            )
            raise

        try:
            engine = create_engine(db_url)
            Session = sessionmaker(bind=engine)
            db = Session()
            raster = db.query(RasterLayer).filter(RasterLayer.id == raster_layer_id).first()
            if raster:
                meta = {
                    **(raster.raster_metadata or {}),
                    "status": "completed",
                    "total_downloaded": result["total_downloaded"],
                    "total_size_mb": result["total_size_mb"],
                    "files": [str(f) for f in result["files"]],
                    "skipped_low_coverage": result.get("skipped_low_coverage", 0),
                    "skipped_high_cloud": result.get("skipped_high_cloud", 0),
                    "progress": 100,
                    "progress_message": "Descarga terminada",
                }
                if result["files"]:
                    meta["primary_file"] = result["files"][0]
                    raster.file_path = result["files"][0]
                raster.raster_metadata = meta
                flag_modified(raster, "raster_metadata")
                db.commit()
            db.close()
        except Exception:
            logger.exception("Error updating raster metadata after S2 download")

        if update_state:
            update_state(
                state="SUCCESS",
                meta={"progress": 100, "message": "Terminado", "phase": "completed"},
            )
        return result
