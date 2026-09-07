"""Celery Fire — solo dispatch a ``application.fire.pipeline_jobs`` (H4)."""

from app.tasks.celery_app import celery_app


@celery_app.task(name="tasks.fire_download_s2", bind=True)
def fire_download_s2(self, order_id: int, db_url: str) -> dict:
    """Descarga parcial S2 L2A para una solicitud Fire (metodología Tolima script 01)."""
    from app.application.fire.pipeline_jobs import RunFireDownloadS2Job

    return RunFireDownloadS2Job().execute(
        order_id=order_id,
        db_url=db_url,
        update_state=self.update_state,
    )


@celery_app.task(name="tasks.fire_process_dnbr", bind=True)
def fire_process_dnbr(self, order_id: int, db_url: str) -> dict:
    """Procesa dNBR/severidad (script 02) para una solicitud Fire."""
    from app.application.fire.pipeline_jobs import RunFireProcessDnbrJob

    return RunFireProcessDnbrJob().execute(
        order_id=order_id,
        db_url=db_url,
        update_state=self.update_state,
    )


@celery_app.task(name="tasks.fire_validate_firms", bind=True)
def fire_validate_firms(
    self,
    order_id: int,
    db_url: str,
    fire_start: str,
    fire_end: str,
) -> dict:
    """Valida candidatos con FIRMS VIIRS (script 03) para una solicitud Fire."""
    from app.application.fire.pipeline_jobs import RunFireValidateFirmsJob

    return RunFireValidateFirmsJob().execute(
        order_id=order_id,
        db_url=db_url,
        fire_start=fire_start,
        fire_end=fire_end,
        update_state=self.update_state,
    )
