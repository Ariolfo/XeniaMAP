"""Cloud-Optimized GeoTIFF helpers (Fire map tiles / range reads)."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import rasterio
from rasterio.shutil import copy as rio_copy

logger = logging.getLogger(__name__)


def is_cloud_optimized(path: Path | str) -> bool:
    """True si el archivo ya es COG o GTiff tiled apto para XYZ (overviews si caben)."""
    p = Path(path)
    if not p.is_file():
        return False
    try:
        with rasterio.open(p) as src:
            if str(src.driver or "").upper() == "COG":
                return True
            layout = ""
            try:
                layout = (
                    src.tags().get("LAYOUT") or src.tags(ns="TIFF").get("LAYOUT") or ""
                ).upper()
            except Exception:
                layout = ""
            if layout == "COG":
                return True
            if not bool(getattr(src, "is_tiled", False)):
                return False
            ovs = src.overviews(1) or []
            if ovs:
                return True
            # GDAL no genera overviews en rasters muy pequeños; tiled basta para tiles.
            return max(int(src.width), int(src.height)) <= 512
    except Exception as exc:
        logger.debug("is_cloud_optimized %s: %s", p, exc)
        return False
    return False


def rewrite_as_cog(
    path: Path | str,
    *,
    overview_resampling: str = "AVERAGE",
    compress: str = "DEFLATE",
) -> Path:
    """
    Reescribe ``path`` in-place como COG (overviews internas).
    No-op si ya está cloud-optimized.
    """
    src_path = Path(path)
    if not src_path.is_file():
        raise FileNotFoundError(str(src_path))
    if is_cloud_optimized(src_path):
        return src_path

    tmp = src_path.with_name(src_path.name + ".cogtmp")
    if tmp.exists():
        tmp.unlink(missing_ok=True)

    resampling = (overview_resampling or "AVERAGE").upper()
    try:
        with rasterio.open(src_path) as src:
            # NEAREST para clases discretas; AVERAGE/BILINEAR para índices continuos
            rio_copy(
                src,
                tmp,
                driver="COG",
                compress=compress,
                blocksize=512,
                overview_resampling=resampling,
                resampling=resampling,
            )
        os.replace(tmp, src_path)
        logger.info("COG written: %s (resampling=%s)", src_path.name, resampling)
    except Exception:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise
    return src_path


def ensure_fire_analysis_cogs(*paths: Path | str) -> list[str]:
    """
    dNBR → AVERAGE; severity / máscaras uint8 → NEAREST.
    Devuelve lista de paths procesados.
    """
    done: list[str] = []
    for raw in paths:
        if not raw:
            continue
        p = Path(raw)
        if not p.is_file():
            continue
        name = p.name.lower()
        if "severity" in name or "mask" in name or "class" in name:
            resampling = "NEAREST"
        else:
            resampling = "AVERAGE"
        try:
            rewrite_as_cog(p, overview_resampling=resampling)
            done.append(str(p))
        except Exception as exc:
            logger.warning("ensure COG failed %s: %s", p, exc)
    return done
