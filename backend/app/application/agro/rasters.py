"""Casos de uso Agro: almacenamiento / inventario / borrado de rasters."""
from __future__ import annotations

import re
import shutil
import uuid
import zipfile
from pathlib import Path
from typing import BinaryIO

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.storage_paths import _tenant_storage
from app.domain.agro.repositories import RasterLayerRepository
from app.domain.shared.ports import ProjectRepository
from app.infrastructure.persistence.sqlalchemy_project_repository import (
    SqlAlchemyProjectRepository,
)
from app.models.models import Project, RasterLayer
from app.services.raster_geo import bounds_wgs84_from_path
from app.services.s2_composites import (
    s2_acquisition_date_label,
    s2_date_slug_for_filename,
)
from app.services.s2_vegetation_indices import sort_key_from_path_or_meta
from app.services.sentinel_safe import (
    S2_BANDS_10M_ORDER,
    find_safe_ancestor,
    find_sentinel_r10_band_files,
    looks_like_sentinel2_product_zip_filename,
    safe_extract_zip,
)
from app.tasks.jobs import process_raster, process_s2_zip_layers

_UPLOAD_RASTER_EXTS = {".tif", ".tiff", ".jp2", ".png", ".jpg", ".jpeg", ".zip"}


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

def _tenant_root_path(tenant_id: int) -> Path:
    return (Path(settings.storage_path).resolve() / f"tenant_{tenant_id}").resolve()


def _project_root_path(tenant_id: int, project_id: int) -> Path:
    return (Path(settings.storage_path).resolve() / f"tenant_{tenant_id}" / f"project_{project_id}").resolve()


def _safe_path_under_tenant(tenant_root: Path, rel: str) -> Path:
    rel = (rel or "").strip().replace("\\", "/")
    parts = [p for p in rel.split("/") if p and p != "."]
    root = tenant_root.resolve()
    cur = root
    for p in parts:
        if p == "..":
            raise ValueError("Ruta inválida")
        cur = (cur / p).resolve()
    try:
        cur.relative_to(root)
    except ValueError as exc:
        raise ValueError("Ruta fuera del tenant") from exc
    return cur


def _safe_path_under_project(project_root: Path, rel: str) -> Path:
    rel = (rel or "").strip().replace("\\", "/")
    parts = [p for p in rel.split("/") if p and p != "."]
    root = project_root.resolve()
    cur = root
    for p in parts:
        if p == "..":
            raise ValueError("Ruta inválida")
        cur = (cur / p).resolve()
    try:
        cur.relative_to(root)
    except ValueError as exc:
        raise ValueError("Ruta fuera del proyecto") from exc
    return cur


def _parent_subpath_for_browse(base_root: Path, current: Path) -> str | None:
    try:
        rel = current.resolve().relative_to(base_root.resolve())
    except ValueError:
        return None
    if rel == Path(".") or str(rel) == ".":
        return None
    par = rel.parent
    if par == Path(".") or str(par) == ".":
        return ""
    return par.as_posix()


def _scan_l2a_products_in_dir(root: Path) -> dict:
    out: dict = {
        "downloads_dir": str(root.resolve()),
        "exists": root.is_dir(),
        "zip_l2a": [],
        "safe_folders": [],
        "other_top_level": [],
    }
    if not root.is_dir():
        return out
    try:
        for p in sorted(root.iterdir()):
            if p.is_file():
                if p.suffix.lower() == ".zip":
                    try:
                        sz = p.stat().st_size
                    except OSError:
                        sz = 0
                    entry: dict = {"name": p.name, "size_bytes": sz}
                    if not looks_like_sentinel2_product_zip_filename(p.name):
                        entry["weak_match"] = True
                    out["zip_l2a"].append(entry)
                else:
                    out["other_top_level"].append(p.name)
            elif p.is_dir():
                if p.name.upper().endswith(".SAFE"):
                    out["safe_folders"].append(p.name)
                else:
                    out["other_top_level"].append(p.name + "/")
    except OSError as exc:
        raise RuntimeError(str(exc)) from exc
    return out


def _looks_like_sentinel1_product_zip_filename(name: str) -> bool:
    u = name.upper()
    if not u.endswith(".ZIP"):
        return False
    return "S1" in u and ("IW_GRD" in u or "IW_GRDM" in u or "GRDH" in u)


def _scan_sentinel1_products_in_dir(sentinel1_root: Path) -> dict:
    """
    Inventario bajo ``…/downloads/<slug>/Sentinel1/``: carpetas ``*.SAFE`` (incluye
    subcarpetas p. ej. ``YYYY/MM/`` de descargas antiguas) y ZIP GRD IW en el primer nivel.
    """
    out: dict = {
        "downloads_dir": str(sentinel1_root.resolve()),
        "exists": sentinel1_root.is_dir(),
        "zip_l2a": [],
        "safe_folders": [],
        "other_top_level": [],
    }
    if not sentinel1_root.is_dir():
        return out

    safe_rel_set: set[str] = set()
    try:
        for p in sorted(sentinel1_root.rglob("*")):
            if not p.is_dir():
                continue
            if not p.name.upper().endswith(".SAFE"):
                continue
            try:
                rel = p.resolve().relative_to(sentinel1_root.resolve()).as_posix()
            except ValueError:
                continue
            if rel:
                safe_rel_set.add(rel)
        out["safe_folders"] = sorted(safe_rel_set)

        for p in sorted(sentinel1_root.iterdir()):
            if p.name.startswith("."):
                continue
            if p.is_file():
                if p.suffix.lower() == ".zip":
                    try:
                        sz = p.stat().st_size
                    except OSError:
                        sz = 0
                    entry: dict = {"name": p.name, "size_bytes": sz}
                    if not _looks_like_sentinel1_product_zip_filename(p.name):
                        entry["weak_match"] = True
                    out["zip_l2a"].append(entry)
                else:
                    out["other_top_level"].append(p.name)
            elif p.is_dir():
                if p.name.upper().endswith(".SAFE"):
                    continue
                out["other_top_level"].append(p.name + "/")
    except OSError as exc:
        raise RuntimeError(str(exc)) from exc
    return out


def _raster_chronological_sort_key(raster: RasterLayer) -> str:
    """Clave ISO YYYY-MM-DD para ordenar recortes S2 y otros rasters por fecha de escena."""
    meta = raster.raster_metadata or {}
    sk = meta.get("s2_sort_key")
    if isinstance(sk, str) and sk.strip():
        return sk.strip()
    dl = meta.get("s2_date_label")
    if isinstance(dl, str) and dl.count("/") == 2:
        parts = [p.strip() for p in dl.split("/")]
        if len(parts) == 3:
            dd, mm, yyyy = parts[0], parts[1], parts[2]
            if len(yyyy) == 4 and len(mm) <= 2 and len(dd) <= 2:
                return f"{yyyy}-{mm.zfill(2)}-{dd.zfill(2)}"
    if raster.created_at:
        return raster.created_at.isoformat()
    return f"id_{raster.id:010d}"


def _remove_extract_dir_if_no_other_layers(
    raster_layers: RasterLayerRepository, project_id: int, tenant_id: int, raster: RasterLayer
) -> None:
    """Elimina la carpeta descomprimida solo cuando no queda ninguna capa que la use."""
    meta = raster.raster_metadata or {}
    ex = meta.get("extract_dir")
    if not ex:
        return
    rid = raster.id
    for other in raster_layers.list_for_project_excluding(
        project_id=project_id, tenant_id=tenant_id, exclude_id=rid
    ):
        if (other.raster_metadata or {}).get("extract_dir") == ex:
            return
    try:
        ep = Path(ex).resolve()
        root = Path(settings.storage_path).resolve()
        if str(ep).startswith(str(root)) and ep.is_dir():
            shutil.rmtree(ep, ignore_errors=True)
    except Exception:
        pass


def delete_raster_layer_row(
    raster_layers: RasterLayerRepository,
    tenant_id: int,
    project_id: int,
    raster: RasterLayer,
) -> None:
    """Elimina archivos en disco vinculados a la capa y la fila ``raster_layers``. No hace ``commit``."""
    _remove_extract_dir_if_no_other_layers(raster_layers, project_id, tenant_id, raster)
    stack_p = (raster.raster_metadata or {}).get("s2_stack_path")
    rid = raster.id
    for p in [raster.cog_path, raster.file_path]:
        if p:
            fp = Path(p)
            if fp.exists():
                fp.unlink(missing_ok=True)
    if stack_p:
        others = raster_layers.list_for_project_excluding(
            project_id=project_id, tenant_id=tenant_id, exclude_id=rid
        )
        if not any((o.raster_metadata or {}).get("s2_stack_path") == stack_p for o in others):
            sp = Path(stack_p).resolve()
            root = Path(settings.storage_path).resolve()
            if str(sp).startswith(str(root)) and sp.is_file():
                sp.unlink(missing_ok=True)
    raster_layers.delete(raster)


