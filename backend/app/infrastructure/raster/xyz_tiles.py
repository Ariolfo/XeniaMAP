"""XYZ PNG tiles (WebMercator) para rasters Fire — sin TiTiler externo."""

from __future__ import annotations

import io
import logging
import math
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.warp import reproject, transform_bounds

from app.services.raster_geo import BURN_SEVERITY_CLASS_RGB

logger = logging.getLogger(__name__)

TILE_SIZE = 256
_EMPTY_PNG: bytes | None = None


def empty_tile_png() -> bytes:
    global _EMPTY_PNG
    if _EMPTY_PNG is None:
        img = Image.new("RGBA", (TILE_SIZE, TILE_SIZE), (0, 0, 0, 0))
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        _EMPTY_PNG = buf.getvalue()
    return _EMPTY_PNG


def _tile_bounds_wgs84(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    """Bounds lon/lat (west, south, east, north) del tile XYZ."""
    n = 2.0**z
    west = x / n * 360.0 - 180.0
    east = (x + 1) / n * 360.0 - 180.0
    north = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    south = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
    return west, south, east, north


def render_fire_xyz_tile_png(
    path: Path,
    z: int,
    x: int,
    y: int,
    *,
    mode: str = "rgb",
    severity_class: int | None = None,
    index_cmap: str = "RdYlBu_r",
) -> bytes:
    """
    Renderiza un tile 256×256 PNG RGBA.

    mode:
      - ``rgb``: primeras 3 bandas (display-ready uint8 o stretch simple)
      - ``severity``: paleta discreta 1–7 (+ only_class)
      - ``index``: banda 1 con colormap matplotlib
    """
    west, south, east, north = _tile_bounds_wgs84(z, x, y)
    try:
        with rasterio.open(path) as src:
            try:
                left, bottom, right, top = transform_bounds(
                    "EPSG:4326", src.crs, west, south, east, north, densify_pts=21
                )
            except Exception:
                return empty_tile_png()

            # Fuera de extensión del raster
            if right < src.bounds.left or left > src.bounds.right or top < src.bounds.bottom or bottom > src.bounds.top:
                return empty_tile_png()

            dst_transform = from_bounds(left, bottom, right, top, TILE_SIZE, TILE_SIZE)

            if mode == "severity":
                band = np.zeros((TILE_SIZE, TILE_SIZE), dtype=np.float32)
                reproject(
                    source=rasterio.band(src, 1),
                    destination=band,
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=dst_transform,
                    dst_crs=src.crs,
                    resampling=Resampling.nearest,
                )
                rgba = np.zeros((TILE_SIZE, TILE_SIZE, 4), dtype=np.uint8)
                data = np.rint(band).astype(np.int16)
                classes = (
                    [severity_class]
                    if severity_class is not None
                    else list(BURN_SEVERITY_CLASS_RGB.keys())
                )
                for code in classes:
                    if code not in BURN_SEVERITY_CLASS_RGB:
                        continue
                    r, g, b = BURN_SEVERITY_CLASS_RGB[code]
                    mask = data == code
                    rgba[mask, 0] = r
                    rgba[mask, 1] = g
                    rgba[mask, 2] = b
                    rgba[mask, 3] = 220
                img = Image.fromarray(rgba, mode="RGBA")
            elif mode == "index":
                band = np.full((TILE_SIZE, TILE_SIZE), np.nan, dtype=np.float32)
                reproject(
                    source=rasterio.band(src, 1),
                    destination=band,
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=dst_transform,
                    dst_crs=src.crs,
                    resampling=Resampling.bilinear,
                    src_nodata=src.nodata,
                    dst_nodata=np.nan,
                )
                valid = np.isfinite(band)
                if not valid.any():
                    return empty_tile_png()
                try:
                    import matplotlib.cm as cm
                    import matplotlib.colors as mcolors

                    vmin = float(np.nanpercentile(band[valid], 2))
                    vmax = float(np.nanpercentile(band[valid], 98))
                    if not math.isfinite(vmin) or not math.isfinite(vmax) or vmin >= vmax:
                        vmin, vmax = float(np.nanmin(band)), float(np.nanmax(band))
                    norm = mcolors.Normalize(vmin=vmin, vmax=vmax, clip=True)
                    cmap = cm.get_cmap(index_cmap)
                    colored = cmap(norm(np.where(valid, band, vmin)))
                    rgba = (np.clip(colored, 0, 1) * 255).astype(np.uint8)
                    rgba[~valid, 3] = 0
                    rgba[valid, 3] = 200
                    img = Image.fromarray(rgba, mode="RGBA")
                except Exception:
                    logger.exception("index tile cmap failed")
                    return empty_tile_png()
            else:
                # RGB display-ready or first 3 bands
                count = min(3, src.count)
                dst = np.zeros((count, TILE_SIZE, TILE_SIZE), dtype=np.float32)
                for i in range(count):
                    reproject(
                        source=rasterio.band(src, i + 1),
                        destination=dst[i],
                        src_transform=src.transform,
                        src_crs=src.crs,
                        dst_transform=dst_transform,
                        dst_crs=src.crs,
                        resampling=Resampling.bilinear,
                    )
                if count == 1:
                    g = dst[0]
                    finite = np.isfinite(g)
                    if not finite.any():
                        return empty_tile_png()
                    # uint8 passthrough vs stretch
                    if float(np.nanmax(g)) <= 255 and float(np.nanmin(g)) >= 0:
                        gray = np.clip(g, 0, 255).astype(np.uint8)
                    else:
                        lo, hi = np.nanpercentile(g[finite], [2, 98])
                        if hi <= lo:
                            hi = lo + 1
                        gray = np.clip((g - lo) / (hi - lo) * 255, 0, 255).astype(np.uint8)
                    rgba = np.zeros((TILE_SIZE, TILE_SIZE, 4), dtype=np.uint8)
                    rgba[..., 0] = gray
                    rgba[..., 1] = gray
                    rgba[..., 2] = gray
                    rgba[..., 3] = np.where(finite, 220, 0).astype(np.uint8)
                    img = Image.fromarray(rgba, mode="RGBA")
                else:
                    rgb = np.zeros((TILE_SIZE, TILE_SIZE, 4), dtype=np.uint8)
                    for i in range(3):
                        ch = dst[i] if i < count else dst[0]
                        finite = np.isfinite(ch)
                        if float(np.nanmax(ch)) <= 255 and float(np.nanmin(np.where(finite, ch, 0))) >= 0:
                            rgb[..., i] = np.clip(np.where(finite, ch, 0), 0, 255).astype(np.uint8)
                        else:
                            lo, hi = np.nanpercentile(ch[finite], [2, 98]) if finite.any() else (0, 1)
                            if hi <= lo:
                                hi = lo + 1
                            rgb[..., i] = np.clip((ch - lo) / (hi - lo) * 255, 0, 255).astype(np.uint8)
                    alpha = np.any(np.isfinite(dst[:count]), axis=0)
                    rgb[..., 3] = np.where(alpha, 230, 0).astype(np.uint8)
                    img = Image.fromarray(rgb, mode="RGBA")

            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            return buf.getvalue()
    except Exception:
        logger.exception("fire xyz tile %s z=%s x=%s y=%s", path, z, x, y)
        return empty_tile_png()
