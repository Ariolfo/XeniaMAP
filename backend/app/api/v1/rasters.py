"""Rutas mapa / mutación raster de proyecto (list, preview, upload, delete, purge)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin, require_project_dashboard_access, tenant_from_jwt
from app.api.v1.helpers import (
    _existing_raster_path,
    _get_project_raster,
    is_legacy_s2_zip_band_raster,
    validate_upload_size,
)
from app.db.session import get_db
from app.models.models import RasterLayer, User
from app.schemas.schemas import PurgeS2L2aRecortesBody
from app.services.raster_geo import (
    render_raster_preview_png,
    render_s1_vh_vv_ratio_preview_png,
)
from app.services.preprocess_pipeline_variant import is_planetscope_ps_recorte_filename
from app.application.agro.rasters import (
    delete_raster_layer_row,
    upload_raster as upload_raster_uc,
    _normalize_s2_sort_keys,
    _raster_chronological_sort_key,
    _scene_iso_yyyy_mm_dd_for_purge,
    _s2_rgb_gallery_raster_meta,
)

router = APIRouter()


@router.post("/upload-raster")
async def upload_raster(
    project_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(tenant_from_jwt),
    _admin: User = Depends(require_admin),
):
    await validate_upload_size(file)
    try:
        return upload_raster_uc(
            db,
            tenant_id=tenant_id,
            project_id=project_id,
            filename=file.filename,
            file_obj=file.file,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/raster/{project_id}/{raster_layer_id}/preview")
def get_raster_preview(
    project_id: int,
    raster_layer_id: int,
    band: int | None = Query(
        None,
        ge=1,
        description="Stacks de índices multibanda: banda (1..N) a visualizar.",
    ),
    index_palette: int = Query(
        0,
        ge=0,
        le=1,
        description="1 = aplicar paleta de índice (RdYlGn: rojo bajo → verde alto). 0 = sin paleta. "
        "Usar 1 solo en la galería «Visual NDVI/…»; el mapa y la galería RGB envían 0.",
    ),
    s1_derived: str | None = Query(
        None,
        description="Sentinel-1 (VV+VH): vista derivada. vh_vv_ratio = cociente VH/VV en lineal "
        "(log-scale + paleta RdYlGn). Ignora preview_rgb_bands.",
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    require_project_dashboard_access(db, user, tenant_id, project_id)
    raster = _get_project_raster(db, tenant_id, project_id, raster_layer_id)
    path = _existing_raster_path(raster)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Raster file not found")
    try:
        meta = dict(raster.raster_metadata or {})
        # Nombre visible de capa suele conservar ``PS_dd-mm-yy.tif`` aunque el archivo en disco sea uuid.tif.
        if not (meta.get("source_name") or "").strip() and (raster.name or "").strip():
            meta["source_name"] = raster.name
        lab0 = (meta.get("source_name") or raster.name or "").strip()
        if lab0 and is_planetscope_ps_recorte_filename(lab0):
            meta["planetscope_composite"] = True
            meta["preview_rgb_bands"] = [6, 4, 2]
        sd = (s1_derived or "").strip().lower()
        if sd == "vh_vv_ratio":
            png = render_s1_vh_vv_ratio_preview_png(path, layer_metadata=meta)
        elif sd != "":
            raise ValueError(f"s1_derived no reconocido: {s1_derived}")
        elif band is not None:
            rgb_override = (band, band, band)
            png = render_raster_preview_png(
                path,
                layer_metadata=meta,
                rgb_bands_1based=rgb_override,
                index_palette_request=index_palette == 1,
            )
        else:
            png = render_raster_preview_png(
                path,
                layer_metadata=meta,
                rgb_bands_1based=None,
                index_palette_request=index_palette == 1,
            )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"No se pudo generar la vista previa: {exc}") from exc
    return Response(
        content=png,
        media_type="image/png",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@router.get("/raster/{project_id}")
def list_rasters(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    require_project_dashboard_access(db, user, tenant_id, project_id)
    rasters = (
        db.query(RasterLayer)
        .filter(RasterLayer.project_id == project_id, RasterLayer.tenant_id == tenant_id)
        .all()
    )
    filtered = [r for r in rasters if not is_legacy_s2_zip_band_raster(r.raster_metadata)]
    filtered.sort(key=_raster_chronological_sort_key)
    return [{"id": r.id, "name": r.name, "metadata": r.raster_metadata} for r in filtered]


@router.delete("/raster/{project_id}/{raster_id}")
def delete_raster(
    project_id: int,
    raster_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(tenant_from_jwt),
    _admin: User = Depends(require_admin),
):
    raster = (
        db.query(RasterLayer)
        .filter(RasterLayer.id == raster_id, RasterLayer.project_id == project_id, RasterLayer.tenant_id == tenant_id)
        .first()
    )
    if not raster:
        raise HTTPException(status_code=404, detail="Raster layer not found")
    delete_raster_layer_row(db, tenant_id, project_id, raster)
    db.commit()
    return {"status": "ok", "deleted_raster_id": raster_id}


@router.post("/raster/{project_id}/purge-s2-l2a-recortes")
def purge_s2_l2a_recortes_by_sort_keys(
    project_id: int,
    payload: PurgeS2L2aRecortesBody,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(tenant_from_jwt),
    _admin: User = Depends(require_admin),
):
    """
    Elimina capas raster del proyecto que entran en la galería RGB Sentinel-2 y cuya fecha
    de escena coincide con ``s2_sort_keys`` (ISO ``YYYY-MM-DD``). No exige solo
    ``s2_l2a_recorte``: también compuestos true-color / seis bandas si la fecha se deduce
    de metadatos, ruta o nombre ``dd/mm/aaaa_clip`` (casos que antes quedaban fuera del purge).
    """
    keys = _normalize_s2_sort_keys(payload.s2_sort_keys)
    if not keys:
        raise HTTPException(status_code=400, detail="Ninguna fecha válida (use YYYY-MM-DD).")
    key_set = set(keys)
    candidates = (
        db.query(RasterLayer)
        .filter(RasterLayer.project_id == project_id, RasterLayer.tenant_id == tenant_id)
        .all()
    )
    to_delete: list[RasterLayer] = []
    for r in candidates:
        meta = r.raster_metadata or {}
        if not _s2_rgb_gallery_raster_meta(meta):
            continue
        scene = _scene_iso_yyyy_mm_dd_for_purge(r)
        if scene and scene in key_set:
            to_delete.append(r)
    deleted_ids: list[int] = []
    deleted_detail: list[dict] = []
    for r in to_delete:
        rid = r.id
        scene_hit = _scene_iso_yyyy_mm_dd_for_purge(r)
        nm = r.name
        delete_raster_layer_row(db, tenant_id, project_id, r)
        deleted_ids.append(rid)
        deleted_detail.append({"raster_layer_id": rid, "scene_iso": scene_hit, "name": nm})
    db.commit()
    return {
        "status": "ok",
        "deleted_raster_ids": deleted_ids,
        "deleted_count": len(deleted_ids),
        "s2_sort_keys": keys,
        "deleted": deleted_detail,
    }