def _normalize_s2_sort_keys(raw: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for s in raw:
        t = (s or "").strip()
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", t):
            continue
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _s2_rgb_gallery_raster_meta(meta: dict) -> bool:
    """
    Capas que la galería «Visual RGB (Sentinel-2)» puede listar (misma idea que
    ``filterGalleryRasters`` en el frontend), excl. S1, PS y descargas crudas.
    """
    if not meta:
        return False
    if (meta.get("source") == "sentinel-2" or meta.get("source") == "sentinel-1") and meta.get("type") == "download":
        return False
    if is_legacy_s2_zip_band_raster(meta):
        return False
    if not meta.get("bounds_wgs84"):
        return False
    if meta.get("composite_kind") == "false_color_nir":
        return False
    if meta.get("planetscope_composite"):
        return False
    if meta.get("s1_grd_recorte"):
        return False
    return bool(
        meta.get("s2_l2a_recorte")
        or meta.get("s2_four_band_stack")
        or meta.get("s2_six_band_stack")
        or meta.get("composite_kind") == "true_color"
    )


def _scene_iso_yyyy_mm_dd_for_purge(raster: RasterLayer) -> str | None:
    """Fecha de escena ISO (solo metadatos, ruta o nombre ``dd/mm/aaaa_clip``); nunca ``created_at``."""
    meta = raster.raster_metadata or {}
    sk = meta.get("s2_sort_key")
    if isinstance(sk, str):
        t = sk.strip()
        if len(t) >= 10 and re.match(r"^\d{4}-\d{2}-\d{2}", t):
            return t[:10]
    try:
        fp = Path(raster.file_path or "")
    except Exception:
        fp = Path("")
    if raster.file_path:
        fk = sort_key_from_path_or_meta(fp, meta)
        if isinstance(fk, str):
            t = fk.strip()
            if len(t) >= 10 and re.match(r"^\d{4}-\d{2}-\d{2}", t):
                return t[:10]
    dl = meta.get("s2_date_label")
    if isinstance(dl, str) and dl.count("/") == 2:
        parts = [p.strip() for p in dl.split("/")]
        if len(parts) == 3:
            dd, mm, yyyy = parts[0], parts[1], parts[2]
            if len(yyyy) == 4 and dd.isdigit() and mm.isdigit():
                return f"{yyyy}-{mm.zfill(2)}-{dd.zfill(2)}"
    name = (raster.name or "").strip()
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})_clip$", name)
    if m:
        dd, mo, yyyy = m.group(1), m.group(2), m.group(3)
        return f"{yyyy}-{mo}-{dd}"
    return None


def upload_raster(
    db: Session,
    *,
    tenant_id: int,
    project_id: int,
    filename: str | None,
    file_obj: BinaryIO,
    projects: ProjectRepository | None = None,
    raster_layers: RasterLayerRepository | None = None,
) -> dict:
    """
    Sube un GeoTIFF/imagen o un ZIP Sentinel-2 (.SAFE con bandas 10 m).
    Encola Celery ``process_raster`` / ``process_s2_zip_layers``.

    Raises:
        LookupError: proyecto no encontrado
        ValueError: formato no soportado o ZIP inválido / bandas faltantes
    """
    from app.application.agro.repos import raster_layers_repo

    projects = projects or SqlAlchemyProjectRepository(db)
    raster_layers = raster_layers or raster_layers_repo(db)

    project = projects.get_by_id(project_id, tenant_id=tenant_id)
    if not project:
        raise LookupError("Project not found")

    source_name = filename or "upload"
    ext = Path(source_name).suffix.lower()
    if ext not in _UPLOAD_RASTER_EXTS:
        raise ValueError("Unsupported raster format")

    out_dir = _tenant_storage(tenant_id, project_id, "rasters")

    if ext == ".zip":
        return _upload_s2_zip(
            db,
            tenant_id=tenant_id,
            project_id=project_id,
            source_name=source_name,
            file_obj=file_obj,
            out_dir=out_dir,
            raster_layers=raster_layers,
        )

    destination = out_dir / f"{uuid.uuid4().hex}{ext}"
    with destination.open("wb") as buffer:
        shutil.copyfileobj(file_obj, buffer)

    cog_path = out_dir / f"{uuid.uuid4().hex}_cog.tif"
    bounds = bounds_wgs84_from_path(destination)
    meta: dict = {"source_name": source_name, "status": "processing", "cog_ready": False}
    if bounds:
        meta["bounds_wgs84"] = list(bounds)
    raster = RasterLayer(
        project_id=project_id,
        tenant_id=tenant_id,
        name=source_name,
        file_path=str(destination),
        cog_path=str(cog_path),
        raster_metadata=meta,
    )
    raster_layers.save(raster)
    process_raster.delay(str(destination), str(cog_path), raster.id)
    return {"raster_layer_id": raster.id, "metadata": raster.raster_metadata}


