"""Rutas admin: browse disco / inventarios / import (H1 — separado del mapa cliente)."""
from __future__ import annotations

import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import require_admin, tenant_from_jwt
from app.api.v1.helpers import (
    _tenant_storage,
    encode_source_subpath_for_path,
    external_data_root_path,
    encode_external_subpath,
    project_downloads_dir,
    project_relative_posix,
    project_sentinel1_dir,
    project_sentinel2_dir,
    resolve_source_subpath,
    validate_upload_size,
)
from app.db.session import get_db
from app.models.models import Project, RasterLayer, User
from app.services.raster_geo import bounds_wgs84_from_path
from app.tasks.jobs import process_raster
from app.application.agro.rasters import (
    _parent_subpath_for_browse,
    _project_root_path,
    _tenant_root_path,
)
from app.application.agro import rasters as _rasters_uc

router = APIRouter()


def _safe_path_under_tenant(tenant_root: Path, rel: str) -> Path:
    try:
        return _rasters_uc._safe_path_under_tenant(tenant_root, rel)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _safe_path_under_project(project_root: Path, rel: str) -> Path:
    try:
        return _rasters_uc._safe_path_under_project(project_root, rel)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _scan_l2a_products_in_dir(root: Path) -> dict:
    try:
        return _rasters_uc._scan_l2a_products_in_dir(root)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _scan_sentinel1_products_in_dir(sentinel1_root: Path) -> dict:
    try:
        return _rasters_uc._scan_sentinel1_products_in_dir(sentinel1_root)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/raster/tenant-storage-browse")
