"""Recorte de GeoTIFF PlanetScope: origen ``rasterPS/`` (originales) → ``recortesPS/`` (recortados)."""

from __future__ import annotations

import logging
from pathlib import Path

from app.services.preprocess_pipeline_variant import (
    is_planetscope_ps_recorte_filename,
    planet_zip_dir_name,
    recortes_dir_name,
)
from app.services.raster_clip import clip_raster_by_wkt_polygon

logger = logging.getLogger(__name__)

PS_CLIP_SOURCE_RECORTE = "recortesPS"
PS_CLIP_SOURCE_RASTER = "rasterPS"
PS_CLIP_SOURCES = frozenset({PS_CLIP_SOURCE_RECORTE, PS_CLIP_SOURCE_RASTER})
# Flujo canónico: originales en rasterPS/, recorte → recortesPS/
DEFAULT_PS_CLIP_SOURCE = PS_CLIP_SOURCE_RASTER


def normalize_ps_clip_source(value: str | None) -> str:
    raw = (value or DEFAULT_PS_CLIP_SOURCE).strip()
    if raw in ("recortes", "recortesps", "recorte"):
        return PS_CLIP_SOURCE_RECORTE
    if raw in ("raster", "rasterps", "zips"):
        return PS_CLIP_SOURCE_RASTER
    if raw in PS_CLIP_SOURCES:
        return raw
    return DEFAULT_PS_CLIP_SOURCE


def ps_clip_source_dir_name(source: str) -> str:
    kind = normalize_ps_clip_source(source)
    if kind == PS_CLIP_SOURCE_RASTER:
        return planet_zip_dir_name()
    return recortes_dir_name("ps")


def _is_candidate_tif(path: Path, source: str) -> bool:
    if not path.is_file():
        return False
    name = path.name
    low = name.lower()
    if not low.endswith(".tif") and not low.endswith(".tiff"):
        return False
    if "_cog" in low:
        return False
    if "udm2" in low:
        return False
    # En ambas carpetas preferimos composites PS_dd-mm-yy.tif; en rasterPS también se aceptan otros .tif.
    if normalize_ps_clip_source(source) == PS_CLIP_SOURCE_RECORTE:
        return is_planetscope_ps_recorte_filename(name)
    return True


def list_ps_clip_tifs(root: Path, source: str) -> list[Path]:
    """Lista GeoTIFF candidatos bajo ``root`` (solo primer nivel)."""
    if not root.is_dir():
        return []
    out: list[Path] = []
    try:
        for p in sorted(root.iterdir()):
            if _is_candidate_tif(p, source):
                out.append(p)
    except OSError:
        return []
    return out


def _unique_path(target: Path) -> Path:
    if not target.exists():
        return target
    stem, suf = target.stem, target.suffix
    n = 1
    while True:
        alt = target.with_name(f"{stem}_{n}{suf}")
        if not alt.exists():
            return alt
        n += 1


def _dest_in_recortes_ps(out_root: Path, src: Path) -> Path:
    """
    Destino en ``recortesPS/``: mismo basename ``PS_*.tif`` (sobrescribe).
    Otros nombres se escriben con basename único para no pisar un PS_ existente.
    """
    if is_planetscope_ps_recorte_filename(src.name):
        return out_root / src.name
    return _unique_path(out_root / src.name)


def clip_ps_tifs_by_wkt(
    source_root: Path,
    out_root: Path,
    wkt: str,
    source: str,
    filenames: list[str] | None = None,
) -> dict:
    """
    Recorta TIF del origen al polígono WKT y escribe en ``out_root`` (``recortesPS/``).

    Flujo esperado: origen ``rasterPS/`` (originales) → ``recortesPS/`` (insumos de RGB/índices).
    Si origen y destino son el mismo archivo, usa temporal y reemplaza.
    """
    kind = normalize_ps_clip_source(source)
    candidates = list_ps_clip_tifs(source_root, kind)
    if not candidates:
        return {
            "ok": False,
            "error": "no_tif",
            "message": f"No hay GeoTIFF válidos en {ps_clip_source_dir_name(kind)}/",
            "processed": 0,
            "outputs": [],
            "errors": [],
            "pipeline": "ps_recorte_clip",
            "source": kind,
        }

    if filenames:
        allowed = {Path(str(x).strip()).name for x in filenames if str(x).strip()}
        if not allowed:
            return {
                "ok": False,
                "error": "no_selection",
                "message": "Lista de archivos vacía.",
                "processed": 0,
                "outputs": [],
                "errors": [],
                "pipeline": "ps_recorte_clip",
                "source": kind,
            }
        candidates = [p for p in candidates if p.name in allowed]
        if not candidates:
            return {
                "ok": False,
                "error": "no_match",
                "message": "Ningún nombre coincide con TIF en la carpeta origen.",
                "processed": 0,
                "outputs": [],
                "errors": [],
                "pipeline": "ps_recorte_clip",
                "source": kind,
            }

    out_root.mkdir(parents=True, exist_ok=True)
    outputs: list[dict] = []
    errors: list[str] = []

    for src in candidates:
        try:
            dest = _dest_in_recortes_ps(out_root, src)
            same_file = False
            try:
                same_file = src.resolve() == dest.resolve() and dest.exists()
            except OSError:
                same_file = False

            if same_file:
                tmp = out_root / f".{src.stem}_clip_tmp{src.suffix}"
                try:
                    clip_raster_by_wkt_polygon(src, wkt, tmp)
                    tmp.replace(dest)
                finally:
                    tmp.unlink(missing_ok=True)
            else:
                # Escribir a temporal en destino y luego reemplazar (evita TIF a medias si falla).
                tmp = out_root / f".{dest.stem}_clip_tmp{dest.suffix}"
                try:
                    clip_raster_by_wkt_polygon(src, wkt, tmp)
                    tmp.replace(dest)
                finally:
                    tmp.unlink(missing_ok=True)

            outputs.append({"source": src.name, "file": str(dest), "basename": dest.name})
            logger.info("ps_recorte_clip: %s → %s", src, dest)
        except Exception as exc:
            logger.exception("ps_recorte_clip failed: %s", src)
            errors.append(f"{src.name}: {exc}")

    return {
        "ok": bool(outputs),
        "processed": len(outputs),
        "outputs": outputs,
        "errors": errors,
        "pipeline": "ps_recorte_clip",
        "source": kind,
        "message": (
            f"Recortados {len(outputs)} TIF desde {kind}/ → recortesPS/."
            if outputs
            else (errors[0] if errors else "Sin archivos recortados.")
        ),
    }