def _upload_s2_zip(
    db: Session,
    *,
    tenant_id: int,
    project_id: int,
    source_name: str,
    file_obj: BinaryIO,
    out_dir: Path,
    raster_layers: RasterLayerRepository | None = None,
) -> dict:
    from app.application.agro.repos import raster_layers_repo

    raster_layers = raster_layers or raster_layers_repo(db)
    pack_id = uuid.uuid4().hex
    zip_path = out_dir / f"{pack_id}.zip"
    with zip_path.open("wb") as buffer:
        shutil.copyfileobj(file_obj, buffer)
    extract_dir = out_dir / f"s2_{pack_id}"
    try:
        safe_extract_zip(zip_path, extract_dir)
    except (zipfile.BadZipFile, OSError) as exc:
        zip_path.unlink(missing_ok=True)
        shutil.rmtree(extract_dir, ignore_errors=True)
        raise ValueError("ZIP invalido o no se pudo descomprimir") from exc
    zip_path.unlink(missing_ok=True)

    band_files = find_sentinel_r10_band_files(extract_dir)
    missing = [b for b in S2_BANDS_10M_ORDER if b not in band_files]
    if missing:
        shutil.rmtree(extract_dir, ignore_errors=True)
        raise ValueError(
            f"No se encontraron JP2 de bandas: {', '.join(missing)}. "
            "Se requieren B02, B03, B04 y B08 a 10 m (L2A: IMG_DATA/R10m; "
            "L1C: IMG_DATA con nombres tipo …_B04.jp2). Producto .SAFE completo."
        )

    zip_stem = Path(source_name).stem
    first_jp2 = next(iter(band_files.values()))
    safe_anc = find_safe_ancestor(Path(first_jp2).resolve())
    stem_for_date = safe_anc.stem if safe_anc else zip_stem
    date_label = s2_acquisition_date_label(stem_for_date)
    date_slug = s2_date_slug_for_filename(date_label)
    name_rgb = f"{date_label}_RGB"
    name_nir = f"{date_label}_NIR"

    uid = uuid.uuid4().hex
    stack_tif = out_dir / f"{date_slug}_S2_4band_{pack_id[:8]}.tif"
    rgb_src = out_dir / f"{uid}_rgb.tif"
    nir_src = out_dir / f"{uid}_nir.tif"
    rgb_cog = out_dir / f"{uid}_rgb_cog.tif"
    nir_cog = out_dir / f"{uid}_nir_cog.tif"

    bounds = bounds_wgs84_from_path(band_files["B02"])
    meta_common = {
        "source_name": source_name,
        "status": "processing",
        "cog_ready": False,
        "extract_dir": str(extract_dir),
        "from_zip": True,
        "s2_band_pack": True,
        "s2_composite": True,
        "s2_stack_path": str(stack_tif),
        "s2_stack_band_order": "B04,B03,B02,B08",
        "s2_date_label": date_label,
    }
    if bounds:
        meta_common["bounds_wgs84"] = list(bounds)

    meta_rgb = {
        **meta_common,
        "composite_kind": "true_color",
        "bands_rgb": "R=B04, G=B03, B=B02",
        "derived_from_stack": True,
    }
    meta_nir = {
        **meta_common,
        "composite_kind": "false_color_nir",
        "bands_rgb": "R=B08, G=B04, B=B03",
        "derived_from_stack": True,
    }

    raster_rgb = RasterLayer(
        project_id=project_id,
        tenant_id=tenant_id,
        name=name_rgb,
        file_path=str(rgb_src),
        cog_path=str(rgb_cog),
        raster_metadata=meta_rgb,
    )
    raster_nir = RasterLayer(
        project_id=project_id,
        tenant_id=tenant_id,
        name=name_nir,
        file_path=str(nir_src),
        cog_path=str(nir_cog),
        raster_metadata=meta_nir,
    )
    raster_layers.save(raster_rgb)
    raster_layers.save(raster_nir)

    band_paths = {k: str(v) for k, v in band_files.items()}
    process_s2_zip_layers.delay(
        band_paths,
        str(stack_tif),
        str(rgb_src),
        str(nir_src),
        str(rgb_cog),
        str(nir_cog),
        raster_rgb.id,
        raster_nir.id,
    )

    items = [
        {
            "id": raster_rgb.id,
            "name": name_rgb,
            "composite": "rgb",
            "metadata": meta_rgb,
        },
        {
            "id": raster_nir.id,
            "name": name_nir,
            "composite": "nir",
            "metadata": meta_nir,
        },
    ]
    return {
        "raster_layer_id": raster_rgb.id,
        "raster_layer_ids": [raster_rgb.id, raster_nir.id],
        "layers": items,
        "metadata": meta_rgb,
    }

