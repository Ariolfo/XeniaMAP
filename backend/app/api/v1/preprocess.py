import json
import io
import logging
import math
import re
import tempfile
import uuid
from pathlib import Path

import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from shapely.geometry import Polygon
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_project_dashboard_access, tenant_from_jwt
from app.api.v1.helpers import (
    _safe_relative_under,
    _existing_raster_path,
    _get_project_raster,
    _tenant_storage,
    ensure_external_sensor_download_dirs,
    is_legacy_s2_zip_band_raster,
    project_s1_preproceso_dir,
    resolve_source_subpath,
    validate_upload_size,
)
from app.application.agro.landing_markdown import (
    EnqueueLandingMarkdown,
    ListLandingMarkdownFiles,
    ResolveLandingMarkdownPath,
)
from app.services.preprocess_pipeline_variant import (
    indices_dir_name,
    normalize_pipeline_variant,
)
from app.core.config import settings
from app.core.http_errors import celery_progress_info, log_celery_failure
from app.db.session import get_db
from app.models.models import Layer, Project, RasterLayer, User
from app.schemas.schemas import (
    ClusterRequest,
    CropRequest,
    DownloadRequest,
    IndicesRequest,
    RoiSelectionNormalized,
    S1GrdRecorteRequest,
    S1SarIndexStacksRequest,
    S1SarTimeSeriesRequest,
    PsPlanetZipExtractRequest,
    PsSpatiotemporalClusterRequest,
    S2IndexStacksRequest,
    S2L2aRecorteRequest,
    StackRequest,
    VegetationTimeSeriesRequest,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _pipeline_variant_query(pipeline_variant: str = Query("s2", description='s2 → recortes/indices; ps → recortesPS/indecesPS')) -> str:
    return normalize_pipeline_variant(pipeline_variant)


from app.application.agro import agroclimate as _agroclimate


def _norm_iso_date(raw: str) -> str:
    return _agroclimate.norm_iso_date(raw)


def _collect_dates_from_index_stacks(tenant_id: int, project_id: int, pipeline_variant: str) -> list[str]:
    """Fechas únicas YYYY-MM-DD desde BAND_DATES_JSON en stacks bajo indices/ o indecesPS/."""
    import rasterio

    root = _tenant_storage(tenant_id, project_id, indices_dir_name(pipeline_variant))
    if not root.is_dir():
        return []
    dates: set[str] = set()
    for p in root.rglob("*.tif"):
        if "_cog" in p.name.lower() or not p.is_file():
            continue
        rel = _safe_relative_under(root, p)
        if rel is None:
            continue
        parts = Path(rel).parts
        if len(parts) < 2:
            continue
        from app.application.agro.optical_inventory import canonical_index_dir_name

        if canonical_index_dir_name(parts[0]) is None:
            continue
        try:
            with rasterio.open(p) as src:
                tags = src.tags()
        except Exception:
            continue
        jd = tags.get("BAND_DATES_JSON")
        if not isinstance(jd, str) or not jd.strip():
            continue
        try:
            arr = json.loads(jd)
        except json.JSONDecodeError:
            continue
        if not isinstance(arr, list):
            continue
        for d in arr:
            nd = _norm_iso_date(str(d))
            if re.match(r"^\d{4}-\d{2}-\d{2}$", nd):
                dates.add(nd)
    return sorted(dates)


def _collect_dates_from_s1_sar_stacks(tenant_id: int, project_id: int) -> list[str]:
    """Fechas únicas YYYY-MM-DD desde BAND_DATES_JSON en stacks SAR bajo s1indices/."""
    import rasterio

    from app.services.s1_sar_indices import S1_SAR_STACKS_ROOT_NAME

    root = _tenant_storage(tenant_id, project_id, S1_SAR_STACKS_ROOT_NAME)
    if not root.is_dir():
        return []
    dates: set[str] = set()
    for p in root.rglob("*.tif"):
        if "_cog" in p.name.lower() or not p.is_file():
            continue
        rel = _safe_relative_under(root, p)
        if rel is None:
            continue
        parts = Path(rel).parts
        if len(parts) < 2:
            continue
        if _canonical_s1_sar_index_dir_name(parts[0]) is None:
            continue
        try:
            with rasterio.open(p) as src:
                tags = src.tags()
        except Exception:
            continue
        jd = tags.get("BAND_DATES_JSON")
        if not isinstance(jd, str) or not jd.strip():
            continue
        try:
            arr = json.loads(jd)
        except json.JSONDecodeError:
            continue
        if not isinstance(arr, list):
            continue
        for d in arr:
            nd = _norm_iso_date(str(d))
            if re.match(r"^\d{4}-\d{2}-\d{2}$", nd):
                dates.add(nd)
    return sorted(dates)


def _open_meteo_daily(lat: float, lon: float, start_date: str, end_date: str) -> list[dict]:
    """Serie diaria (Open-Meteo archive); lógica en application/agro/agroclimate."""
    try:
        return _agroclimate.fetch_open_meteo_daily(lat, lon, start_date, end_date)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _monthly_means_from_daily(rows: list[dict]) -> dict[str, dict]:
    return _agroclimate.monthly_means_from_daily(rows)


def _series_from_scene_dates(scene_dates: list[str], monthly_means: dict[str, dict]) -> list[dict]:
    return _agroclimate.series_from_scene_dates(scene_dates, monthly_means)


@router.post("/preprocess/download")
def preprocess_download(
    payload: DownloadRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    from app.application.agro.download import StartSentinel2ProjectDownload, WriteStubProjectDownload

    require_project_dashboard_access(db, user, tenant_id, payload.project_id)

    if payload.source == "sentinel-2":
        from app.services.project_geometry import wkt_union_from_project_layers

        wkt = wkt_union_from_project_layers(db, payload.project_id, tenant_id, payload.layer_id)
        try:
            from app.application.agro.repos import raster_layers_repo

            return StartSentinel2ProjectDownload().execute(
                raster_layers=raster_layers_repo(db),
                tenant_id=tenant_id,
                project_id=payload.project_id,
                start_date=payload.start_date,
                end_date=payload.end_date,
                download_subpath=payload.download_subpath,
                wkt=wkt,
                copernicus_configured=bool(settings.copernicus_user and settings.copernicus_password),
                database_url=settings.database_url,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            detail = str(exc)
            code = 500 if "credentials" in detail.lower() else 503
            raise HTTPException(status_code=code, detail=detail) from exc

    from app.application.agro.repos import raster_layers_repo

    return WriteStubProjectDownload().execute(
        raster_layers=raster_layers_repo(db),
        tenant_id=tenant_id,
        project_id=payload.project_id,
        source=payload.source,
    )


@router.post("/preprocess/sentinel1-download")
async def preprocess_sentinel1_download(
    project_id: int = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    layer_id: str | None = Form(None),
    aoi_file: UploadFile | None = File(None),
    images_per_month: int = Form(0),
    download_subpath: str | None = Form(
        None,
        description="Destino disco externo (ext:…). Obligatoria. Crea Sentinel1/ si no existe.",
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    """
    Descarga Sentinel-1 GRD IW (VV+VH) desde Copernicus (STAC + OData).
    AOI: capa vectorial del proyecto (layer_id) o archivo GeoJSON / ZIP shapefile (aoi_file).
    Destino: carpeta en el disco externo (``download_subpath``); archivos en ``Sentinel1/``.
    """
    from app.application.agro.download import StartSentinel1ProjectDownload, parse_sentinel1_layer_id

    require_project_dashboard_access(db, user, tenant_id, project_id)

    try:
        lid = parse_sentinel1_layer_id(layer_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    has_aoi_upload = bool(aoi_file and getattr(aoi_file, "filename", None))
    if not has_aoi_upload and lid is None:
        raise HTTPException(
            status_code=400,
            detail="Indica una capa vectorial (paso 1) o sube un AOI (GeoJSON o ZIP shapefile).",
        )

    wkt: str | None = None
    if has_aoi_upload:
        await validate_upload_size(aoi_file)
        ext = Path(aoi_file.filename).suffix.lower()
        allowed = {".geojson", ".json", ".zip"}
        if ext not in allowed:
            raise HTTPException(status_code=400, detail="AOI: use .geojson, .json o .zip (shapefile)")

        raw = await aoi_file.read()
        with tempfile.NamedTemporaryFile(suffix=ext, prefix="aoi_s1_", delete=False) as tf:
            tf.write(raw)
            tmp_path = Path(tf.name)
        try:
            from app.services.aoi_vector import geometry_wkt_from_vector_path

            wkt, _meta = geometry_wkt_from_vector_path(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

    if wkt is None and lid is not None:
        from app.services.project_geometry import wkt_union_from_project_layers

        wkt = wkt_union_from_project_layers(db, project_id, tenant_id, lid)
        if not wkt:
            raise HTTPException(status_code=400, detail="No se pudo obtener geometría desde la capa vectorial.")

    try:
        from app.application.agro.repos import raster_layers_repo

        return StartSentinel1ProjectDownload().execute(
            raster_layers=raster_layers_repo(db),
            tenant_id=tenant_id,
            project_id=project_id,
            start_date=start_date,
            end_date=end_date,
            download_subpath=download_subpath,
            wkt=wkt,
            layer_id=lid,
            images_per_month=images_per_month,
            copernicus_configured=bool(settings.copernicus_user and settings.copernicus_password),
            database_url=settings.database_url,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        detail = str(exc)
        code = 500 if "credentials" in detail.lower() else 503
        raise HTTPException(status_code=code, detail=detail) from exc


@router.get("/preprocess/sentinel-status/{project_id}/{raster_id}")
def sentinel_download_status(
    project_id: int,
    raster_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    """Poll Sentinel-2 download progress (Celery + DB metadata)."""
    from app.application.agro.download import GetSentinelDownloadStatus

    require_project_dashboard_access(db, user, tenant_id, project_id)
    try:
        from app.application.agro.repos import raster_layers_repo

        return GetSentinelDownloadStatus().execute(
            raster_layers=raster_layers_repo(db),
            tenant_id=tenant_id,
            project_id=project_id,
            raster_id=raster_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/preprocess/crop")
def preprocess_crop(
    payload: CropRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    from app.application.agro.crop_recortes import CropRasterCenter, crop_output_path

    require_project_dashboard_access(db, user, tenant_id, payload.project_id)
    raster = _get_project_raster(db, tenant_id, payload.project_id, payload.raster_layer_id)
    src_path = _existing_raster_path(raster)
    out_path = crop_output_path(tenant_id, payload.project_id)
    output = CropRasterCenter().execute(
        src_path=src_path,
        out_path=out_path,
        crop_ratio=payload.crop_ratio,
    )
    return {"status": "ok", "output_path": output}


# Fecha de adquisición en nombres GRD IW: ...S1A_IW_GRDH_1SDV_20250111T102623...
# ENVI/SNAP sigma0 en dB bajo s1preproceso/ (legacy: s1prepoceso)
# Constantes / helpers → application/agro/s1_inventory.py


@router.get("/preprocess/s1-preproceso-sigma0-vv-inventory/{project_id}")
@router.get("/preprocess/s1-prepoceso-sigma0-vv-inventory/{project_id}")  # legacy typo
def get_s1_preproceso_sigma0_vv_inventory(
    project_id: int,
    pol: str = Query(
        "vv",
        description="Polarización: vv → Sigma0_VV_db.img, vh → Sigma0_VH_db.img",
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    """
    Lista ``Sigma0_VV_db.img`` o ``Sigma0_VH_db.img`` bajo ``s1preproceso/`` (SNAP/ENVI).
    ``sort_key`` en formato ISO (YYYY-MM-DD) extraído de ``..._S1?_IW_GRDH_1SDV_YYYYMMDDTh...`` en la ruta.
    """
    from app.application.agro.s1_inventory import ListS1PrepSigma0Inventory

    require_project_dashboard_access(db, user, tenant_id, project_id)
    try:
        return ListS1PrepSigma0Inventory().execute(
            tenant_id=tenant_id, project_id=project_id, pol=pol
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/preprocess/s1-preproceso-sigma0-vv-preview/{project_id}")
@router.get("/preprocess/s1-prepoceso-sigma0-vv-preview/{project_id}")  # legacy typo
def get_s1_preproceso_sigma0_vv_preview(
    project_id: int,
    img_relpath: str | None = Query(
        None,
        alias="path",
        description="Ruta relativa dentro de s1preproceso/ hasta Sigma0_VV_db.img o Sigma0_VH_db.img",
    ),
    pol: str = Query(
        "vv",
        description="Debe coincidir con el archivo: vv → Sigma0_VV_db.img, vh → Sigma0_VH_db.img",
    ),
    palette: str = Query(
        "spectral",
        description="Paleta tipo JET/Spectral (matplotlib): spectral | jet | turbo",
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    """PNG de una banda (sigma0 VV o VH en dB) desde ENVI en ``s1preproceso/`` (paleta científica)."""
    from app.application.agro.s1_inventory import PreviewS1PrepSigma0Png

    require_project_dashboard_access(db, user, tenant_id, project_id)
    try:
        png = PreviewS1PrepSigma0Png().execute(
            tenant_id=tenant_id,
            project_id=project_id,
            img_relpath=img_relpath,
            pol=pol,
            palette=palette,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        content=png,
        media_type="image/png",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@router.get("/preprocess/s1-preproceso-sar-scenes-inventory/{project_id}")
@router.get("/preprocess/s1-prepoceso-sar-scenes-inventory/{project_id}")  # legacy typo
def get_s1_prep_sar_scenes_inventory(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    """
    Escenas con par ``Sigma0_VV_db.img`` + ``Sigma0_VH_db.img`` en ``s1preproceso/`` (misma carpeta ``.data``).
    Orden cronológico por fecha GRD en la ruta.
    """
    from app.application.agro.s1_inventory import ListS1PrepSarScenes

    require_project_dashboard_access(db, user, tenant_id, project_id)
    return ListS1PrepSarScenes().execute(tenant_id=tenant_id, project_id=project_id)


@router.post("/preprocess/s1-sar-index-stacks")
def preprocess_s1_sar_index_stacks(
    payload: S1SarIndexStacksRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    """
    Encola generación de stacks multibanda (una banda por escena, orden cronológico) por cada índice SAR.
    Salida **solo** en ``s1indices/<INDICE>/`` del proyecto (no usa ``indices/`` de Sentinel-2).
    """
    from app.application.agro.s1_inventory import EnqueueS1SarIndexStacks

    require_project_dashboard_access(db, user, tenant_id, payload.project_id)
    try:
        return EnqueueS1SarIndexStacks().execute(
            tenant_id=tenant_id,
            project_id=payload.project_id,
            indices=payload.indices,
            scene_vv_relpaths=payload.scene_vv_relpaths,
            database_url=settings.database_url,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/preprocess/recortes-inventory/{project_id}")
def get_recortes_inventory(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
    pipeline_variant: str = Depends(_pipeline_variant_query),
):
    """
    Lista GeoTIFF bajo ``recortes/`` o ``recortesPS/`` (incl. subcarpetas) con ≥6 bandas, sin depender de capas en BD.
    ``relative_path`` identifica el archivo para preview y tareas; ``basename`` es solo el nombre final.
    ``raster_layer_id`` si una capa apunta al mismo path resuelto, al mismo basename, o a ``metadata.source_name`` con ese basename (p. ej. TIF en ``rasters/`` copiado desde ``recortesPS/``).
    """
    from app.application.agro.recortes_inventory import ListRecortesInventory

    require_project_dashboard_access(db, user, tenant_id, project_id)
    from app.application.agro.repos import raster_layers_repo

    return ListRecortesInventory().execute(
        raster_layers_repo(db),
        tenant_id=tenant_id,
        project_id=project_id,
        pipeline_variant=pipeline_variant,
    )


@router.get("/preprocess/recortes-preview/{project_id}")
def get_recorte_preview_disk(
    project_id: int,
    recorte_relpath: str | None = Query(
        None,
        alias="path",
        description="Ruta relativa dentro de recortes/ (p. ej. sub/escena.tif). Preferido frente a name.",
    ),
    name: str | None = Query(
        None,
        min_length=1,
        description="Solo basename en la raíz de recortes/ (compatibilidad). Usar query path si hay subcarpetas.",
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
    pipeline_variant: str = Depends(_pipeline_variant_query),
):
    """Vista RGB desde GeoTIFF en ``recortes/`` o ``recortesPS/``: S2 típico B04,B03,B02 → 3,2,1; Planet PS (≥6 bandas) → 6,4,2."""
    from app.application.agro.recortes_inventory import PreviewRecortePng

    require_project_dashboard_access(db, user, tenant_id, project_id)
    try:
        from app.application.agro.repos import raster_layers_repo

        png = PreviewRecortePng().execute(
            raster_layers_repo(db),
            tenant_id=tenant_id,
            project_id=project_id,
            recorte_relpath=recorte_relpath,
            name=name,
            pipeline_variant=pipeline_variant,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        content=png,
        media_type="image/png",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


def _canonical_s1_sar_index_dir_name(raw: str) -> str | None:
    from app.application.agro.s1_inventory import canonical_s1_sar_index_dir_name

    return canonical_s1_sar_index_dir_name(raw)


@router.get("/preprocess/index-stacks-inventory/{project_id}")
def get_index_stacks_inventory(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
    pipeline_variant: str = Depends(_pipeline_variant_query),
):
    """Lista GeoTIFF multibanda en ``indices/`` o ``indecesPS/`` (salida del pipeline de estimación, sin capas en BD)."""
    from app.application.agro.optical_inventory import ListIndexStacksInventory

    require_project_dashboard_access(db, user, tenant_id, project_id)
    return ListIndexStacksInventory().execute(
        tenant_id=tenant_id,
        project_id=project_id,
        pipeline_variant=pipeline_variant,
    )


@router.get("/preprocess/index-stacks-preview/{project_id}")
def get_index_stack_preview_disk(
    project_id: int,
    stack_relpath: str | None = Query(
        None,
        alias="path",
        description="Ruta relativa bajo indices/ (p. ej. NDVI/NDVI_20240101_20241231.tif)",
    ),
    band: int | None = Query(
        None,
        ge=1,
        description="Banda (fecha) 1..N.",
    ),
    index_palette: int = Query(
        0,
        ge=0,
        le=1,
        description="1 = paleta RdYlGn (galería «Visual índices»).",
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
    pipeline_variant: str = Depends(_pipeline_variant_query),
):
    """PNG de una banda de un stack de índices en disco (no requiere RasterLayer)."""
    from app.application.agro.optical_inventory import PreviewIndexStackPng

    require_project_dashboard_access(db, user, tenant_id, project_id)
    try:
        png = PreviewIndexStackPng().execute(
            tenant_id=tenant_id,
            project_id=project_id,
            stack_relpath=stack_relpath,
            band=band,
            index_palette=index_palette,
            pipeline_variant=pipeline_variant,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        content=png,
        media_type="image/png",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@router.get("/preprocess/s1-sar-index-stacks-inventory/{project_id}")
def get_s1_sar_index_stacks_inventory(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    """Lista GeoTIFF multibanda en ``s1indices/<INDICE>/`` (stacks SAR por escena)."""
    from app.application.agro.s1_inventory import ListS1SarIndexStacksInventory

    require_project_dashboard_access(db, user, tenant_id, project_id)
    return ListS1SarIndexStacksInventory().execute(tenant_id=tenant_id, project_id=project_id)


@router.get("/preprocess/s1-sar-index-stacks-preview/{project_id}")
def get_s1_sar_index_stack_preview_disk(
    project_id: int,
    stack_relpath: str | None = Query(
        None,
        alias="path",
        description="Ruta relativa bajo s1indices/ (p. ej. RVI/RVI_20250111_20251225.tif)",
    ),
    band: int | None = Query(
        None,
        ge=1,
        description="Banda (fecha) 1..N.",
    ),
    index_palette: int = Query(
        0,
        ge=0,
        le=1,
        description="1 = paleta RdYlGn (galería «Visual índices SAR»).",
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    """PNG de una banda de un stack de índices SAR en ``s1indices/``."""
    from app.application.agro.s1_inventory import PreviewS1SarIndexStackPng

    require_project_dashboard_access(db, user, tenant_id, project_id)
    try:
        png = PreviewS1SarIndexStackPng().execute(
            tenant_id=tenant_id,
            project_id=project_id,
            stack_relpath=stack_relpath,
            band=band,
            index_palette=index_palette,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        content=png,
        media_type="image/png",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@router.post("/preprocess/s2-index-stacks")
def preprocess_s2_index_stacks(
    payload: S2IndexStacksRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    """
    Genera stacks multibanda (una banda por escena/fecha) por índice en ``indices/<INDICE>/`` o ``indecesPS/``.
    Requiere GeoTIFF de recorte L2A de 6 bandas en ``recortes/`` o ``recortesPS/``.
    """
    from app.application.agro.indices import EnqueueS2IndexStacks

    require_project_dashboard_access(db, user, tenant_id, payload.project_id)
    try:
        return EnqueueS2IndexStacks().execute(
            tenant_id=tenant_id,
            project_id=payload.project_id,
            indices=payload.indices,
            database_url=settings.database_url,
            raster_layer_ids=payload.raster_layer_ids,
            recorte_filenames=payload.recorte_filenames,
            pipeline_variant=payload.pipeline_variant,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/preprocess/vegetation-time-series")
def preprocess_vegetation_time_series(
    payload: VegetationTimeSeriesRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    """
    Series desde stacks ya estimados en ``indices/`` (S2) o ``indecesPS/`` (PS).
    No selecciona escenas: cada stack (una banda por fecha) alimenta medias y series por píxel.
    """
    from app.application.agro.time_series import BuildVegetationTimeSeries

    require_project_dashboard_access(db, user, tenant_id, payload.project_id)
    try:
        return BuildVegetationTimeSeries().execute(
            tenant_id=tenant_id,
            project_id=payload.project_id,
            pipeline_variant=payload.pipeline_variant,
            dates=payload.dates,
            max_pixel_series=payload.max_pixel_series,
            random_seed=payload.random_seed,
            roi_selection=payload.roi_selection,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/preprocess/s1-sar-time-series")
def preprocess_s1_sar_time_series(
    payload: S1SarTimeSeriesRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    """
    Medias espaciales y series por píxel (muestreadas) desde los stacks en ``s1indices/``,
    misma forma de respuesta que ``/preprocess/vegetation-time-series`` (campo adicional ``source``).
    """
    from app.application.agro.time_series import BuildS1SarTimeSeries

    require_project_dashboard_access(db, user, tenant_id, payload.project_id)
    try:
        return BuildS1SarTimeSeries().execute(
            tenant_id=tenant_id,
            project_id=payload.project_id,
            dates=payload.dates,
            max_pixel_series=payload.max_pixel_series,
            random_seed=payload.random_seed,
            roi_selection=payload.roi_selection,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/preprocess/agroclimate-series")
def preprocess_agroclimate_series(
    project_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    """
    Serie agroclimática por sensor para el dashboard multisensor.
    - Centroide: geometría unión del proyecto (WGS84).
    - Rango: min/max de fechas disponibles entre stacks S1/S2/PS.
    - Valor por escena: promedio mensual del mes al que pertenece cada fecha del timelapse.
    """
    from app.application.agro.time_series import BuildAgroclimateSeries
    from app.services.project_geometry import wkt_union_from_project_layers

    require_project_dashboard_access(db, user, tenant_id, project_id)
    wkt = wkt_union_from_project_layers(db, project_id, tenant_id, None)
    try:
        return BuildAgroclimateSeries().execute(
            project_id=project_id,
            wkt=wkt,
            s1_dates=_collect_dates_from_s1_sar_stacks(tenant_id, project_id),
            s2_dates=_collect_dates_from_index_stacks(tenant_id, project_id, "s2"),
            ps_dates=_collect_dates_from_index_stacks(tenant_id, project_id, "ps"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/preprocess/indices")
def preprocess_indices(
    payload: IndicesRequest,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(tenant_from_jwt),
):
    from app.application.agro.indices import ComputeSimpleVegetationIndex, simple_index_output_path

    raster = _get_project_raster(db, tenant_id, payload.project_id, payload.raster_layer_id)
    src_path = _existing_raster_path(raster)
    out_path = simple_index_output_path(tenant_id, payload.project_id, payload.index_type)
    try:
        index_type = ComputeSimpleVegetationIndex().execute(
            src_path=src_path,
            out_path=out_path,
            index_type=payload.index_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "index_type": index_type}


@router.post("/preprocess/stack")
def preprocess_stack(payload: StackRequest, db: Session = Depends(get_db), tenant_id: int = Depends(tenant_from_jwt)):
    rasters = (
        db.query(RasterLayer)
        .filter(RasterLayer.project_id == payload.project_id, RasterLayer.tenant_id == tenant_id)
        .order_by(RasterLayer.id.desc())
        .all()
    )
    rasters = [r for r in rasters if not is_legacy_s2_zip_band_raster(r.raster_metadata)]
    if not rasters:
        raise HTTPException(status_code=404, detail="No rasters available")
    if payload.mode.lower() == "visualizar":
        return {
            "status": "ok",
            "mode": "visualizar",
            "rasters": [{"id": r.id, "name": r.name} for r in rasters[:10]],
        }
    if payload.mode.lower() == "gif":
        out_path = _tenant_storage(tenant_id, payload.project_id, "preprocess") / f"stack_gif_manifest_{uuid.uuid4().hex}.json"
        out_path.write_text(
            json.dumps([{"id": r.id, "name": r.name} for r in rasters[:12]], indent=2),
            encoding="utf-8",
        )
        return {"status": "ok", "mode": "gif"}
    raise HTTPException(status_code=400, detail="Unsupported stack mode")


@router.post("/preprocess/cluster")
def preprocess_cluster(
    payload: ClusterRequest,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(tenant_from_jwt),
):
    raster = _get_project_raster(db, tenant_id, payload.project_id, payload.raster_layer_id)
    src_path = _existing_raster_path(raster)
    out_path = _tenant_storage(tenant_id, payload.project_id, "preprocess") / f"cluster_{uuid.uuid4().hex}.tif"

    import rasterio

    k = max(2, min(10, payload.clusters))
    with rasterio.open(src_path) as src:
        band = src.read(1).astype("float32")
        bins = np.quantile(band, np.linspace(0, 1, k + 1))
        classified = np.digitize(band, bins[1:-1]).astype("uint8")
        profile = src.profile.copy()
        profile.update(dtype="uint8", count=1)
        with rasterio.open(out_path, "w", **profile) as dst:
            dst.write(classified, 1)
    return {"status": "ok", "clusters": k}


@router.post("/preprocess/sentinel1-recortes")
def preprocess_sentinel1_recortes(
    payload: S1GrdRecorteRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    """
    Por cada producto Sentinel-1 (.SAFE o .zip bajo ``Sentinel1/``): apila VV+VH, recorta al polígono
    (subset espacial equivalente a SNAP Raster/Subset/Polygon) y guarda GeoTIFF en ``recortes/S1/``.
    """
    from app.application.agro.crop_recortes import EnqueueS1GrdRecortes

    project = require_project_dashboard_access(db, user, tenant_id, payload.project_id)
    try:
        from app.application.agro.repos import layers_repo

        return EnqueueS1GrdRecortes().execute(
            layers=layers_repo(db),
            tenant_id=tenant_id,
            project_id=payload.project_id,
            project_name=project.name,
            layer_id=payload.layer_id,
            product_paths=payload.product_paths,
            source_subpath=payload.source_subpath,
            database_url=settings.database_url,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/preprocess/ps-planetscope-zip-extract")
def preprocess_ps_planetscope_zip_extract(
    payload: PsPlanetZipExtractRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    """
    Por cada ``*.zip`` en ``rasterPS/`` del proyecto: extrae ``composite.tif`` y metadatos (XML, JSON,
    ``composite_udm2.tif``) a ``rasterPS/`` como ``PS_dd-mm-yy.tif`` (originales para el recorte).
    """
    from app.application.agro.ps_planet import EnqueuePsPlanetZipExtract

    require_project_dashboard_access(db, user, tenant_id, payload.project_id)
    try:
        return EnqueuePsPlanetZipExtract().execute(
            tenant_id=tenant_id,
            project_id=payload.project_id,
            source_subpath=payload.source_subpath,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/preprocess/ps-tif-inventory/{project_id}")
def get_ps_tif_inventory(
    project_id: int,
    source: str = Query(
        "rasterPS",
        description="Carpeta origen del recorte: ``rasterPS`` (originales, por defecto) o ``recortesPS``.",
    ),
    source_subpath: str | None = Query(
        None,
        description="Si se envía, lista TIF en esa ruta (proyecto o ``ext:``). Si se omite, según ``source``.",
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    """Lista GeoTIFF a recortar en ``recortesPS/`` o ``rasterPS/`` (flujo PlanetScope)."""
    from app.application.agro.ps_planet import ListPsTifInventory

    require_project_dashboard_access(db, user, tenant_id, project_id)
    try:
        return ListPsTifInventory().execute(
            tenant_id=tenant_id,
            project_id=project_id,
            source=source,
            source_subpath=source_subpath,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/preprocess/ps-recorte-clip")
async def preprocess_ps_recorte_clip(
    project_id: int = Form(...),
    layer_id: str | None = Form(None),
    aoi_file: UploadFile | None = File(None),
    source: str = Form("rasterPS"),
    filenames_json: str | None = Form(
        None,
        description='JSON array de basenames a procesar, p. ej. ``["PS_23-03-26.tif"]``. Omitir = todos.',
    ),
    source_subpath: str | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    """
    Recorta GeoTIFF PlanetScope al polígono del proyecto (capa / unión) o a un AOI subido
    (GeoJSON / ZIP shapefile).

    Origen por defecto: ``rasterPS/`` (originales). Salida: ``recortesPS/`` (insumos de RGB e índices).
    """
    from app.application.agro.download import parse_optional_layer_id
    from app.application.agro.ps_planet import EnqueuePsRecorteClip, parse_filenames_json

    require_project_dashboard_access(db, user, tenant_id, project_id)

    try:
        lid = parse_optional_layer_id(layer_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    has_aoi_upload = bool(aoi_file and getattr(aoi_file, "filename", None))
    wkt: str | None = None
    if has_aoi_upload:
        await validate_upload_size(aoi_file)
        ext = Path(aoi_file.filename).suffix.lower()
        allowed = {".geojson", ".json", ".zip"}
        if ext not in allowed:
            raise HTTPException(status_code=400, detail="AOI: use .geojson, .json o .zip (shapefile)")
        raw = await aoi_file.read()
        with tempfile.NamedTemporaryFile(suffix=ext, prefix="aoi_ps_", delete=False) as tf:
            tf.write(raw)
            tmp_path = Path(tf.name)
        try:
            from app.services.aoi_vector import geometry_wkt_from_vector_path

            wkt, _meta = geometry_wkt_from_vector_path(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)
    else:
        from app.services.project_geometry import wkt_union_from_project_layers

        wkt = wkt_union_from_project_layers(db, project_id, tenant_id, lid)

    try:
        filenames = parse_filenames_json(filenames_json)
        from app.application.agro.repos import layers_repo

        return EnqueuePsRecorteClip().execute(
            layers=layers_repo(db),
            tenant_id=tenant_id,
            project_id=project_id,
            wkt=wkt,
            source=source,
            filenames=filenames,
            source_subpath=source_subpath,
            layer_id=lid,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/preprocess/s2-l2a-recortes")
def preprocess_s2_l2a_recortes(
    payload: S2L2aRecorteRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    """
    Por cada producto L2A (.zip o carpeta .SAFE) en la carpeta de descargas del proyecto:
    apila 6 bandas (B02,B03,B04,B08; B05 y B11 remuestreadas a la grilla 10 m de B02), recorta al
    polígono del lote, guarda en `recortes/` (GeoTIFF con nombre del producto) y registra la capa (vista RGB R=B04,G=B03,B=B02).
    """
    from app.application.agro.crop_recortes import EnqueueS2L2aRecortes
    from app.services.project_geometry import wkt_union_from_project_layers

    project = require_project_dashboard_access(db, user, tenant_id, payload.project_id)
    wkt = wkt_union_from_project_layers(db, payload.project_id, tenant_id, payload.layer_id)
    try:
        from app.application.agro.repos import layers_repo

        return EnqueueS2L2aRecortes().execute(
            layers=layers_repo(db),
            tenant_id=tenant_id,
            project_id=payload.project_id,
            project_name=project.name,
            layer_id=payload.layer_id,
            wkt=wkt,
            product_names=payload.product_names,
            source_subpath=payload.source_subpath,
            pipeline_variant=payload.pipeline_variant,
            database_url=settings.database_url,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/preprocess/landing-markdown-generate/{project_id}")
def landing_markdown_generate(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    """Encola la generación de los 3 Markdown de la landing (PS, S1, S2), cada uno ≤ 4.9 MB."""
    require_project_dashboard_access(db, user, tenant_id, project_id)
    try:
        return EnqueueLandingMarkdown().execute(tenant_id=tenant_id, project_id=project_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/preprocess/landing-markdown-files/{project_id}")
def landing_markdown_files(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    """Lista los Markdown generados en ``markdown/`` con tamaño y fecha."""
    require_project_dashboard_access(db, user, tenant_id, project_id)
    return ListLandingMarkdownFiles().execute(tenant_id=tenant_id, project_id=project_id)


@router.get("/preprocess/landing-markdown-download/{project_id}")
def landing_markdown_download(
    project_id: int,
    sensor: str = Query(..., description="PS, S1 o S2"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    """Descarga uno de los Markdown generados."""
    require_project_dashboard_access(db, user, tenant_id, project_id)
    try:
        p = ResolveLandingMarkdownPath().execute(
            tenant_id=tenant_id, project_id=project_id, sensor=sensor
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(p, media_type="text/markdown", filename=p.name)


@router.get("/preprocess/task-status/{task_id}")
def preprocess_task_status(
    task_id: str,
    _user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    """Estado de una tarea Celery. Solo visible para el tenant que la encoló."""
    from celery.result import AsyncResult

    from app.core.celery_task_registry import get_celery_task_owner
    from app.tasks.celery_app import celery_app

    owner = get_celery_task_owner(task_id)
    if not owner or int(owner["tenant_id"]) != int(tenant_id):
        raise HTTPException(status_code=404, detail="Tarea no encontrada")

    ar = AsyncResult(task_id, app=celery_app)
    if ar.state == "PENDING":
        return {"state": ar.state, "ready": False}
    if ar.state == "SUCCESS":
        return {"state": ar.state, "ready": True, "result": ar.result}
    if ar.state == "FAILURE":
        return {
            "state": ar.state,
            "ready": True,
            "error": log_celery_failure(task_id=task_id, result=ar.result),
        }
    out: dict = {"state": ar.state, "ready": bool(ar.ready())}
    progress = celery_progress_info(ar.info)
    if progress:
        out["info"] = progress
    return out


@router.post("/preprocess/ps-spatiotemporal-cluster/{project_id}")
def ps_spatiotemporal_cluster_run(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
    preset: str = Query(
        "smart1",
        description=(
            "smart1 → ps_st_cluster/; smart2 → ps_st_cluster_smart2/; smart3 → ps_st_cluster_smart3/ "
            "(ver documentación del preset)."
        ),
    ),
    body: PsSpatiotemporalClusterRequest | None = None,
):
    """
    Pipeline resumido: cuatro stacks en ``indecesPS/`` → 7 features por píxel → KMeans.
    ``preset=smart1``: NDVI (mean/std/min), NDRE_mean, NDWI_mean/std, VARI_mean.
    ``preset=smart2``: EVI (mean/std/min), NDRE_mean, NDWI_mean/std, VARI_mean.
    ``preset=smart3``: KNDVI (mean/std/min), MCARI_mean, NDWI_mean/std, VARI_mean.
    """
    from app.application.agro.ps_planet import RunPsSpatiotemporalCluster

    require_project_dashboard_access(db, user, tenant_id, project_id)
    opts = body or PsSpatiotemporalClusterRequest()
    try:
        return RunPsSpatiotemporalCluster().execute(
            tenant_id=tenant_id,
            project_id=project_id,
            preset=preset,
            n_clusters=opts.n_clusters,
            random_state=opts.random_state,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/preprocess/ps-spatiotemporal-cluster-status/{project_id}")
def ps_spatiotemporal_cluster_status(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
    preset: str = Query("smart1", description="smart1, smart2 o smart3"),
):
    from app.application.agro.ps_planet import GetPsSpatiotemporalClusterStatus

    require_project_dashboard_access(db, user, tenant_id, project_id)
    try:
        return GetPsSpatiotemporalClusterStatus().execute(
            tenant_id=tenant_id,
            project_id=project_id,
            preset=preset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/preprocess/ps-spatiotemporal-cluster-preview/{project_id}")
def ps_spatiotemporal_cluster_preview(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
    preset: str = Query("smart1", description="smart1, smart2 o smart3"),
):
    """PNG del mapa de clusters (colores discretos)."""
    from app.application.agro.ps_planet import GetPsSpatiotemporalClusterPreviewPng

    require_project_dashboard_access(db, user, tenant_id, project_id)
    try:
        png = GetPsSpatiotemporalClusterPreviewPng().execute(
            tenant_id=tenant_id,
            project_id=project_id,
            preset=preset,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        content=png,
        media_type="image/png",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )
