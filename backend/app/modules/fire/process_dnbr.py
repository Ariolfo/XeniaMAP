#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
02_process_dnbr_tolima_RGB_MNDWI_v6.py

Burned-area and burn-severity mapping from Sentinel-2 L2A following the
UN-SPIDER NBR/dNBR methodology, adapted for a cloudy tropical environment and
for reproducible processing of multiple PRE and POST acquisitions.

Workflow
--------
1. Read all partial Sentinel-2 L2A products downloaded by script 01.
2. Read B8A, B11, B12 and SCL at 20 m for burn/water processing, plus
   B04/B03/B02 at 10 m for visual validation.
3. Convert Sentinel-2 DN to surface reflectance using BOA_QUANTIFICATION_VALUE
   and BOA_ADD_OFFSET from MTD_MSIL2A.xml.
4. Apply a FIRE-PERMISSIVE SCL mask to remove clouds/invalid observations.
5. Build a PRE-fire MNDWI composite using B03 and B11:
       MNDWI = (B03 - B11) / (B03 + B11)
   and derive a conservative open-water mask BEFORE the dNBR calculation.
6. Calculate NBR = (B8A - B12) / (B8A + B12) for each acquisition.
7. Build pixel-wise median PRE and POST NBR composites in memory, block by block.
8. Calculate dNBR = median(NBR_pre) - median(NBR_post), then set PRE-fire
   MNDWI water pixels to nodata.
9. Classify dNBR using commonly used USGS / UN-SPIDER severity ranges.
10. Delineate candidate burned areas (dNBR >= 0.15 by default), remove small
    connected patches, calculate polygon-level dNBR metrics, and export them for
    visual/FIRMS validation.
11. Calculate severity-class areas and candidate/reference-threshold areas by
    municipality/AOI feature.
12. Generate PRE and POST 10 m natural-colour COGs (B04/B03/B02) as median
    cloud-screened composites for visual interpretation and validation.

No PRE-NBR, POST-NBR, individual RGB scene composites, or temporary cloud-mask
rasters are retained. Temporary rasters needed to build COGs/polygons are
created in a system temporary directory and deleted automatically.

IMPORTANT: SCL mask philosophy
------------------------------
This workflow intentionally DOES NOT use SCL=6 as the definitive water mask.
SCL remains fire-permissive so that dark/burned surfaces are not discarded
prematurely. Permanent/open water is instead removed spectrally BEFORE dNBR
using a PRE-fire multi-date MNDWI composite (B03/B11). This directly addresses
river/reservoir false positives while keeping the cloud mask permissive.

Default FIRE_PERMISSIVE masked classes:
    0  NO_DATA
    1  SATURATED_OR_DEFECTIVE
    3  CLOUD_SHADOWS
    8  CLOUD_MEDIUM_PROBABILITY
    9  CLOUD_HIGH_PROBABILITY
    11 SNOW_OR_ICE

SCL=2 and SCL=6 are intentionally preserved. SCL=10 is also preserved in the
default fire-permissive mode because open fires can occasionally be classified
as cirrus. A stricter or more permissive preset can be selected in USER
CONFIGURATION. Multi-date median compositing and the minimum valid observation
requirement provide additional robustness against occasional contamination.

Dependencies
------------
    numpy, pandas, geopandas, shapely, rasterio
"""

from __future__ import annotations

import json
import math
import re
import sys
import tempfile
import time
import warnings
import xml.etree.ElementTree as ET
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.enums import ColorInterp, Resampling
from rasterio.errors import WindowError
from rasterio.features import geometry_mask, geometry_window, shapes
from rasterio.shutil import copy as rio_copy
from rasterio.transform import from_origin
from rasterio.vrt import WarpedVRT
from shapely.geometry import shape


# =============================================================================
# USER CONFIGURATION
# =============================================================================

SCRIPT_DIR = Path(__file__).resolve().parent

# Defaults (overridden by run_dnbr_pipeline for each FireOrder).
AOI_PATH = SCRIPT_DIR / "aoi" / "Incendios_Tolima.shp"
S2_ROOT = SCRIPT_DIR / "s2_tolima"
PRE_DIR = S2_ROOT / "pre"
POST_DIR = S2_ROOT / "post"
OUTPUT_DIR = SCRIPT_DIR / "tolima_fire_results"
OUTPUT_PREFIX = "Fire"

# Output pixel size for dNBR/severity. B8A, B12 and SCL are native 20 m.
RESOLUTION_M = 20.0

# RGB validation COGs use native B02/B03/B04 resolution. The PRE and POST
# products use the same fixed reflectance stretch so visual differences are
# comparable rather than independently auto-stretched. Valid pixels are scaled
# to 1..255; 0 is reserved for nodata/outside AOI.
SCRIPT_VERSION = "2026-09-03-rgb-mndwi-v6"
WRITE_RGB_COGS = True
RGB_RESOLUTION_M = 10.0
RGB_REFLECTANCE_MIN = 0.00
RGB_REFLECTANCE_MAX = 0.30
RGB_GAMMA = 1.0
RGB_NODATA = 0

# Cloud/quality mask preset. FIRE_PERMISSIVE is the recommended default here:
#   - retain 2 = cast/dark shadows (important over dark burned surfaces)
#   - retain 6 = water
#   - retain 7 = unclassified
#   - retain 10 = thin cirrus, because Sentinel-2 documentation notes that open
#     fires can occasionally be misclassified as cirrus
#   - mask 3 = cloud shadows, because they can create strong false dNBR changes
#
# Available presets:
#   "fire_permissive" -> {0,1,3,8,9,11}
#   "minimal"         -> {0,1,8,9,11}
#   "strict"          -> {0,1,2,3,8,9,10,11}
SCL_MASK_MODE = "fire_permissive"
SCL_MASK_PRESETS = {
    "fire_permissive": {0, 1, 3, 8, 9, 11},
    "minimal": {0, 1, 8, 9, 11},
    "strict": {0, 1, 2, 3, 8, 9, 10, 11},
}
MASKED_SCL_CLASSES = SCL_MASK_PRESETS[SCL_MASK_MODE]

# Drop products with almost no usable AOI pixels. The threshold is intentionally
# low because a partly clear image can still contribute useful pixels to the
# multi-date median composite.
MIN_SCENE_USABLE_PERCENT = 2.0

# Require this many valid observations independently in PRE and POST for a final
# dNBR pixel. Two observations is a useful safeguard against one bad acquisition.
MIN_VALID_OBSERVATIONS = 2

# ---------------------------------------------------------------------------
# PRE-FIRE MNDWI WATER MASK
# ---------------------------------------------------------------------------
# Open water is removed BEFORE dNBR using the pre-fire period only:
#     MNDWI = (B03 - B11) / (B03 + B11)
#
# A threshold of 0.0 is a common starting point for MNDWI water extraction.
# This workflow defaults to 0.10 to be deliberately conservative (avoid masking
# moist soil / non-water), then dilates the detected water by one 20 m pixel to
# cover mixed edge pixels along rivers and reservoirs.
WRITE_PRE_MNDWI = True
WRITE_WATER_MASK = True
MNDWI_WATER_THRESHOLD = 0.10
MNDWI_MIN_VALID_OBSERVATIONS = 2
WATER_MASK_DILATION_PIXELS = 1
MNDWI_NODATA = -9999.0
WATER_MASK_NODATA = 255

# Candidate delineation is intentionally more conservative than the severity
# classification. The standard severity raster still uses 0.10 as the lower
# boundary of "low severity", but automatic polygons start at 0.15 to reduce
# false positives from agricultural/fenological change and other non-fire change.
CANDIDATE_DNBR_THRESHOLD = 0.15

# A second threshold is stored as a useful spectral-evidence reference. It is
# NOT used to delete candidates: script 03 combines polygon dNBR metrics with
# independent NASA FIRMS/VIIRS active-fire detections.
SPECTRAL_REFERENCE_THRESHOLD = 0.20
STRONG_SPECTRAL_THRESHOLD = 0.27

# Remove connected candidate patches smaller than this area.
MIN_CANDIDATE_PATCH_HA = 2.0

# Municipality/department fields in the supplied Incendios_Tolima layer.
# The AOI is dissolved by these fields, so the workflow is also robust if a
# municipality is represented by several polygon records in a future layer.
MUNICIPALITY_FIELD: Optional[str] = "MpNombre"
DEPARTMENT_FIELD: Optional[str] = "Depto"

# Final outputs. Intermediate PRE/POST NBR composites are never written.
WRITE_DNBR = True
WRITE_SEVERITY = True
WRITE_BURNED_POLYGONS = True
WRITE_STATISTICS = True

# Nodata values.
DNBR_NODATA = -9999.0
SEVERITY_NODATA = 255

# dNBR severity classes (NBR expressed as -1..1, not multiplied by 1000):
# 1 high post-fire regrowth
# 2 low post-fire regrowth
# 3 unburned
# 4 low severity
# 5 moderate-low severity
# 6 moderate-high severity
# 7 high severity
SEVERITY_LABELS = {
    1: "high_regrowth",
    2: "low_regrowth",
    3: "unburned",
    4: "low_severity",
    5: "moderate_low_severity",
    6: "moderate_high_severity",
    7: "high_severity",
}


# =============================================================================
# DATA STRUCTURES / HELPERS
# =============================================================================

@dataclass
class Scene:
    period: str
    product_dir: Path
    product_name: str
    sensing_datetime: str
    mgrs_tile: str
    b02_path: Path
    b03_path: Path
    b04_path: Path
    b8a_path: Path
    b11_path: Path
    b12_path: Path
    scl_path: Path
    metadata_path: Path
    quantification: float
    offset_b02: float
    offset_b03: float
    offset_b04: float
    offset_b8a: float
    offset_b11: float
    offset_b12: float
    usable_percent: Optional[float] = None


def local_tag(tag: str) -> str:
    return tag.split("}")[-1]


def sensing_datetime_from_name(name: str) -> str:
    match = re.search(r"_MSIL2A_(\d{8}T\d{6})_", name)
    return match.group(1) if match else "UNKNOWN"


def mgrs_tile_from_name(name: str) -> str:
    match = re.search(r"_T(\d{2}[A-Z]{3})_", name)
    return match.group(1) if match else "UNKNOWN"


def find_single(product_dir: Path, pattern: str) -> Path:
    matches = sorted(product_dir.rglob(pattern))
    if not matches:
        raise FileNotFoundError(f"Missing {pattern} in {product_dir}")
    if len(matches) > 1:
        raise RuntimeError(
            f"Expected one {pattern} in {product_dir}, found {len(matches)}."
        )
    return matches[0]


def read_l2a_radiometry(metadata_path: Path) -> Tuple[float, Dict[str, float]]:
    """
    Parse BOA quantification and BOA additive offsets from MTD_MSIL2A.xml.

    Sentinel-2 band_id mapping used by product metadata (0-based):
        band_id 1  -> B02
        band_id 2  -> B03
        band_id 3  -> B04
        band_id 8  -> B8A
        band_id 11 -> B11
        band_id 12 -> B12

    Older products may not contain BOA_ADD_OFFSET. In that case offsets are 0.
    """
    tree = ET.parse(metadata_path)
    root = tree.getroot()

    quantification = 10000.0
    offsets: Dict[str, float] = {}

    for elem in root.iter():
        tag = local_tag(elem.tag)

        if tag == "BOA_QUANTIFICATION_VALUE" and elem.text:
            quantification = float(elem.text)

        elif tag == "BOA_ADD_OFFSET":
            band_id = elem.attrib.get("band_id")
            if band_id is not None and elem.text:
                offsets[band_id] = float(elem.text)

    return quantification, offsets


def discover_scenes(period: str, period_dir: Path) -> List[Scene]:
    if not period_dir.exists():
        raise FileNotFoundError(
            f"Input directory does not exist: {period_dir}\n"
            "Run 01_download_s2_tolima.py first."
        )

    product_dirs = sorted(p for p in period_dir.glob("*.SAFE") if p.is_dir())
    if not product_dirs:
        raise RuntimeError(f"No .SAFE directories found in {period_dir}")

    scenes: List[Scene] = []
    for product_dir in product_dirs:
        metadata = product_dir / "MTD_MSIL2A.xml"
        if not metadata.exists():
            raise FileNotFoundError(f"Missing MTD_MSIL2A.xml in {product_dir}")

        b02 = find_single(product_dir, "*_B02_10m.jp2")
        b03 = find_single(product_dir, "*_B03_10m.jp2")
        b04 = find_single(product_dir, "*_B04_10m.jp2")
        b8a = find_single(product_dir, "*_B8A_20m.jp2")
        b11 = find_single(product_dir, "*_B11_20m.jp2")
        b12 = find_single(product_dir, "*_B12_20m.jp2")
        scl = find_single(product_dir, "*_SCL_20m.jp2")

        quantification, offsets = read_l2a_radiometry(metadata)

        scenes.append(
            Scene(
                period=period,
                product_dir=product_dir,
                product_name=product_dir.name,
                sensing_datetime=sensing_datetime_from_name(product_dir.name),
                mgrs_tile=mgrs_tile_from_name(product_dir.name),
                b02_path=b02,
                b03_path=b03,
                b04_path=b04,
                b8a_path=b8a,
                b11_path=b11,
                b12_path=b12,
                scl_path=scl,
                metadata_path=metadata,
                quantification=quantification,
                offset_b02=offsets.get("1", 0.0),
                offset_b03=offsets.get("2", 0.0),
                offset_b04=offsets.get("3", 0.0),
                offset_b8a=offsets.get("8", 0.0),
                offset_b11=offsets.get("11", 0.0),
                offset_b12=offsets.get("12", 0.0),
            )
        )

    return scenes


def load_aoi(aoi_path: Path) -> gpd.GeoDataFrame:
    if not aoi_path.exists():
        raise FileNotFoundError(f"AOI not found: {aoi_path}")

    gdf = gpd.read_file(aoi_path)
    if gdf.empty:
        raise RuntimeError("AOI contains no features.")
    if gdf.crs is None:
        raise RuntimeError("AOI has no CRS. Define it before running.")

    gdf = gdf[gdf.geometry.notna()].copy()
    gdf = gdf[~gdf.geometry.is_empty].copy()
    if gdf.empty:
        raise RuntimeError("AOI contains no non-empty geometries.")

    invalid = ~gdf.geometry.is_valid
    if invalid.any():
        gdf.loc[invalid, "geometry"] = gdf.loc[invalid, "geometry"].buffer(0)

    if MUNICIPALITY_FIELD:
        if MUNICIPALITY_FIELD not in gdf.columns:
            raise KeyError(
                f"MUNICIPALITY_FIELD='{MUNICIPALITY_FIELD}' not found. "
                f"Available fields: {list(gdf.columns)}"
            )

        group_fields = [MUNICIPALITY_FIELD]
        if DEPARTMENT_FIELD:
            if DEPARTMENT_FIELD not in gdf.columns:
                raise KeyError(
                    f"DEPARTMENT_FIELD='{DEPARTMENT_FIELD}' not found. "
                    f"Available fields: {list(gdf.columns)}"
                )
            group_fields.insert(0, DEPARTMENT_FIELD)

        gdf = (
            gdf[group_fields + [gdf.geometry.name]]
            .dissolve(by=group_fields, as_index=False)
            .reset_index(drop=True)
        )

    return gdf


def choose_utm_crs(aoi: gpd.GeoDataFrame) -> str:
    """Choose a local UTM CRS from AOI centroid. Tolima resolves to UTM 18N."""
    aoi4326 = aoi.to_crs(4326)
    geom = aoi4326.geometry.unary_union
    centroid = geom.centroid
    lon, lat = centroid.x, centroid.y
    zone = int(math.floor((lon + 180.0) / 6.0) + 1)
    epsg = (32600 if lat >= 0 else 32700) + zone
    return f"EPSG:{epsg}"


def build_target_grid(
    aoi_projected: gpd.GeoDataFrame,
    resolution: float,
) -> Tuple[object, int, int, Tuple[float, float, float, float]]:
    minx, miny, maxx, maxy = aoi_projected.total_bounds

    left = math.floor(minx / resolution) * resolution
    bottom = math.floor(miny / resolution) * resolution
    right = math.ceil(maxx / resolution) * resolution
    top = math.ceil(maxy / resolution) * resolution

    width = int(round((right - left) / resolution))
    height = int(round((top - bottom) / resolution))
    transform = from_origin(left, top, resolution, resolution)

    return transform, width, height, (left, bottom, right, top)


def infer_name_field(gdf: gpd.GeoDataFrame) -> Optional[str]:
    if MUNICIPALITY_FIELD:
        if MUNICIPALITY_FIELD not in gdf.columns:
            raise KeyError(
                f"MUNICIPALITY_FIELD='{MUNICIPALITY_FIELD}' not found. "
                f"Available fields: {list(gdf.columns)}"
            )
        return MUNICIPALITY_FIELD

    preferred = [
        "MpNombre",
        "MPIO_CNMBR",
        "MUNICIPIO",
        "Municipio",
        "municipio",
        "NOM_MPIO",
        "NOMBRE",
        "Nombre",
        "NAME_2",
        "NAME",
        "name",
    ]
    for field in preferred:
        if field in gdf.columns:
            return field

    # Fallback to first textual non-geometry field.
    for field in gdf.columns:
        if field == gdf.geometry.name:
            continue
        if pd.api.types.is_string_dtype(gdf[field]) or gdf[field].dtype == object:
            return field

    return None


def infer_department_field(gdf: gpd.GeoDataFrame) -> Optional[str]:
    if DEPARTMENT_FIELD:
        if DEPARTMENT_FIELD not in gdf.columns:
            raise KeyError(
                f"DEPARTMENT_FIELD='{DEPARTMENT_FIELD}' not found. "
                f"Available fields: {list(gdf.columns)}"
            )
        return DEPARTMENT_FIELD

    for field in ("Depto", "DEPARTAMENTO", "Departamento", "department"):
        if field in gdf.columns:
            return field
    return None


# =============================================================================
# SCENE QUALITY SCREENING
# =============================================================================

def scene_usable_percent(scene: Scene, aoi: gpd.GeoDataFrame) -> float:
    """Estimate usable SCL percentage over the part of the AOI covered by scene."""
    with rasterio.open(scene.scl_path) as src:
        aoi_src = aoi.to_crs(src.crs)
        geoms = [geom for geom in aoi_src.geometry if geom is not None and not geom.is_empty]
        if not geoms:
            return 0.0

        try:
            window = geometry_window(src, geoms, pad_x=0, pad_y=0)
        except WindowError:
            return 0.0

        scl = src.read(1, window=window)
        win_transform = src.window_transform(window)
        inside = geometry_mask(
            geoms,
            out_shape=scl.shape,
            transform=win_transform,
            invert=True,
        )

        n_inside = int(inside.sum())
        if n_inside == 0:
            return 0.0

        bad = np.isin(scl, list(MASKED_SCL_CLASSES))
        usable = inside & (~bad)
        return float(usable.sum() / n_inside * 100.0)


def screen_scenes(scenes: Sequence[Scene], aoi: gpd.GeoDataFrame) -> List[Scene]:
    kept: List[Scene] = []

    print("\n[QA] Scene usability from SCL inside AOI")
    print(f"[QA] Masked SCL classes: {sorted(MASKED_SCL_CLASSES)}")

    for idx, scene in enumerate(scenes, start=1):
        pct = scene_usable_percent(scene, aoi)
        scene.usable_percent = pct
        status = "KEEP" if pct >= MIN_SCENE_USABLE_PERCENT else "DROP"
        print(
            f"[QA] {idx:02d}/{len(scenes):02d} {scene.period.upper()} "
            f"{scene.sensing_datetime} {scene.mgrs_tile}: {pct:5.1f}% usable -> {status}"
        )
        if pct >= MIN_SCENE_USABLE_PERCENT:
            kept.append(scene)

    if not kept:
        raise RuntimeError(
            f"All {scenes[0].period.upper()} scenes were rejected by "
            f"MIN_SCENE_USABLE_PERCENT={MIN_SCENE_USABLE_PERCENT}."
        )

    return kept



# =============================================================================
# PRE-FIRE MNDWI WATER MASK
# =============================================================================

def open_mndwi_scene_vrts(
    stack: ExitStack,
    scenes: Sequence[Scene],
    target_crs,
    transform,
    width: int,
    height: int,
):
    """Open B03, B11 and SCL aligned to the common 20 m analysis grid."""
    opened = []
    for scene in scenes:
        green_src = stack.enter_context(rasterio.open(scene.b03_path))
        swir1_src = stack.enter_context(rasterio.open(scene.b11_path))
        scl_src = stack.enter_context(rasterio.open(scene.scl_path))

        green_vrt = stack.enter_context(
            WarpedVRT(
                green_src,
                crs=target_crs,
                transform=transform,
                width=width,
                height=height,
                resampling=Resampling.bilinear,
                src_nodata=0,
                nodata=0,
            )
        )
        swir1_vrt = stack.enter_context(
            WarpedVRT(
                swir1_src,
                crs=target_crs,
                transform=transform,
                width=width,
                height=height,
                resampling=Resampling.bilinear,
                src_nodata=0,
                nodata=0,
            )
        )
        scl_vrt = stack.enter_context(
            WarpedVRT(
                scl_src,
                crs=target_crs,
                transform=transform,
                width=width,
                height=height,
                resampling=Resampling.nearest,
                src_nodata=0,
                nodata=0,
            )
        )
        opened.append((scene, green_vrt, swir1_vrt, scl_vrt))
    return opened


def calculate_scene_mndwi(
    scene: Scene,
    green_vrt,
    swir1_vrt,
    scl_vrt,
    window,
) -> np.ndarray:
    """Calculate cloud-screened MNDWI surface reflectance for one acquisition."""
    green_dn = green_vrt.read(1, window=window).astype("float32")
    swir1_dn = swir1_vrt.read(1, window=window).astype("float32")
    scl = scl_vrt.read(1, window=window)

    valid_dn = (green_dn > 0) & (swir1_dn > 0)
    green = np.full(green_dn.shape, np.nan, dtype="float32")
    swir1 = np.full(swir1_dn.shape, np.nan, dtype="float32")

    green[valid_dn] = (
        green_dn[valid_dn] + scene.offset_b03
    ) / scene.quantification
    swir1[valid_dn] = (
        swir1_dn[valid_dn] + scene.offset_b11
    ) / scene.quantification

    # Same cloud/quality philosophy as the burn workflow. SCL=6 is NOT required
    # here; water is identified spectrally by MNDWI, not by the SCL label.
    bad_scl = np.isin(scl, list(MASKED_SCL_CLASSES))
    denominator = green + swir1
    valid = (
        valid_dn
        & (~bad_scl)
        & np.isfinite(denominator)
        & (np.abs(denominator) > 1e-6)
    )

    mndwi = np.full(green.shape, np.nan, dtype="float32")
    mndwi[valid] = (green[valid] - swir1[valid]) / denominator[valid]
    np.clip(mndwi, -1.0, 1.0, out=mndwi)
    return mndwi


def median_mndwi_for_window(opened_scenes, window) -> Tuple[np.ndarray, np.ndarray]:
    arrays = []
    for scene, green_vrt, swir1_vrt, scl_vrt in opened_scenes:
        arrays.append(
            calculate_scene_mndwi(scene, green_vrt, swir1_vrt, scl_vrt, window)
        )
    cube = np.stack(arrays, axis=0)
    counts = np.sum(np.isfinite(cube), axis=0).astype("uint16")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        median = np.nanmedian(cube, axis=0).astype("float32")
    median[counts < MNDWI_MIN_VALID_OBSERVATIONS] = np.nan
    return median, counts


def dilate_binary_mask(mask: np.ndarray, radius: int) -> np.ndarray:
    """Binary square dilation implemented with NumPy; avoids an extra SciPy dependency."""
    if radius <= 0:
        return mask.astype(bool, copy=True)
    mask = mask.astype(bool, copy=False)
    padded = np.pad(mask, radius, mode="constant", constant_values=False)
    out = np.zeros(mask.shape, dtype=bool)
    h, w = mask.shape
    for dy in range(2 * radius + 1):
        for dx in range(2 * radius + 1):
            out |= padded[dy:dy + h, dx:dx + w]
    return out


def create_pre_mndwi_water_mask(
    pre_scenes: Sequence[Scene],
    aoi_projected: gpd.GeoDataFrame,
    target_crs,
    transform,
    width: int,
    height: int,
    mndwi_path: Path,
    water_mask_path: Path,
) -> None:
    """
    Create a PRE-fire median MNDWI raster and an open-water mask.

    The first pass writes the spectral water mask using MNDWI >= threshold.
    The second pass dilates it with a halo so dilation is correct across raster
    block boundaries. Water is represented by 1; land by 0; outside AOI/nodata
    by WATER_MASK_NODATA.
    """
    geoms = [
        geom for geom in aoi_projected.geometry
        if geom is not None and not geom.is_empty
    ]
    aoi_inside = geometry_mask(
        geoms,
        out_shape=(height, width),
        transform=transform,
        invert=True,
    )

    base_profile = {
        "driver": "GTiff",
        "width": width,
        "height": height,
        "count": 1,
        "crs": target_crs,
        "transform": transform,
        "tiled": True,
        "blockxsize": 512,
        "blockysize": 512,
        "compress": "deflate",
        "BIGTIFF": "IF_SAFER",
    }

    mndwi_profile = base_profile | {
        "dtype": "float32",
        "nodata": MNDWI_NODATA,
        "predictor": 2,
    }
    raw_mask_profile = base_profile | {
        "dtype": "uint8",
        "nodata": WATER_MASK_NODATA,
        "predictor": 1,
    }

    print("\n[WATER] Building PRE-fire median MNDWI water mask")
    print("[WATER] Formula: (B03 - B11) / (B03 + B11)")
    print(f"[WATER] PRE scenes used: {len(pre_scenes)}")
    print(f"[WATER] Threshold: MNDWI >= {MNDWI_WATER_THRESHOLD:.2f}")
    print(f"[WATER] Minimum valid PRE observations: {MNDWI_MIN_VALID_OBSERVATIONS}")
    print(f"[WATER] Dilation: {WATER_MASK_DILATION_PIXELS} pixel(s) at {RESOLUTION_M:.0f} m")

    with tempfile.TemporaryDirectory(prefix="tolima_mndwi_water_") as tmp_dir:
        raw_mask_path = Path(tmp_dir) / "water_mask_raw.tif"

        with ExitStack() as stack:
            opened = open_mndwi_scene_vrts(
                stack, pre_scenes, target_crs, transform, width, height
            )
            mndwi_dst = stack.enter_context(
                rasterio.open(mndwi_path, "w", **mndwi_profile)
            )
            raw_dst = stack.enter_context(
                rasterio.open(raw_mask_path, "w", **raw_mask_profile)
            )

            windows = list(mndwi_dst.block_windows(1))
            total = len(windows)
            for index, (_, window) in enumerate(windows, start=1):
                mndwi, _counts = median_mndwi_for_window(opened, window)

                row0 = int(window.row_off)
                row1 = row0 + int(window.height)
                col0 = int(window.col_off)
                col1 = col0 + int(window.width)
                inside = aoi_inside[row0:row1, col0:col1]

                valid = inside & np.isfinite(mndwi)
                water = valid & (mndwi >= MNDWI_WATER_THRESHOLD)

                mndwi_write = np.where(valid, mndwi, MNDWI_NODATA).astype("float32")
                mask_write = np.full(mndwi.shape, WATER_MASK_NODATA, dtype="uint8")
                mask_write[valid] = 0
                mask_write[water] = 1

                mndwi_dst.write(mndwi_write, 1, window=window)
                raw_dst.write(mask_write, 1, window=window)

                if index == 1 or index % 20 == 0 or index == total:
                    print(f"[WATER] MNDWI blocks: {index}/{total}")

        # Dilation with a halo prevents seams at internal GeoTIFF block borders.
        with rasterio.open(raw_mask_path) as src:
            out_profile = src.profile.copy()
            with rasterio.open(water_mask_path, "w", **out_profile) as dst:
                windows = list(src.block_windows(1))
                total = len(windows)
                radius = max(0, int(WATER_MASK_DILATION_PIXELS))

                for index, (_, window) in enumerate(windows, start=1):
                    r0 = int(window.row_off)
                    c0 = int(window.col_off)
                    r1 = r0 + int(window.height)
                    c1 = c0 + int(window.width)

                    hr0 = max(0, r0 - radius)
                    hc0 = max(0, c0 - radius)
                    hr1 = min(src.height, r1 + radius)
                    hc1 = min(src.width, c1 + radius)

                    halo_window = rasterio.windows.Window(
                        hc0, hr0, hc1 - hc0, hr1 - hr0
                    )
                    raw = src.read(1, window=halo_window)
                    raw_water = raw == 1
                    dilated = dilate_binary_mask(raw_water, radius)

                    rr0 = r0 - hr0
                    cc0 = c0 - hc0
                    rr1 = rr0 + int(window.height)
                    cc1 = cc0 + int(window.width)
                    core = dilated[rr0:rr1, cc0:cc1]

                    original_core = src.read(1, window=window)
                    out = original_core.copy()
                    valid_core = original_core != WATER_MASK_NODATA
                    out[valid_core] = 0
                    out[valid_core & core] = 1
                    dst.write(out.astype("uint8"), 1, window=window)

                    if index == 1 or index % 20 == 0 or index == total:
                        print(f"[WATER] Dilation blocks: {index}/{total}")

    # Report water area.
    with rasterio.open(water_mask_path) as src:
        pixel_area_ha = abs(src.transform.a * src.transform.e) / 10000.0
        water_pixels = 0
        for _, window in src.block_windows(1):
            arr = src.read(1, window=window)
            water_pixels += int(np.sum(arr == 1))
        print(f"[WATER] Masked PRE-fire open-water area: {water_pixels * pixel_area_ha:.2f} ha")
        print(f"[WATER] MNDWI output: {mndwi_path}")
        print(f"[WATER] Water mask output: {water_mask_path}")


# =============================================================================
# NBR / dNBR PROCESSING
# =============================================================================

def open_scene_vrts(
    stack: ExitStack,
    scenes: Sequence[Scene],
    target_crs,
    transform,
    width: int,
    height: int,
):
    opened = []

    for scene in scenes:
        nir_src = stack.enter_context(rasterio.open(scene.b8a_path))
        swir_src = stack.enter_context(rasterio.open(scene.b12_path))
        scl_src = stack.enter_context(rasterio.open(scene.scl_path))

        nir_vrt = stack.enter_context(
            WarpedVRT(
                nir_src,
                crs=target_crs,
                transform=transform,
                width=width,
                height=height,
                resampling=Resampling.bilinear,
                src_nodata=0,
                nodata=0,
            )
        )
        swir_vrt = stack.enter_context(
            WarpedVRT(
                swir_src,
                crs=target_crs,
                transform=transform,
                width=width,
                height=height,
                resampling=Resampling.bilinear,
                src_nodata=0,
                nodata=0,
            )
        )
        scl_vrt = stack.enter_context(
            WarpedVRT(
                scl_src,
                crs=target_crs,
                transform=transform,
                width=width,
                height=height,
                resampling=Resampling.nearest,
                src_nodata=0,
                nodata=0,
            )
        )

        opened.append((scene, nir_vrt, swir_vrt, scl_vrt))

    return opened


def calculate_scene_nbr(scene: Scene, nir_vrt, swir_vrt, scl_vrt, window) -> np.ndarray:
    nir_dn = nir_vrt.read(1, window=window).astype("float32")
    swir_dn = swir_vrt.read(1, window=window).astype("float32")
    scl = scl_vrt.read(1, window=window)

    # DN=0 is Sentinel-2 NO_DATA and must not receive the radiometric offset.
    valid_dn = (nir_dn > 0) & (swir_dn > 0)

    nir = np.full(nir_dn.shape, np.nan, dtype="float32")
    swir = np.full(swir_dn.shape, np.nan, dtype="float32")

    nir[valid_dn] = (
        nir_dn[valid_dn] + scene.offset_b8a
    ) / scene.quantification
    swir[valid_dn] = (
        swir_dn[valid_dn] + scene.offset_b12
    ) / scene.quantification

    bad_scl = np.isin(scl, list(MASKED_SCL_CLASSES))
    denominator = nir + swir
    valid = valid_dn & (~bad_scl) & np.isfinite(denominator) & (np.abs(denominator) > 1e-6)

    nbr = np.full(nir.shape, np.nan, dtype="float32")
    nbr[valid] = (nir[valid] - swir[valid]) / denominator[valid]

    # Extremely low/negative reflectances can numerically push a normalized
    # difference outside its usual physical range. Clip rather than deleting
    # dark pixels, which are important for this fire application.
    np.clip(nbr, -1.0, 1.0, out=nbr)
    return nbr


def median_nbr_for_window(opened_scenes, window) -> Tuple[np.ndarray, np.ndarray]:
    stack = []
    for scene, nir_vrt, swir_vrt, scl_vrt in opened_scenes:
        stack.append(calculate_scene_nbr(scene, nir_vrt, swir_vrt, scl_vrt, window))

    cube = np.stack(stack, axis=0)
    counts = np.sum(np.isfinite(cube), axis=0).astype("uint16")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        median = np.nanmedian(cube, axis=0).astype("float32")

    median[counts < MIN_VALID_OBSERVATIONS] = np.nan
    return median, counts


def classify_dnbr(dnbr: np.ndarray) -> np.ndarray:
    out = np.full(dnbr.shape, SEVERITY_NODATA, dtype="uint8")
    valid = np.isfinite(dnbr)

    out[valid & (dnbr < -0.25)] = 1
    out[valid & (dnbr >= -0.25) & (dnbr < -0.10)] = 2
    out[valid & (dnbr >= -0.10) & (dnbr < 0.10)] = 3
    out[valid & (dnbr >= 0.10) & (dnbr < 0.27)] = 4
    out[valid & (dnbr >= 0.27) & (dnbr < 0.44)] = 5
    out[valid & (dnbr >= 0.44) & (dnbr < 0.66)] = 6
    out[valid & (dnbr >= 0.66)] = 7

    return out


def process_dnbr(
    pre_scenes: Sequence[Scene],
    post_scenes: Sequence[Scene],
    aoi_projected: gpd.GeoDataFrame,
    target_crs,
    transform,
    width: int,
    height: int,
    dnbr_path: Path,
    severity_path: Path,
    water_mask_path: Path,
) -> None:
    geoms = [geom for geom in aoi_projected.geometry if geom is not None and not geom.is_empty]
    aoi_inside = geometry_mask(
        geoms,
        out_shape=(height, width),
        transform=transform,
        invert=True,
    )

    base_profile = {
        "driver": "GTiff",
        "width": width,
        "height": height,
        "count": 1,
        "crs": target_crs,
        "transform": transform,
        "tiled": True,
        "blockxsize": 512,
        "blockysize": 512,
        "compress": "deflate",
        "BIGTIFF": "IF_SAFER",
    }

    dnbr_profile = base_profile | {
        "dtype": "float32",
        "nodata": DNBR_NODATA,
        "predictor": 2,
    }
    severity_profile = base_profile | {
        "dtype": "uint8",
        "nodata": SEVERITY_NODATA,
    }

    with ExitStack() as stack:
        pre_opened = open_scene_vrts(
            stack, pre_scenes, target_crs, transform, width, height
        )
        post_opened = open_scene_vrts(
            stack, post_scenes, target_crs, transform, width, height
        )

        dnbr_dst = stack.enter_context(rasterio.open(dnbr_path, "w", **dnbr_profile))
        severity_dst = stack.enter_context(
            rasterio.open(severity_path, "w", **severity_profile)
        )
        water_src = stack.enter_context(rasterio.open(water_mask_path))

        windows = list(dnbr_dst.block_windows(1))
        total = len(windows)

        print("\n[PROCESS] Calculating multi-date median NBR and dNBR")
        print(f"[PROCESS] PRE scenes used:  {len(pre_scenes)}")
        print(f"[PROCESS] POST scenes used: {len(post_scenes)}")
        print(f"[PROCESS] Minimum valid observations per period: {MIN_VALID_OBSERVATIONS}")

        for index, (_, window) in enumerate(windows, start=1):
            pre_nbr, _ = median_nbr_for_window(pre_opened, window)
            post_nbr, _ = median_nbr_for_window(post_opened, window)

            dnbr = pre_nbr - post_nbr

            row0 = int(window.row_off)
            row1 = row0 + int(window.height)
            col0 = int(window.col_off)
            col1 = col0 + int(window.width)
            inside = aoi_inside[row0:row1, col0:col1]

            dnbr[~inside] = np.nan

            # PRE-fire open water is removed before severity/candidate mapping.
            # This prevents rivers/reservoirs from becoming high-confidence
            # dNBR false positives when their water level/turbidity changes.
            water = water_src.read(1, window=window) == 1
            dnbr[water] = np.nan

            severity = classify_dnbr(dnbr)

            dnbr_write = np.where(np.isfinite(dnbr), dnbr, DNBR_NODATA).astype("float32")
            dnbr_dst.write(dnbr_write, 1, window=window)
            severity_dst.write(severity, 1, window=window)

            if index == 1 or index % 20 == 0 or index == total:
                print(f"[PROCESS] Blocks: {index}/{total}")


# =============================================================================
# RGB VALIDATION COGS
# =============================================================================

def open_rgb_scene_vrts(
    stack: ExitStack,
    scenes: Sequence[Scene],
    target_crs,
    transform,
    width: int,
    height: int,
):
    """Open B04/B03/B02 + SCL warped to the common 10 m RGB grid."""
    opened = []

    for scene in scenes:
        red_src = stack.enter_context(rasterio.open(scene.b04_path))
        green_src = stack.enter_context(rasterio.open(scene.b03_path))
        blue_src = stack.enter_context(rasterio.open(scene.b02_path))
        scl_src = stack.enter_context(rasterio.open(scene.scl_path))

        def reflectance_vrt(src):
            return stack.enter_context(
                WarpedVRT(
                    src,
                    crs=target_crs,
                    transform=transform,
                    width=width,
                    height=height,
                    resampling=Resampling.bilinear,
                    src_nodata=0,
                    nodata=0,
                )
            )

        red_vrt = reflectance_vrt(red_src)
        green_vrt = reflectance_vrt(green_src)
        blue_vrt = reflectance_vrt(blue_src)
        scl_vrt = stack.enter_context(
            WarpedVRT(
                scl_src,
                crs=target_crs,
                transform=transform,
                width=width,
                height=height,
                resampling=Resampling.nearest,
                src_nodata=0,
                nodata=0,
            )
        )

        opened.append((scene, red_vrt, green_vrt, blue_vrt, scl_vrt))

    return opened


def calculate_scene_rgb_reflectance(
    scene: Scene,
    red_vrt,
    green_vrt,
    blue_vrt,
    scl_vrt,
    window,
) -> np.ndarray:
    """Return a 3 x H x W natural-colour surface-reflectance array."""
    red_dn = red_vrt.read(1, window=window).astype("float32")
    green_dn = green_vrt.read(1, window=window).astype("float32")
    blue_dn = blue_vrt.read(1, window=window).astype("float32")
    scl = scl_vrt.read(1, window=window)

    # Use one common validity mask for the three channels so colour is never
    # assembled from different validity states.
    valid_dn = (red_dn > 0) & (green_dn > 0) & (blue_dn > 0)
    bad_scl = np.isin(scl, list(MASKED_SCL_CLASSES))
    valid = valid_dn & (~bad_scl)

    rgb = np.full((3, red_dn.shape[0], red_dn.shape[1]), np.nan, dtype="float32")
    if np.any(valid):
        rgb[0, valid] = (red_dn[valid] + scene.offset_b04) / scene.quantification
        rgb[1, valid] = (green_dn[valid] + scene.offset_b03) / scene.quantification
        rgb[2, valid] = (blue_dn[valid] + scene.offset_b02) / scene.quantification

    return rgb


def median_rgb_for_window(opened_scenes, window) -> Tuple[np.ndarray, np.ndarray]:
    """Pixel-wise median RGB reflectance and count of valid acquisitions."""
    scene_arrays = []
    for scene, red_vrt, green_vrt, blue_vrt, scl_vrt in opened_scenes:
        scene_arrays.append(
            calculate_scene_rgb_reflectance(
                scene, red_vrt, green_vrt, blue_vrt, scl_vrt, window
            )
        )

    cube = np.stack(scene_arrays, axis=0)  # scene, band, row, col
    # Validity is common to all 3 channels, so count band 0 only.
    counts = np.sum(np.isfinite(cube[:, 0, :, :]), axis=0).astype("uint16")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        median = np.nanmedian(cube, axis=0).astype("float32")

    median[:, counts < MIN_VALID_OBSERVATIONS] = np.nan
    return median, counts


def rgb_reflectance_to_uint8(rgb: np.ndarray) -> np.ndarray:
    """Convert RGB surface reflectance to display-ready 8-bit values."""
    if RGB_REFLECTANCE_MAX <= RGB_REFLECTANCE_MIN:
        raise ValueError("RGB_REFLECTANCE_MAX must be greater than RGB_REFLECTANCE_MIN")
    if RGB_GAMMA <= 0:
        raise ValueError("RGB_GAMMA must be > 0")

    valid = np.all(np.isfinite(rgb), axis=0)
    out = np.zeros(rgb.shape, dtype="uint8")

    if np.any(valid):
        norm = (rgb[:, valid] - RGB_REFLECTANCE_MIN) / (
            RGB_REFLECTANCE_MAX - RGB_REFLECTANCE_MIN
        )
        norm = np.clip(norm, 0.0, 1.0)
        if RGB_GAMMA != 1.0:
            norm = np.power(norm, 1.0 / RGB_GAMMA)

        # Reserve 0 for nodata. Valid pixels occupy 1..255 so genuinely dark
        # burned surfaces remain visible rather than becoming nodata.
        out[:, valid] = np.clip(np.rint(1.0 + norm * 254.0), 1, 255).astype("uint8")

    return out


def create_rgb_cog(
    period: str,
    scenes: Sequence[Scene],
    aoi_projected: gpd.GeoDataFrame,
    target_crs,
    output_path: Path,
) -> None:
    """
    Create a 10 m, display-ready natural-colour COG for PRE or POST validation.

    The composite is the pixel-wise median of cloud-screened B04/B03/B02
    surface reflectance from the same scene set used by the dNBR analysis.
    PRE and POST use an identical fixed stretch, making visual comparison fair.
    """
    transform, width, height, _ = build_target_grid(
        aoi_projected, RGB_RESOLUTION_M
    )
    geoms = [geom for geom in aoi_projected.geometry if geom is not None and not geom.is_empty]
    aoi_inside = geometry_mask(
        geoms,
        out_shape=(height, width),
        transform=transform,
        invert=True,
    )

    print(
        f"[RGB] {period.upper()} grid: {width} x {height} at "
        f"{RGB_RESOLUTION_M:.1f} m"
    )

    with tempfile.TemporaryDirectory(prefix=f"tolima_rgb_{period}_") as tmp_dir:
        tmp_gtiff = Path(tmp_dir) / f"{period}_rgb_work.tif"
        profile = {
            "driver": "GTiff",
            "width": width,
            "height": height,
            "count": 3,
            "crs": target_crs,
            "transform": transform,
            "dtype": "uint8",
            "nodata": RGB_NODATA,
            "tiled": True,
            "blockxsize": 512,
            "blockysize": 512,
            "compress": "deflate",
            "predictor": 2,
            "BIGTIFF": "IF_SAFER",
        }

        with ExitStack() as stack:
            opened = open_rgb_scene_vrts(
                stack, scenes, target_crs, transform, width, height
            )
            dst = stack.enter_context(rasterio.open(tmp_gtiff, "w", **profile))
            dst.colorinterp = (ColorInterp.red, ColorInterp.green, ColorInterp.blue)
            dst.set_band_description(1, "Red - Sentinel-2 B04")
            dst.set_band_description(2, "Green - Sentinel-2 B03")
            dst.set_band_description(3, "Blue - Sentinel-2 B02")
            dst.update_tags(
                PRODUCT="Sentinel-2 L2A natural-colour validation composite",
                PERIOD=period.upper(),
                COMPOSITE="pixel-wise median",
                SCL_MASK_MODE=SCL_MASK_MODE,
                RGB_STRETCH=(
                    f"reflectance {RGB_REFLECTANCE_MIN:.4f}.."
                    f"{RGB_REFLECTANCE_MAX:.4f}; gamma={RGB_GAMMA:.3f}"
                ),
            )

            block_windows = list(dst.block_windows(1))
            total = len(block_windows)
            for index, (_, window) in enumerate(block_windows, start=1):
                rgb, _counts = median_rgb_for_window(opened, window)

                row0 = int(window.row_off)
                row1 = row0 + int(window.height)
                col0 = int(window.col_off)
                col1 = col0 + int(window.width)
                inside = aoi_inside[row0:row1, col0:col1]
                rgb[:, ~inside] = np.nan

                dst.write(rgb_reflectance_to_uint8(rgb), window=window)

                if index == 1 or index % 20 == 0 or index == total:
                    print(f"[RGB] {period.upper()} blocks: {index}/{total}")

        # Convert the temporary tiled GeoTIFF into a true Cloud Optimized GeoTIFF.
        # GDAL's COG driver builds internal overviews and preserves RGB metadata.
        if output_path.exists():
            output_path.unlink()
        rio_copy(
            tmp_gtiff,
            output_path,
            driver="COG",
            BLOCKSIZE=512,
            COMPRESS="DEFLATE",
            OVERVIEW_RESAMPLING="AVERAGE",
            NUM_THREADS="ALL_CPUS",
            BIGTIFF="IF_SAFER",
        )

    # Basic structural validation: a COG should use the COG layout metadata in
    # recent GDAL versions. Even when that item is unavailable, tiled + overviews
    # are checked and reported.
    with rasterio.open(output_path) as src:
        layout = src.tags(ns="IMAGE_STRUCTURE").get("LAYOUT")
        ovs = src.overviews(1)
        print(
            f"[RGB] {period.upper()} COG written: {output_path} "
            f"(layout={layout or 'not-reported'}, overviews={ovs})"
        )


# =============================================================================
# CANDIDATE POLYGONISATION / SPECTRAL METRICS
# =============================================================================

def _dnbr_values_for_geometry(src, geom) -> np.ndarray:
    """Read valid dNBR pixels inside one geometry."""
    try:
        window = geometry_window(src, [geom])
    except WindowError:
        return np.array([], dtype="float32")

    arr = src.read(1, window=window).astype("float32")
    inside = geometry_mask(
        [geom],
        out_shape=arr.shape,
        transform=src.window_transform(window),
        invert=True,
    )
    valid = inside & (arr != DNBR_NODATA) & np.isfinite(arr)
    return arr[valid]


def add_candidate_dnbr_metrics(
    candidates: gpd.GeoDataFrame,
    dnbr_path: Path,
) -> gpd.GeoDataFrame:
    """Add robust dNBR summary metrics used by script 03 for confidence scoring."""
    if candidates.empty:
        for field in (
            "dnbr_mean", "dnbr_median", "dnbr_p90", "dnbr_max",
            "pct_ge_020", "pct_ge_027", "spectral_evidence",
        ):
            candidates[field] = []
        return candidates

    rows = []
    with rasterio.open(dnbr_path) as src:
        for _, feature in candidates.iterrows():
            vals = _dnbr_values_for_geometry(src, feature.geometry)
            if vals.size == 0:
                metrics = {
                    "dnbr_mean": np.nan,
                    "dnbr_median": np.nan,
                    "dnbr_p90": np.nan,
                    "dnbr_max": np.nan,
                    "pct_ge_020": 0.0,
                    "pct_ge_027": 0.0,
                    "spectral_evidence": "LOW",
                }
            else:
                mean = float(np.mean(vals))
                median = float(np.median(vals))
                p90 = float(np.percentile(vals, 90))
                maximum = float(np.max(vals))
                pct20 = float(np.mean(vals >= SPECTRAL_REFERENCE_THRESHOLD) * 100.0)
                pct27 = float(np.mean(vals >= STRONG_SPECTRAL_THRESHOLD) * 100.0)

                # This is deliberately only a spectral tier, not a final fire
                # classification. Script 03 adds independent VIIRS evidence.
                if median >= STRONG_SPECTRAL_THRESHOLD or pct27 >= 50.0:
                    evidence = "STRONG"
                elif median >= SPECTRAL_REFERENCE_THRESHOLD or pct20 >= 50.0:
                    evidence = "MODERATE"
                else:
                    evidence = "WEAK"

                metrics = {
                    "dnbr_mean": mean,
                    "dnbr_median": median,
                    "dnbr_p90": p90,
                    "dnbr_max": maximum,
                    "pct_ge_020": pct20,
                    "pct_ge_027": pct27,
                    "spectral_evidence": evidence,
                }

            row = feature.to_dict()
            row.update(metrics)
            rows.append(row)

    return gpd.GeoDataFrame(rows, geometry="geometry", crs=candidates.crs)


def create_burn_candidates(
    dnbr_path: Path,
    output_gpkg: Path,
    target_crs,
    aoi_projected: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """Polygonise dNBR candidates and attribute/split them by municipality."""
    with tempfile.TemporaryDirectory(prefix="tolima_burn_candidates_") as tmp_dir:
        candidate_mask_path = Path(tmp_dir) / "candidate_mask.tif"

        with rasterio.open(dnbr_path) as src:
            profile = src.profile.copy()
            profile.update(dtype="uint8", nodata=0, compress="deflate", predictor=1)

            with rasterio.open(candidate_mask_path, "w", **profile) as dst:
                for _, window in src.block_windows(1):
                    dnbr = src.read(1, window=window)
                    valid = dnbr != DNBR_NODATA
                    candidate = (
                        valid & (dnbr >= CANDIDATE_DNBR_THRESHOLD)
                    ).astype("uint8")
                    dst.write(candidate, 1, window=window)

        records = []
        with rasterio.open(candidate_mask_path) as src:
            band = rasterio.band(src, 1)
            for geom_mapping, value in shapes(band, mask=None, transform=src.transform):
                if int(value) != 1:
                    continue
                geom = shape(geom_mapping)
                if geom.is_empty:
                    continue
                area_ha = geom.area / 10000.0
                if area_ha < MIN_CANDIDATE_PATCH_HA:
                    continue
                records.append(
                    {
                        "candidate_thr": CANDIDATE_DNBR_THRESHOLD,
                        "area_ha": area_ha,
                        "geometry": geom,
                    }
                )

    if records:
        base = gpd.GeoDataFrame(records, geometry="geometry", crs=target_crs)
        base = base.sort_values("area_ha", ascending=False).reset_index(drop=True)
        base.insert(0, "source_candidate_id", np.arange(1, len(base) + 1, dtype=int))

        name_field = infer_name_field(aoi_projected)
        dept_field = infer_department_field(aoi_projected)
        attributed_records = []

        for _, candidate in base.iterrows():
            for _, municipality in aoi_projected.iterrows():
                if not candidate.geometry.intersects(municipality.geometry):
                    continue
                piece = candidate.geometry.intersection(municipality.geometry)
                if piece.is_empty:
                    continue
                piece_area_ha = piece.area / 10000.0
                if piece_area_ha <= 0:
                    continue

                attributed_records.append(
                    {
                        "source_candidate_id": int(candidate["source_candidate_id"]),
                        "municipality": (
                            str(municipality[name_field])
                            if name_field and pd.notna(municipality[name_field])
                            else None
                        ),
                        "department": (
                            str(municipality[dept_field])
                            if dept_field and pd.notna(municipality[dept_field])
                            else None
                        ),
                        "candidate_thr": CANDIDATE_DNBR_THRESHOLD,
                        "area_ha": piece_area_ha,
                        "geometry": piece,
                    }
                )

        gdf = gpd.GeoDataFrame(attributed_records, geometry="geometry", crs=target_crs)
        if not gdf.empty:
            gdf = add_candidate_dnbr_metrics(gdf, dnbr_path)
            gdf = gdf.sort_values(
                ["municipality", "area_ha"],
                ascending=[True, False],
                na_position="last",
            ).reset_index(drop=True)
            gdf.insert(0, "candidate_id", np.arange(1, len(gdf) + 1, dtype=int))
    else:
        gdf = gpd.GeoDataFrame(
            {
                "candidate_id": [],
                "source_candidate_id": [],
                "municipality": [],
                "department": [],
                "candidate_thr": [],
                "area_ha": [],
                "dnbr_mean": [],
                "dnbr_median": [],
                "dnbr_p90": [],
                "dnbr_max": [],
                "pct_ge_020": [],
                "pct_ge_027": [],
                "spectral_evidence": [],
            },
            geometry=[],
            crs=target_crs,
        )

    if output_gpkg.exists():
        output_gpkg.unlink()
    gdf.to_file(output_gpkg, layer="burn_candidates", driver="GPKG")
    return gdf


# =============================================================================
# MUNICIPALITY / AOI STATISTICS
# =============================================================================

def calculate_statistics(
    severity_path: Path,
    dnbr_path: Path,
    candidates: Optional[gpd.GeoDataFrame],
    aoi_projected: gpd.GeoDataFrame,
    output_csv: Path,
) -> pd.DataFrame:
    """Report severity areas plus conservative candidate/reference areas."""
    name_field = infer_name_field(aoi_projected)
    dept_field = infer_department_field(aoi_projected)
    rows = []

    candidate_area_lookup = {}
    if candidates is not None and not candidates.empty:
        grouped = candidates.groupby(["department", "municipality"], dropna=False)["area_ha"].sum()
        candidate_area_lookup = grouped.to_dict()

    with rasterio.open(severity_path) as sev_src, rasterio.open(dnbr_path) as dnbr_src:
        pixel_area_ha = abs(sev_src.transform.a * sev_src.transform.e) / 10000.0

        for idx, feature in aoi_projected.iterrows():
            geom = feature.geometry
            if geom is None or geom.is_empty:
                continue

            try:
                sev_window = geometry_window(sev_src, [geom])
                dnbr_window = geometry_window(dnbr_src, [geom])
            except WindowError:
                continue

            sev = sev_src.read(1, window=sev_window)
            sev_inside = geometry_mask(
                [geom],
                out_shape=sev.shape,
                transform=sev_src.window_transform(sev_window),
                invert=True,
            )

            dnbr = dnbr_src.read(1, window=dnbr_window).astype("float32")
            dnbr_inside = geometry_mask(
                [geom],
                out_shape=dnbr.shape,
                transform=dnbr_src.window_transform(dnbr_window),
                invert=True,
            )
            dnbr_valid = dnbr_inside & (dnbr != DNBR_NODATA) & np.isfinite(dnbr)

            municipality = (
                str(feature[name_field])
                if name_field and pd.notna(feature[name_field])
                else f"feature_{idx}"
            )
            department = (
                str(feature[dept_field])
                if dept_field and pd.notna(feature[dept_field])
                else None
            )

            row = {
                "department": department,
                "municipality": municipality,
            }

            severity_ge010 = 0.0
            for class_value in (4, 5, 6, 7):
                count = int(np.sum(sev_inside & (sev == class_value)))
                area_ha = count * pixel_area_ha
                row[f"{SEVERITY_LABELS[class_value]}_ha"] = area_ha
                severity_ge010 += area_ha

            row["severity_dnbr_ge_010_ha"] = severity_ge010
            row["dnbr_ge_015_raw_ha"] = float(
                np.sum(dnbr_valid & (dnbr >= CANDIDATE_DNBR_THRESHOLD)) * pixel_area_ha
            )
            row["dnbr_ge_020_raw_ha"] = float(
                np.sum(dnbr_valid & (dnbr >= SPECTRAL_REFERENCE_THRESHOLD)) * pixel_area_ha
            )
            row["candidate_polygons_ge2ha_ha"] = float(
                candidate_area_lookup.get((department, municipality), 0.0)
            )
            rows.append(row)

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(
            ["department", "candidate_polygons_ge2ha_ha"], ascending=[True, False]
        )
    df.to_csv(output_csv, index=False, encoding="utf-8")
    return df


# =============================================================================
# PROCESSING SUMMARY
# =============================================================================

def scene_to_dict(scene: Scene) -> Dict:
    return {
        "period": scene.period,
        "product_name": scene.product_name,
        "sensing_datetime": scene.sensing_datetime,
        "mgrs_tile": scene.mgrs_tile,
        "usable_percent_scl": scene.usable_percent,
        "boa_quantification_value": scene.quantification,
        "boa_add_offset_b02": scene.offset_b02,
        "boa_add_offset_b03": scene.offset_b03,
        "boa_add_offset_b04": scene.offset_b04,
        "boa_add_offset_b8a": scene.offset_b8a,
        "boa_add_offset_b11": scene.offset_b11,
        "boa_add_offset_b12": scene.offset_b12,
    }


def write_summary(
    path: Path,
    target_crs,
    pre_all: Sequence[Scene],
    post_all: Sequence[Scene],
    pre_used: Sequence[Scene],
    post_used: Sequence[Scene],
    candidates: Optional[gpd.GeoDataFrame],
) -> None:
    summary = {
        "method": "UN-SPIDER NBR/dNBR burn severity, multi-date median adaptation",
        "nbr_formula": "(B8A - B12) / (B8A + B12)",
        "dnbr_formula": "median(NBR_pre) - median(NBR_post), excluding PRE-fire MNDWI open water",
        "mndwi_formula": "(B03 - B11) / (B03 + B11)",
        "mndwi_period": "PRE only",
        "mndwi_water_threshold": MNDWI_WATER_THRESHOLD,
        "mndwi_min_valid_observations": MNDWI_MIN_VALID_OBSERVATIONS,
        "water_mask_dilation_pixels": WATER_MASK_DILATION_PIXELS,
        "resolution_m": RESOLUTION_M,
        "rgb_validation_cogs": WRITE_RGB_COGS,
        "rgb_resolution_m": RGB_RESOLUTION_M,
        "rgb_bands": "B04/B03/B02 natural colour",
        "rgb_composite": "pixel-wise median surface reflectance",
        "rgb_reflectance_stretch": [RGB_REFLECTANCE_MIN, RGB_REFLECTANCE_MAX],
        "rgb_gamma": RGB_GAMMA,
        "target_crs": str(target_crs),
        "municipality_field": MUNICIPALITY_FIELD,
        "department_field": DEPARTMENT_FIELD,
        "scl_mask_mode": SCL_MASK_MODE,
        "masked_scl_classes": sorted(MASKED_SCL_CLASSES),
        "min_scene_usable_percent": MIN_SCENE_USABLE_PERCENT,
        "min_valid_observations_per_period": MIN_VALID_OBSERVATIONS,
        "candidate_dnbr_threshold": CANDIDATE_DNBR_THRESHOLD,
        "spectral_reference_threshold": SPECTRAL_REFERENCE_THRESHOLD,
        "strong_spectral_threshold": STRONG_SPECTRAL_THRESHOLD,
        "min_candidate_patch_ha": MIN_CANDIDATE_PATCH_HA,
        "severity_thresholds": {
            "1_high_regrowth": "dNBR < -0.25",
            "2_low_regrowth": "-0.25 <= dNBR < -0.10",
            "3_unburned": "-0.10 <= dNBR < 0.10",
            "4_low_severity": "0.10 <= dNBR < 0.27",
            "5_moderate_low": "0.27 <= dNBR < 0.44",
            "6_moderate_high": "0.44 <= dNBR < 0.66",
            "7_high": "dNBR >= 0.66",
        },
        "pre_scenes_discovered": len(pre_all),
        "post_scenes_discovered": len(post_all),
        "pre_scenes_used": [scene_to_dict(s) for s in pre_used],
        "post_scenes_used": [scene_to_dict(s) for s in post_used],
        "candidate_polygon_count": None if candidates is None else len(candidates),
        "candidate_polygon_area_ha_after_min_patch_filter": (
            None
            if candidates is None or candidates.empty
            else float(candidates["area_ha"].sum())
        ),
    }

    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")


# =============================================================================
# MAIN
# =============================================================================

def main() -> dict:
    t0 = time.perf_counter()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prefix = OUTPUT_PREFIX or "Fire"

    dnbr_path = OUTPUT_DIR / f"{prefix}_dNBR.tif"
    severity_path = OUTPUT_DIR / f"{prefix}_burn_severity.tif"
    polygons_path = OUTPUT_DIR / f"{prefix}_burn_candidates.gpkg"
    stats_path = OUTPUT_DIR / f"{prefix}_burn_statistics_by_municipality.csv"
    summary_path = OUTPUT_DIR / f"{prefix}_processing_summary.json"
    rgb_pre_path = OUTPUT_DIR / f"{prefix}_RGB_PRE_10m_COG.tif"
    rgb_post_path = OUTPUT_DIR / f"{prefix}_RGB_POST_10m_COG.tif"
    mndwi_path = OUTPUT_DIR / f"{prefix}_PRE_MNDWI.tif"
    water_mask_path = OUTPUT_DIR / f"{prefix}_PRE_MNDWI_water_mask.tif"

    print("=" * 80)
    print("SENTINEL-2 dNBR BURN-SEVERITY PROCESSING (Fire module)")
    print("=" * 80)
    print(f"[INFO] AOI: {AOI_PATH}")
    print(f"[INFO] S2 root: {S2_ROOT}")
    print(f"[INFO] Output: {OUTPUT_DIR}")

    aoi = load_aoi(AOI_PATH)
    target_crs = choose_utm_crs(aoi)
    aoi_projected = aoi.to_crs(target_crs)
    transform, width, height, bounds = build_target_grid(
        aoi_projected, RESOLUTION_M
    )

    print(f"[GRID] CRS: {target_crs}")
    print(f"[GRID] Resolution: {RESOLUTION_M:.1f} m")
    print(f"[GRID] Size: {width} x {height} pixels")
    print(f"[GRID] Bounds: {bounds}")
    name_field = infer_name_field(aoi_projected)
    dept_field = infer_department_field(aoi_projected)
    print(f"[AOI] Municipality field: {name_field}")
    if dept_field:
        print(f"[AOI] Department field: {dept_field}")
    print(f"[AOI] Municipalities/features after dissolve: {len(aoi_projected)}")
    for _, feat in aoi_projected.iterrows():
        label = str(feat[name_field]) if name_field else "UNKNOWN"
        dept = str(feat[dept_field]) if dept_field else ""
        print(f"[AOI]   - {label}" + (f" ({dept})" if dept else ""))

    pre_all = discover_scenes("pre", PRE_DIR)
    post_all = discover_scenes("post", POST_DIR)

    print(f"[INPUT] PRE scenes discovered:  {len(pre_all)}")
    print(f"[INPUT] POST scenes discovered: {len(post_all)}")

    pre_used = screen_scenes(pre_all, aoi)
    post_used = screen_scenes(post_all, aoi)

    if len(pre_used) < MIN_VALID_OBSERVATIONS:
        print(
            f"[WARNING] Only {len(pre_used)} PRE scenes remain, while "
            f"MIN_VALID_OBSERVATIONS={MIN_VALID_OBSERVATIONS}. Some/all output "
            "pixels may be nodata."
        )
    if len(post_used) < MIN_VALID_OBSERVATIONS:
        print(
            f"[WARNING] Only {len(post_used)} POST scenes remain, while "
            f"MIN_VALID_OBSERVATIONS={MIN_VALID_OBSERVATIONS}. Some/all output "
            "pixels may be nodata."
        )

    # Derive PRE-fire open-water mask before any dNBR candidate mapping.
    create_pre_mndwi_water_mask(
        pre_scenes=pre_used,
        aoi_projected=aoi_projected,
        target_crs=target_crs,
        transform=transform,
        width=width,
        height=height,
        mndwi_path=mndwi_path,
        water_mask_path=water_mask_path,
    )

    if WRITE_RGB_COGS:
        print("\n[RGB] Creating 10 m natural-colour validation COGs")
        create_rgb_cog(
            period="pre",
            scenes=pre_used,
            aoi_projected=aoi_projected,
            target_crs=target_crs,
            output_path=rgb_pre_path,
        )
        create_rgb_cog(
            period="post",
            scenes=post_used,
            aoi_projected=aoi_projected,
            target_crs=target_crs,
            output_path=rgb_post_path,
        )

    # Always create both internally because polygons/statistics depend on severity.
    process_dnbr(
        pre_scenes=pre_used,
        post_scenes=post_used,
        aoi_projected=aoi_projected,
        target_crs=target_crs,
        transform=transform,
        width=width,
        height=height,
        dnbr_path=dnbr_path,
        severity_path=severity_path,
        water_mask_path=water_mask_path,
    )

    # F6: dNBR / severity como COG (tiles XYZ MapLibre); RGB ya salen con driver=COG.
    try:
        from app.infrastructure.raster.cog import ensure_fire_analysis_cogs

        cogged = ensure_fire_analysis_cogs(
            dnbr_path if WRITE_DNBR else None,
            severity_path if WRITE_SEVERITY else None,
        )
        if cogged:
            print(f"[COG] Cloud-optimized: {', '.join(Path(p).name for p in cogged)}")
    except Exception as cog_exc:
        print(f"[COG] WARNING: could not optimize dNBR/severity: {cog_exc}")

    candidates: Optional[gpd.GeoDataFrame] = None
    if WRITE_BURNED_POLYGONS:
        print("\n[VECTOR] Polygonising dNBR burn candidates")
        candidates = create_burn_candidates(
            dnbr_path=dnbr_path,
            output_gpkg=polygons_path,
            target_crs=target_crs,
            aoi_projected=aoi_projected,
        )
        print(f"[VECTOR] Candidate polygons >= {MIN_CANDIDATE_PATCH_HA:.2f} ha: {len(candidates)}")
        print(f"[VECTOR] Output: {polygons_path}")

    if WRITE_STATISTICS:
        print("\n[STATS] Calculating severity and candidate areas by municipality")
        stats = calculate_statistics(
            severity_path=severity_path,
            dnbr_path=dnbr_path,
            candidates=candidates,
            aoi_projected=aoi_projected,
            output_csv=stats_path,
        )
        print(f"[STATS] Rows: {len(stats)}")
        print(f"[STATS] Output: {stats_path}")

    write_summary(
        summary_path,
        target_crs,
        pre_all,
        post_all,
        pre_used,
        post_used,
        candidates,
    )

    # If the user requested only one final raster, remove the other here.
    if not WRITE_DNBR and dnbr_path.exists():
        dnbr_path.unlink()
    if not WRITE_SEVERITY and severity_path.exists():
        severity_path.unlink()

    elapsed = time.perf_counter() - t0

    print("\n" + "=" * 80)
    print("FINISHED")
    print("=" * 80)
    if WRITE_DNBR:
        print(f"[RESULT] dNBR: {dnbr_path}")
    if WRITE_SEVERITY:
        print(f"[RESULT] Severity: {severity_path}")
    if WRITE_BURNED_POLYGONS:
        print(f"[RESULT] Burn candidates: {polygons_path}")
    if WRITE_STATISTICS:
        print(f"[RESULT] Statistics: {stats_path}")
    if WRITE_RGB_COGS:
        print(f"[RESULT] RGB PRE COG: {rgb_pre_path}")
        print(f"[RESULT] RGB POST COG: {rgb_post_path}")
    if WRITE_PRE_MNDWI:
        print(f"[RESULT] PRE MNDWI: {mndwi_path}")
    if WRITE_WATER_MASK:
        print(f"[RESULT] PRE MNDWI water mask: {water_mask_path}")
    print(f"[RESULT] Processing summary: {summary_path}")
    print(f"[TIME] Total: {elapsed / 60:.1f} min")

    return {
        "ok": True,
        "elapsed_min": round(elapsed / 60.0, 2),
        "output_dir": str(OUTPUT_DIR),
        "dnbr": str(dnbr_path) if WRITE_DNBR else None,
        "severity": str(severity_path) if WRITE_SEVERITY else None,
        "candidates": str(polygons_path) if WRITE_BURNED_POLYGONS else None,
        "statistics": str(stats_path) if WRITE_STATISTICS else None,
        "summary": str(summary_path),
        "rgb_pre": str(rgb_pre_path) if WRITE_RGB_COGS else None,
        "rgb_post": str(rgb_post_path) if WRITE_RGB_COGS else None,
        "mndwi": str(mndwi_path) if WRITE_PRE_MNDWI else None,
        "water_mask": str(water_mask_path) if WRITE_WATER_MASK else None,
        "candidate_count": None if candidates is None else int(len(candidates)),
    }


def run_dnbr_pipeline(
    *,
    aoi_path: str | Path,
    s2_root: str | Path,
    output_dir: str | Path,
    output_prefix: str = "Fire",
    municipality_field: str = "MpNombre",
    department_field: str = "Depto",
) -> dict:
    """
    Run script-02 methodology for one Fire order.
    Expects ``s2_root/pre/*.SAFE`` and ``s2_root/post/*.SAFE`` from script 01.
    """
    global AOI_PATH, S2_ROOT, PRE_DIR, POST_DIR, OUTPUT_DIR, OUTPUT_PREFIX
    global MUNICIPALITY_FIELD, DEPARTMENT_FIELD

    AOI_PATH = Path(aoi_path)
    S2_ROOT = Path(s2_root)
    PRE_DIR = S2_ROOT / "pre"
    POST_DIR = S2_ROOT / "post"
    OUTPUT_DIR = Path(output_dir)
    OUTPUT_PREFIX = output_prefix or "Fire"
    MUNICIPALITY_FIELD = municipality_field
    DEPARTMENT_FIELD = department_field
    return main()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("\n[ERROR]", exc)
        sys.exit(1)