def tenant_storage_browse(
    path: str = Query("", description="Ruta relativa bajo storage/tenant_*/"),
    tenant_id: int = Depends(tenant_from_jwt),
    _admin: User = Depends(require_admin),
):
    """Lista carpetas y archivos desde la raíz del tenant (p. ej. project_1, project_2, …)."""
    root = _tenant_root_path(tenant_id)
    if not root.is_dir():
        raise HTTPException(status_code=404, detail="Carpeta del tenant no existe en almacenamiento")
    target = _safe_path_under_tenant(root, path)
    if not target.is_dir():
        raise HTTPException(status_code=404, detail="No es una carpeta")
    entries: list[dict] = []
    try:
        for p in sorted(target.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if p.name.startswith("."):
                continue
            try:
                rel_posix = p.resolve().relative_to(root.resolve()).as_posix()
            except ValueError:
                continue
            if p.is_dir():
                entries.append({"name": p.name, "kind": "dir", "relative_path": rel_posix})
            else:
                try:
                    sz = p.stat().st_size if p.is_file() else 0
                except OSError:
                    sz = 0
                entries.append(
                    {"name": p.name, "kind": "file", "relative_path": rel_posix, "size_bytes": sz}
                )
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    try:
        rel_current = target.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        rel_current = ""
    parent_subpath = _parent_subpath_for_browse(root, target)
    return {
        "tenant_root": str(root),
        "relative_path": rel_current,
        "parent_subpath": parent_subpath,
        "entries": entries,
    }


@router.get("/raster/external-data-status")
def external_data_status(
    tenant_id: int = Depends(tenant_from_jwt),
    _admin: User = Depends(require_admin),
):
    """Indica si hay disco externo montado y listo para recorte local."""
    root = external_data_root_path()
    return {
        "enabled": root is not None,
        "root": str(root) if root else None,
        "label": "Disco externo",
    }


@router.get("/raster/external-data-browse")
def external_data_browse(
    path: str = Query("", description="Ruta relativa (posix) bajo EXTERNAL_DATA_ROOT"),
    tenant_id: int = Depends(tenant_from_jwt),
    _admin: User = Depends(require_admin),
):
    """Navega carpetas en el disco externo local (sin copiar al proyecto)."""
    root = external_data_root_path()
    if root is None:
        raise HTTPException(
            status_code=503,
            detail="Disco externo no configurado o no montado (EXTERNAL_DATA_ROOT).",
        )
    target = _safe_path_under_project(root, path)
    if not target.is_dir():
        raise HTTPException(status_code=404, detail="No es una carpeta")
    entries: list[dict] = []
    try:
        for p in sorted(target.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if p.name.startswith("."):
                continue
            try:
                rel_posix = p.resolve().relative_to(root.resolve()).as_posix()
            except ValueError:
                continue
            if p.is_dir():
                entries.append({"name": p.name, "kind": "dir", "relative_path": rel_posix})
            else:
                try:
                    sz = p.stat().st_size if p.is_file() else 0
                except OSError:
                    sz = 0
                entries.append(
                    {"name": p.name, "kind": "file", "relative_path": rel_posix, "size_bytes": sz}
                )
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    try:
        rel_current = target.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        rel_current = ""
    parent_subpath = _parent_subpath_for_browse(root, target)
    return {
        "root": str(root),
        "relative_path": rel_current,
        "parent_subpath": parent_subpath,
        "source_subpath": encode_external_subpath(rel_current),
        "entries": entries,
    }


@router.post("/raster/external-data-mkdir")
def external_data_mkdir(
    name: str = Form(..., description="Nombre de la carpeta nueva (un solo segmento)"),
    parent_path: str = Form("", description="Ruta relativa bajo el disco externo donde crear"),
    tenant_id: int = Depends(tenant_from_jwt),
    _admin: User = Depends(require_admin),
):
    """Crea una subcarpeta bajo el disco externo (p. ej. un lote nuevo)."""
    root = external_data_root_path()
    if root is None:
        raise HTTPException(
            status_code=503,
            detail="Disco externo no configurado o no montado (EXTERNAL_DATA_ROOT).",
        )
    raw_name = str(name or "").strip()
    if not raw_name or "/" in raw_name or "\\" in raw_name or raw_name in {".", ".."}:
        raise HTTPException(status_code=400, detail="Nombre de carpeta inválido")
    if not re.fullmatch(r"[A-Za-z0-9ÁÉÍÓÚáéíóúÑñ _.\-]{1,120}", raw_name):
        raise HTTPException(status_code=400, detail="Nombre de carpeta con caracteres no permitidos")
    parent = _safe_path_under_project(root, parent_path)
    if not parent.is_dir():
        raise HTTPException(status_code=404, detail="Carpeta padre no existe")
    dest = (parent / raw_name).resolve()
    try:
        dest.relative_to(root.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Ruta fuera del disco externo") from exc
    if dest.exists():
        if not dest.is_dir():
            raise HTTPException(status_code=400, detail="Ya existe un archivo con ese nombre")
    else:
        dest.mkdir(parents=False, exist_ok=False)
    try:
        rel = dest.relative_to(root.resolve()).as_posix()
    except ValueError:
        rel = raw_name
    return {
        "ok": True,
        "relative_path": rel,
        "source_subpath": encode_external_subpath(rel),
    }


@router.get("/raster/project-storage-browse/{project_id}")
def project_storage_browse(
    project_id: int,
    path: str = Query("", description="Ruta relativa (posix) bajo la raíz del proyecto"),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(tenant_from_jwt),
    _admin: User = Depends(require_admin),
):
    """Lista carpetas y archivos para navegar desde la raíz del proyecto (storage/tenant_*/project_*)."""
    project = db.query(Project).filter(Project.id == project_id, Project.tenant_id == tenant_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    root = _project_root_path(tenant_id, project_id)
    if not root.is_dir():
        raise HTTPException(status_code=404, detail="Carpeta del proyecto no existe en almacenamiento")
    target = _safe_path_under_project(root, path)
    if not target.is_dir():
        raise HTTPException(status_code=404, detail="No es una carpeta")
    entries: list[dict] = []
    try:
        for p in sorted(target.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if p.name.startswith("."):
                continue
            try:
                rel_posix = p.resolve().relative_to(root.resolve()).as_posix()
            except ValueError:
                continue
            if p.is_dir():
                entries.append({"name": p.name, "kind": "dir", "relative_path": rel_posix})
            else:
                try:
                    sz = p.stat().st_size if p.is_file() else 0
                except OSError:
                    sz = 0
                entries.append(
                    {"name": p.name, "kind": "file", "relative_path": rel_posix, "size_bytes": sz}
                )
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    try:
        rel_current = target.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        rel_current = ""
    parent_subpath = _parent_subpath_for_browse(root, target)
    return {
        "project_root": str(root),
        "relative_path": rel_current,
        "parent_subpath": parent_subpath,
        "entries": entries,
    }


@router.get("/raster/project-downloads-inventory/{project_id}")
def project_downloads_inventory(
    project_id: int,
    subpath: str | None = Query(
        None,
        description="Si se envía, lista L2A en esa ruta (proyecto o ``ext:``). Si se omite, ``downloads/<slug>/Sentinel2/``.",
    ),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(tenant_from_jwt),
    _admin: User = Depends(require_admin),
):
    """
    Lista productos Sentinel-2 (ZIP y carpetas .SAFE reconocibles, p. ej. L2A/L1C) en el directorio indicado (primer nivel),
    más otros elementos del mismo nivel.
    Sin ``subpath``: ``downloads/<slug>/Sentinel2/`` (misma carpeta que la descarga Sentinel-2).
    Con ``subpath``: carpeta bajo la raíz del proyecto (p. ej. ``downloads/mi_slug/Sentinel2``).
    """
    project = db.query(Project).filter(Project.id == project_id, Project.tenant_id == tenant_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if subpath is None:
        root = project_sentinel2_dir(tenant_id, project_id, project.name)
    else:
        resolved = resolve_source_subpath(tenant_id, project_id, subpath)
        if resolved is None:
            raise HTTPException(status_code=400, detail="Ruta subpath inválida")
        root = resolved
    out = _scan_l2a_products_in_dir(root)
    out["source_subpath"] = encode_source_subpath_for_path(tenant_id, project_id, root, subpath)
    return out


@router.get("/raster/project-sentinel1-inventory/{project_id}")
def project_sentinel1_inventory(
    project_id: int,
    subpath: str | None = Query(
        None,
        description="Si se envía, lista S1 en esa ruta (proyecto o ``ext:``). Si se omite, ``downloads/<slug>/Sentinel1/``.",
    ),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(tenant_from_jwt),
    _admin: User = Depends(require_admin),
):
    """
    Lista productos Sentinel-1 (carpetas ``*.SAFE``, ZIP GRD) en la carpeta indicada.
    Sin ``subpath``: ``downloads/<slug>/Sentinel1/``.
    """
    project = db.query(Project).filter(Project.id == project_id, Project.tenant_id == tenant_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if subpath is None:
        root = project_sentinel1_dir(tenant_id, project_id, project.name)
    else:
        resolved = resolve_source_subpath(tenant_id, project_id, subpath)
        if resolved is None:
            raise HTTPException(status_code=400, detail="Ruta subpath inválida")
        root = resolved
    out = _scan_sentinel1_products_in_dir(root)
    out["source"] = "sentinel-1"
    out["source_subpath"] = encode_source_subpath_for_path(tenant_id, project_id, root, subpath)
    return out


@router.get("/raster/project-planetscope-zip-inventory/{project_id}")
def project_planetscope_zip_inventory(
    project_id: int,
    subpath: str | None = Query(
        None,
        description="Si se envía, lista ZIP en esa ruta (proyecto o ``ext:``). Si se omite, ``rasterPS/``.",
    ),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(tenant_from_jwt),
    _admin: User = Depends(require_admin),
):
    """Lista ``*.zip`` PlanetScope en la carpeta origen (por defecto ``rasterPS/``)."""
    from app.services.preprocess_pipeline_variant import planet_zip_dir_name

    project = db.query(Project).filter(Project.id == project_id, Project.tenant_id == tenant_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if subpath is None:
        root = _tenant_storage(tenant_id, project_id, planet_zip_dir_name())
    else:
        resolved = resolve_source_subpath(tenant_id, project_id, subpath)
        if resolved is None:
            raise HTTPException(status_code=400, detail="Ruta subpath inválida")
        root = resolved
    zips: list[dict] = []
    if root.is_dir():
        for p in sorted(root.glob("*.zip")):
            try:
                sz = p.stat().st_size
            except OSError:
                sz = 0
            zips.append({"name": p.name, "size_bytes": sz})
    return {
        "downloads_dir": str(root.resolve()),
        "exists": root.is_dir(),
        "zips": zips,
        "source_subpath": encode_source_subpath_for_path(tenant_id, project_id, root, subpath),
    }


def _safe_relative_import_path(rel: str) -> str | None:
    """Normaliza ruta relativa de importación local; rechaza absolutas y ``..``."""
    raw = str(rel or "").strip().replace("\\", "/")
    if not raw or raw.startswith("/") or raw.startswith("~"):
        return None
    parts = [p for p in raw.split("/") if p and p != "."]
    if not parts or any(p == ".." for p in parts):
        return None
    # Quitar el primer segmento (nombre de la carpeta elegida en el SO).
    if len(parts) > 1:
        parts = parts[1:]
    if not parts:
        return None
    return "/".join(parts)


@router.post("/raster/project-local-folder-import/{project_id}")
async def project_local_folder_import(
    project_id: int,
    kind: str = Form(..., description="s1 | s2 | ps"),
    relative_path: str = Form(..., description="Ruta relativa del archivo (webkitRelativePath)"),
    file: UploadFile = File(...),
    batch_id: str | None = Form(None, description="Id de lote; si se omite se crea uno nuevo"),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(tenant_from_jwt),
    _admin: User = Depends(require_admin),
):
    """
    Sube un archivo desde el computador del usuario a ``local_import/<kind>/<batch_id>/``.
    Tras subir toda la carpeta, usar ``source_subpath`` devuelto como origen del recorte.
    """
    project = db.query(Project).filter(Project.id == project_id, Project.tenant_id == tenant_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    k = str(kind or "").strip().lower()
    if k not in {"s1", "s2", "ps"}:
        raise HTTPException(status_code=400, detail="kind debe ser s1, s2 o ps")
    rel = _safe_relative_import_path(relative_path)
    if not rel:
        raise HTTPException(status_code=400, detail="relative_path inválida")
    await validate_upload_size(file)

    bid = str(batch_id or "").strip()
    if not bid:
        bid = datetime.utcnow().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
    elif not re.fullmatch(r"[A-Za-z0-9_\-]{4,64}", bid):
        raise HTTPException(status_code=400, detail="batch_id inválido")

    dest_root = _tenant_storage(tenant_id, project_id, "local_import") / k / bid
    dest_file = (dest_root / rel).resolve()
    try:
        dest_file.relative_to(dest_root.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Ruta fuera del destino de importación") from exc
    dest_file.parent.mkdir(parents=True, exist_ok=True)
    with dest_file.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    source_subpath = project_relative_posix(tenant_id, project_id, dest_root)
    return {
        "ok": True,
        "batch_id": bid,
        "saved_as": rel,
        "source_subpath": source_subpath,
        "bytes": dest_file.stat().st_size if dest_file.is_file() else 0,
    }


def _merge_copy_downloads_dir(src: Path, dst: Path) -> int:
    """
    Copia el contenido de ``src`` dentro de ``dst``, fusionando carpetas con el mismo nombre.
    Devuelve el número de archivos copiados (incluye archivos dentro de árboles copiados con copytree).
    """
    n_files = 0
    dst.mkdir(parents=True, exist_ok=True)
    for child in sorted(src.iterdir()):
        if child.name.startswith("."):
            continue
        target = dst / child.name
        if child.is_file():
            shutil.copy2(child, target)
            n_files += 1
        elif child.is_dir():
            if target.exists():
                if not target.is_dir():
                    raise HTTPException(
                        status_code=409,
                        detail=f"Conflicto: «{child.name}» existe como archivo en destino y como carpeta en origen.",
                    )
                n_files += _merge_copy_downloads_dir(child, target)
            else:
                shutil.copytree(child, target)
                n_files += sum(1 for p in child.rglob("*") if p.is_file())
        else:
            continue
    return n_files


@router.post("/raster/copy-downloads-from-project")
def copy_downloads_from_project(
    source_project_id: int = Query(..., description="Proyecto origen (tiene las descargas)"),
    target_project_id: int = Query(..., description="Proyecto destino (proyecto actual)"),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(tenant_from_jwt),
    _admin: User = Depends(require_admin),
):
    """
    Copia el contenido de ``downloads/<slug>`` del proyecto origen sobre la carpeta de descargas del proyecto destino
    (mismo tenant). No elimina archivos previos en destino; fusiona por nombre.
    """
    if source_project_id == target_project_id:
        raise HTTPException(status_code=400, detail="El origen y el destino deben ser proyectos distintos.")
    src_project = db.query(Project).filter(Project.id == source_project_id, Project.tenant_id == tenant_id).first()
    tgt_project = db.query(Project).filter(Project.id == target_project_id, Project.tenant_id == tenant_id).first()
    if not src_project or not tgt_project:
        raise HTTPException(status_code=404, detail="Project not found")
    src_dir = project_downloads_dir(tenant_id, source_project_id, src_project.name)
    tgt_dir = project_downloads_dir(tenant_id, target_project_id, tgt_project.name)
    if not src_dir.is_dir():
        raise HTTPException(
            status_code=404,
            detail="El proyecto origen no tiene carpeta de descargas (downloads).",
        )
    if not any(src_dir.iterdir()):
        raise HTTPException(status_code=400, detail="La carpeta de descargas del proyecto origen está vacía.")
    n_files = _merge_copy_downloads_dir(src_dir, tgt_dir)
    return {
        "ok": True,
        "source_project_id": source_project_id,
        "target_project_id": target_project_id,
        "files_copied": n_files,
        "target_downloads_dir": str(tgt_dir.resolve()),
    }


@router.get("/raster/project-downloads/{project_id}")
def list_project_download_files(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(tenant_from_jwt),
    _admin: User = Depends(require_admin),
):
    """List files in the project's Sentinel-2 download folder (not shown as map layers until imported)."""
    project = db.query(Project).filter(Project.id == project_id, Project.tenant_id == tenant_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    d = project_sentinel2_dir(tenant_id, project_id, project.name)
    if not d.is_dir():
        return {"files": [], "folder": project.name}
    allowed = {".tif", ".tiff", ".jp2", ".zip", ".png", ".jpg", ".jpeg"}
    files = []
    for p in sorted(d.iterdir()):
        if p.is_file() and p.suffix.lower() in allowed:
            try:
                sz = p.stat().st_size
            except OSError:
                continue
            files.append({"name": p.name, "size_bytes": sz, "ext": p.suffix.lower()})
    return {"files": files, "folder": project.name}


@router.post("/raster/import-from-downloads")
def import_raster_from_downloads(
    project_id: int = Query(..., description="Project ID"),
    filename: str = Query(..., description="File name inside project download folder"),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(tenant_from_jwt),
    _admin: User = Depends(require_admin),
):
    """Copy a file from the project download folder into rasters and register as a normal raster layer."""
    safe = Path(filename).name
    if safe != filename or ".." in safe:
        raise HTTPException(status_code=400, detail="Invalid filename")

    project = db.query(Project).filter(Project.id == project_id, Project.tenant_id == tenant_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    src_dir = project_sentinel2_dir(tenant_id, project_id, project.name)
    src = (src_dir / safe).resolve()
    base = src_dir.resolve()
    if not str(src).startswith(str(base)) or not src.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    ext = src.suffix.lower()
    if ext not in {".tif", ".tiff", ".jp2", ".png", ".jpg", ".jpeg"}:
        raise HTTPException(
            status_code=400,
            detail="Solo se pueden importar como capa raster: GeoTIFF, JP2 o imagen. Para .ZIP use extracción manual.",
        )

    out_dir = _tenant_storage(tenant_id, project_id, "rasters")
    destination = out_dir / f"{uuid.uuid4().hex}{ext}"
    shutil.copy2(src, destination)
    cog_path = out_dir / f"{destination.stem}_cog.tif"
    bounds = bounds_wgs84_from_path(destination)
    meta = {
        "source_name": safe,
        "status": "processing",
        "cog_ready": False,
        "imported_from": "project_downloads",
    }
    if bounds:
        meta["bounds_wgs84"] = list(bounds)
    raster = RasterLayer(
        project_id=project_id,
        tenant_id=tenant_id,
        name=safe,
        file_path=str(destination),
        cog_path=str(cog_path),
        raster_metadata=meta,
    )
    db.add(raster)
    db.commit()
    db.refresh(raster)
    process_raster.delay(str(destination), str(cog_path), raster.id)
    return {"raster_layer_id": raster.id, "name": safe, "metadata": raster.raster_metadata}


