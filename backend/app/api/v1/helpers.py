from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_max_upload_mb
from app.core.storage_paths import (  # noqa: F401
    EXTERNAL_SOURCE_PREFIX,
    S1_PREPROCESO_DIR_NAME,
    S1_PREPROCESO_DIR_NAME_LEGACY,
    _tenant_storage,
    encode_external_subpath,
    encode_source_subpath_for_path,
    ensure_external_sensor_download_dirs,
    external_data_root_path,
    is_external_source_subpath,
    project_downloads_dir,
    project_downloads_slug,
    project_relative_posix,
    project_root_path,
    project_s1_preproceso_dir,
    project_sentinel1_dir,
    project_sentinel2_dir,
    resolve_external_subpath,
    resolve_project_subpath,
    resolve_source_subpath,
)
from app.models.models import RasterLayer


async def validate_upload_size(file: UploadFile):
    file.file.seek(0, 2)
    size = file.file.tell()
    file.file.seek(0)
    max_mb = get_max_upload_mb()
    max_bytes = max_mb * 1024 * 1024
    if size > max_bytes:
        raise HTTPException(status_code=413, detail=f"File too large. Max {max_mb}MB")


def is_legacy_s2_zip_band_raster(meta: dict | None) -> bool:
    """
    True si es una capa raster del flujo antiguo Sentinel-2 (un JP2 por banda).
    Esas entradas no deben mostrarse en el mapa: solo las vistas RGB/NIR (composite_kind).
    """
    if not meta:
        return False
    return bool(
        meta.get("s2_band_pack")
        and meta.get("band")
        and not meta.get("composite_kind")
    )


def _get_project_raster(db: Session, tenant_id: int, project_id: int, raster_layer_id: int) -> RasterLayer:
    raster = (
        db.query(RasterLayer)
        .filter(
            RasterLayer.id == raster_layer_id,
            RasterLayer.project_id == project_id,
            RasterLayer.tenant_id == tenant_id,
        )
        .first()
    )
    if not raster:
        raise HTTPException(status_code=404, detail="Raster layer not found")
    return raster


def _existing_raster_path(raster: RasterLayer) -> Path:
    cog = Path(raster.cog_path) if raster.cog_path else None
    raw = Path(raster.file_path)
    if cog and cog.exists():
        return cog
    if raw.exists():
        return raw
    raise HTTPException(status_code=404, detail="Raster file not available")
