import logging

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.fire_download_s2", bind=True)
def fire_download_s2(self, order_id: int, db_url: str) -> dict:
    """Descarga parcial S2 L2A para una solicitud Fire (metodología Tolima script 01)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.orm.attributes import flag_modified

    from app.models.models import FireOrder
    from app.application.fire.download_s2 import DownloadFireS2

    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        order = db.query(FireOrder).filter(FireOrder.id == int(order_id)).first()
        if not order:
            raise RuntimeError(f"FireOrder {order_id} not found")

        def progress_cb(current: int, total: int, message: str) -> None:
            pct = int((current / max(total, 1)) * 100)
            self.update_state(
                state="PROGRESS",
                meta={"progress": pct, "message": message, "phase": "fire_download"},
            )
            try:
                order.download_message = message
                db.commit()
            except Exception:
                db.rollback()

        self.update_state(
            state="PROGRESS",
            meta={"progress": 1, "message": "Iniciando descarga Fire S2...", "phase": "fire_download"},
        )
        order.status = "en_descarga"
        order.download_message = "Iniciando descarga Fire S2..."
        db.commit()

        data_root = order.data_root
        if not data_root:
            from pathlib import Path

            from app.core.config import settings

            data_root = str(Path(settings.storage_path) / "fire" / f"order_{order.id}" / "s2")
            order.data_root = data_root
            db.commit()

        result = DownloadFireS2().execute(
            geometry=order.geometry_geojson,
            pre_start=order.pre_start.isoformat(),
            pre_end=order.pre_end.isoformat(),
            post_start=order.post_start.isoformat(),
            post_end=order.post_end.isoformat(),
            max_cloud_cover=float(order.max_cloud_cover or 95),
            output_root=data_root,
            progress=progress_cb,
        )
        order.status = "descargado"
        order.download_message = (
            f"OK: PRE={result['pre']['product_count']} POST={result['post']['product_count']} "
            f"({result.get('backend')}, {result.get('elapsed_sec')}s)"
        )
        order.download_manifest = result
        flag_modified(order, "download_manifest")
        db.commit()
        self.update_state(
            state="SUCCESS",
            meta={"progress": 100, "message": order.download_message, "phase": "completed"},
        )
        return result
    except Exception as exc:
        logger.exception("Fire S2 download failed for order %s", order_id)
        try:
            order = db.query(FireOrder).filter(FireOrder.id == int(order_id)).first()
            if order:
                order.status = "error"
                order.download_message = str(exc)
                db.commit()
        except Exception:
            db.rollback()
        self.update_state(
            state="FAILURE",
            meta={"progress": 0, "message": str(exc), "phase": "failed"},
        )
        raise
    finally:
        db.close()


@celery_app.task(name="tasks.fire_process_dnbr", bind=True)
def fire_process_dnbr(self, order_id: int, db_url: str) -> dict:
    """Procesa dNBR/severidad (script 02) para una solicitud Fire."""
    from pathlib import Path

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.orm.attributes import flag_modified

    from app.application.fire.process_dnbr import ProcessDnbrPipeline
    from app.core.config import settings
    from app.models.models import FireOrder
    from app.modules.fire.aoi_io import order_paths, write_order_aoi_gpkg

    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        order = db.query(FireOrder).filter(FireOrder.id == int(order_id)).first()
        if not order:
            raise RuntimeError(f"FireOrder {order_id} not found")

        self.update_state(
            state="PROGRESS",
            meta={"progress": 5, "message": "Preparando AOI y rutas...", "phase": "fire_dnbr"},
        )
        order.status = "procesando"
        order.process_message = "Preparando AOI y rutas..."
        db.commit()

        paths = order_paths(settings.storage_path, order.id)
        s2_root = Path(order.data_root) if order.data_root else paths["s2"]
        results_root = paths["results"]
        results_root.mkdir(parents=True, exist_ok=True)
        order.results_root = str(results_root)

        write_order_aoi_gpkg(
            geometry_geojson=order.geometry_geojson,
            request_name=order.request_name,
            department=order.department,
            output_path=paths["aoi"],
        )
        order.process_message = "Ejecutando dNBR / severidad / candidatos..."
        db.commit()
        self.update_state(
            state="PROGRESS",
            meta={"progress": 20, "message": order.process_message, "phase": "fire_dnbr"},
        )

        result = ProcessDnbrPipeline().execute(
            aoi_path=paths["aoi"],
            s2_root=s2_root,
            output_dir=results_root,
            output_prefix="Fire",
            municipality_field="MpNombre",
            department_field="Depto",
        )
        order.status = "procesado"
        order.process_message = (
            f"OK dNBR: candidatos={result.get('candidate_count')} "
            f"({result.get('elapsed_min')} min)"
        )
        order.process_manifest = result
        flag_modified(order, "process_manifest")
        db.commit()
        self.update_state(
            state="SUCCESS",
            meta={"progress": 100, "message": order.process_message, "phase": "completed"},
        )
        return result
    except Exception as exc:
        logger.exception("Fire dNBR process failed for order %s", order_id)
        try:
            order = db.query(FireOrder).filter(FireOrder.id == int(order_id)).first()
            if order:
                order.status = "error"
                order.process_message = str(exc)
                db.commit()
        except Exception:
            db.rollback()
        self.update_state(
            state="FAILURE",
            meta={"progress": 0, "message": str(exc), "phase": "failed"},
        )
        raise
    finally:
        db.close()


@celery_app.task(name="tasks.fire_validate_firms", bind=True)
def fire_validate_firms(
    self,
    order_id: int,
    db_url: str,
    fire_start: str,
    fire_end: str,
) -> dict:
    """Valida candidatos con FIRMS VIIRS (script 03) para una solicitud Fire."""
    from pathlib import Path

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.orm.attributes import flag_modified

    from app.core.config import settings
    from app.models.models import FireOrder
    from app.modules.fire.aoi_io import order_paths, write_order_aoi_gpkg
    from app.modules.fire.validate_firms import run_firms_pipeline

    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        order = db.query(FireOrder).filter(FireOrder.id == int(order_id)).first()
        if not order:
            raise RuntimeError(f"FireOrder {order_id} not found")

        map_key = (settings.firms_map_key or "").strip()
        if not map_key:
            import os

            map_key = (os.environ.get("FIRMS_MAP_KEY") or "").strip()
        if not map_key:
            raise RuntimeError(
                "FIRMS_MAP_KEY no configurada. Defina FIRMS_MAP_KEY en .env "
                "(https://firms.modaps.eosdis.nasa.gov/api/map_key/)."
            )

        self.update_state(
            state="PROGRESS",
            meta={"progress": 5, "message": "Preparando validación FIRMS...", "phase": "fire_firms"},
        )
        order.status = "validando"
        order.firms_message = "Preparando validación FIRMS..."
        db.commit()

        paths = order_paths(settings.storage_path, order.id)
        results_root = Path(order.results_root) if order.results_root else paths["results"]
        write_order_aoi_gpkg(
            geometry_geojson=order.geometry_geojson,
            request_name=order.request_name,
            department=order.department,
            output_path=paths["aoi"],
        )

        order.firms_message = f"Consultando FIRMS {fire_start} .. {fire_end}..."
        db.commit()
        self.update_state(
            state="PROGRESS",
            meta={"progress": 25, "message": order.firms_message, "phase": "fire_firms"},
        )

        result = run_firms_pipeline(
            aoi_path=paths["aoi"],
            results_dir=results_root,
            fire_start=fire_start,
            fire_end=fire_end,
            output_prefix="Fire",
            map_key=map_key,
        )
        order.status = "validado"
        order.firms_message = (
            f"OK FIRMS: HIGH={result.get('high_count')} "
            f"MEDIUM={result.get('medium_count')} LOW={result.get('low_count')} "
            f"recomendados={result.get('recommended_count')}"
        )
        order.firms_manifest = result
        flag_modified(order, "firms_manifest")
        db.commit()
        self.update_state(
            state="SUCCESS",
            meta={"progress": 100, "message": order.firms_message, "phase": "completed"},
        )
        return result
    except Exception as exc:
        logger.exception("Fire FIRMS validation failed for order %s", order_id)
        try:
            order = db.query(FireOrder).filter(FireOrder.id == int(order_id)).first()
            if order:
                order.status = "error"
                order.firms_message = str(exc)
                db.commit()
        except Exception:
            db.rollback()
        self.update_state(
            state="FAILURE",
            meta={"progress": 0, "message": str(exc), "phase": "failed"},
        )
        raise
    finally:
        db.close()
