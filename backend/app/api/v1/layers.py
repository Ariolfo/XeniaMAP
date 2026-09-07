import json
import logging
import re
import shutil
import uuid
import zipfile
from pathlib import Path

from defusedxml.ElementTree import fromstring as safe_xml_parse
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.api.deps import (
    get_current_user,
    require_project_dashboard_access,
    tenant_from_jwt,
)
from app.api.v1.helpers import _tenant_storage, validate_upload_size
from app.application.agro.repos import layers_repo
from app.application.agro.layer_mvt import (
    MVT_SOURCE_LAYER,
    RenderLayerMvtTile,
    SyncLayerGeom,
    layer_geom_meta,
)
from app.db.session import get_db
from app.models.models import Layer, Project, User

logger = logging.getLogger(__name__)
router = APIRouter()


def _safe_zip_name(name: str) -> bool:
    return ".." not in name and not name.startswith("/") and not name.startswith("\\")


@router.post("/upload-shapefile")
async def upload_shapefile(
    project_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(tenant_from_jwt),
):
    project = db.query(Project).filter(Project.id == project_id, Project.tenant_id == tenant_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    await validate_upload_size(file)
    out_dir = _tenant_storage(tenant_id, project_id, "vectors")
    ext = Path(file.filename).suffix.lower()
    if ext not in {".zip", ".shp", ".geojson", ".json", ".kml", ".kmz"}:
        raise HTTPException(status_code=400, detail="Unsupported vector format")
    destination = out_dir / f"{uuid.uuid4().hex}{ext}"
    with destination.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    layer = Layer(
        project_id=project_id,
        tenant_id=tenant_id,
        name=file.filename,
        file_path=str(destination),
        geom_type="Vector",
        layer_metadata={"source_name": file.filename},
    )
    db.add(layer)
    db.commit()
    db.refresh(layer)
    sync_meta: dict = {"mvt_ready": False, "bbox": None}
    try:
        sync_meta = SyncLayerGeom().execute(layers_repo(db), layer=layer)
    except Exception as exc:
        logger.warning("upload-shapefile: sync geom falló layer=%s: %s", layer.id, exc)
    return {
        "layer_id": layer.id,
        "mvt_ready": bool(sync_meta.get("mvt_ready")),
        "bbox": sync_meta.get("bbox"),
        "mvt_source_layer": MVT_SOURCE_LAYER,
    }


@router.get("/layers/{project_id}")
def list_layers(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    require_project_dashboard_access(db, user, tenant_id, project_id)
    layers = (
        db.query(Layer)
        .filter(Layer.project_id == project_id, Layer.tenant_id == tenant_id)
        .all()
    )
    meta_by_id = layer_geom_meta(layers_repo(db), layer_ids=[l.id for l in layers])
    return [
        {
            "id": l.id,
            "name": l.name,
            "geom_type": l.geom_type,
            "metadata": l.layer_metadata,
            "mvt_ready": bool(meta_by_id.get(l.id, {}).get("mvt_ready")),
            "bbox": meta_by_id.get(l.id, {}).get("bbox"),
            "mvt_source_layer": MVT_SOURCE_LAYER,
        }
        for l in layers
    ]


@router.delete("/layers/{project_id}/{layer_id}")
def delete_layer(
    project_id: int,
    layer_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(tenant_from_jwt),
):
    layer = (
        db.query(Layer)
        .filter(Layer.id == layer_id, Layer.project_id == project_id, Layer.tenant_id == tenant_id)
        .first()
    )
    if not layer:
        raise HTTPException(status_code=404, detail="Layer not found")
    fp = Path(layer.file_path)
    if fp.exists():
        fp.unlink(missing_ok=True)
    db.delete(layer)
    db.commit()
    return {"status": "ok", "deleted_layer_id": layer_id}


def _kml_to_geojson(kml_text: str) -> dict | None:
    root = safe_xml_parse(kml_text)
    ns = re.match(r"\{.*\}", root.tag)
    ns = ns.group(0) if ns else ""
    features = []
    for pm in root.iter(f"{ns}Placemark"):
        name_el = pm.find(f"{ns}name")
        name = name_el.text if name_el is not None else ""
        coords_el = pm.find(f".//{ns}coordinates")
        if coords_el is None or not coords_el.text:
            continue
        raw = coords_el.text.strip()
        points = []
        for s in raw.split():
            parts = s.split(",")
            if len(parts) >= 2:
                points.append([float(parts[0]), float(parts[1])])
        if not points:
            continue
        if len(points) == 1:
            geometry = {"type": "Point", "coordinates": points[0]}
        elif len(points) > 2 and points[0] == points[-1]:
            geometry = {"type": "Polygon", "coordinates": [points]}
        else:
            geometry = {"type": "LineString", "coordinates": points}
        features.append({"type": "Feature", "properties": {"name": name}, "geometry": geometry})
    if not features:
        return None
    return {"type": "FeatureCollection", "features": features}


@router.get("/layers/{project_id}/{layer_id}/geojson")
def get_layer_geojson(
    project_id: int,
    layer_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    require_project_dashboard_access(db, user, tenant_id, project_id)
    layer = (
        db.query(Layer)
        .filter(Layer.id == layer_id, Layer.project_id == project_id, Layer.tenant_id == tenant_id)
        .first()
    )
    if not layer:
        raise HTTPException(status_code=404, detail="Layer not found")
    fp = Path(layer.file_path)
    if not fp.exists():
        raise HTTPException(status_code=404, detail="Layer file not found on disk")
    ext = fp.suffix.lower()
    if ext in {".geojson", ".json"}:
        return JSONResponse(json.loads(fp.read_text(encoding="utf-8")))
    if ext == ".kml":
        result = _kml_to_geojson(fp.read_text(encoding="utf-8"))
        if result:
            return JSONResponse(result)
    if ext == ".kmz":
        try:
            with zipfile.ZipFile(fp) as zf:
                for name in zf.namelist():
                    if not _safe_zip_name(name):
                        continue
                    if name.lower().endswith(".kml"):
                        kml_text = zf.read(name).decode("utf-8")
                        result = _kml_to_geojson(kml_text)
                        if result:
                            return JSONResponse(result)
        except Exception:
            pass
    if ext == ".zip":
        try:
            with zipfile.ZipFile(fp) as zf:
                for name in zf.namelist():
                    if not _safe_zip_name(name):
                        continue
                    if name.lower().endswith((".geojson", ".json")):
                        return JSONResponse(json.loads(zf.read(name).decode("utf-8")))
                    if name.lower().endswith(".kml"):
                        result = _kml_to_geojson(zf.read(name).decode("utf-8"))
                        if result:
                            return JSONResponse(result)
        except Exception:
            pass
    raise HTTPException(status_code=422, detail="Cannot convert this layer to GeoJSON")


@router.post("/layers/{project_id}/{layer_id}/sync-geom")
def sync_layer_geom(
    project_id: int,
    layer_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    """Backfill ``layers.geom`` desde el archivo en disco (admin o dashboard)."""
    require_project_dashboard_access(db, user, tenant_id, project_id)
    layer = (
        db.query(Layer)
        .filter(Layer.id == layer_id, Layer.project_id == project_id, Layer.tenant_id == tenant_id)
        .first()
    )
    if not layer:
        raise HTTPException(status_code=404, detail="Layer not found")
    try:
        out = SyncLayerGeom().execute(layers_repo(db), layer=layer)
    except Exception as exc:
        logger.exception("sync-geom falló layer=%s", layer_id)
        raise HTTPException(status_code=500, detail=f"sync-geom failed: {exc}") from exc
    if not out.get("ok"):
        raise HTTPException(
            status_code=422,
            detail=out.get("detail") or "Cannot sync layer geometry",
        )
    return {
        "layer_id": layer_id,
        "mvt_ready": True,
        "bbox": out.get("bbox"),
        "mvt_source_layer": MVT_SOURCE_LAYER,
    }


@router.get("/layers/{project_id}/{layer_id}/tiles/{z}/{x}/{y}.mvt")
def get_layer_mvt_tile(
    project_id: int,
    layer_id: int,
    z: int,
    x: int,
    y: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    """Vector tile Mapbox (MVT) desde ``layers.geom`` (PostGIS ``ST_AsMVT``)."""
    require_project_dashboard_access(db, user, tenant_id, project_id)
    layer = (
        db.query(Layer)
        .filter(Layer.id == layer_id, Layer.project_id == project_id, Layer.tenant_id == tenant_id)
        .first()
    )
    if not layer:
        raise HTTPException(status_code=404, detail="Layer not found")
    try:
        payload = RenderLayerMvtTile().execute(layers_repo(db), layer=layer, z=z, x=x, y=y)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LookupError:
        raise HTTPException(status_code=404, detail="Layer geometry not available for MVT") from None
    except Exception as exc:
        logger.exception("mvt tile falló layer=%s z=%s x=%s y=%s", layer_id, z, x, y)
        raise HTTPException(status_code=500, detail=f"MVT render failed: {exc}") from exc
    return Response(
        content=payload,
        media_type="application/vnd.mapbox-vector-tile",
        headers={"Cache-Control": "private, max-age=60"},
    )
