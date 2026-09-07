"""Composition root H3 — defaults de adapters (inyección opcional en UC)."""

from __future__ import annotations

from app.infrastructure.jobs.celery_job_queue import CeleryJobQueue
from app.infrastructure.mail.smtp_mail_adapter import SmtpMailAdapter
from app.infrastructure.raster.tile_render_adapter import CompositeTileRenderAdapter
from app.infrastructure.storage.raster_storage_adapter import DiskRasterStorage


def default_job_queue() -> CeleryJobQueue:
    return CeleryJobQueue()


def default_raster_storage() -> DiskRasterStorage:
    return DiskRasterStorage()


def default_mail() -> SmtpMailAdapter:
    return SmtpMailAdapter()


def default_tile_render() -> CompositeTileRenderAdapter:
    return CompositeTileRenderAdapter()
