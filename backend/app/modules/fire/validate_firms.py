#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
03_validate_burn_candidates_firms_MNDWI_v6.py

Auxiliary validation / prioritisation of Sentinel-2 dNBR burn candidates using
NASA FIRMS VIIRS active-fire detections.

This version assumes script 02 has already removed PRE-fire open water using a
multi-date MNDWI mask. FIRMS is therefore used only as independent positive
evidence for fire, not to repair water false positives.

IMPORTANT
---------
FIRMS is used as POSITIVE supporting evidence, not as a veto. A candidate is
never deleted merely because no VIIRS hotspot was detected: clouds, overpass
timing, fire size/intensity and sensor geometry can all lead to missed active
fire detections.

Inputs
------
- aoi/Incendios_Tolima.shp
- tolima_fire_results/Tolima_burn_candidates.gpkg  (from script 02 v4)

Outputs
-------
- Tolima_FIRMS_VIIRS_hotspots.gpkg
- Tolima_burn_candidates_validated.gpkg
- Tolima_burned_area_recommended.gpkg   (HIGH + MEDIUM confidence; still review)
- Tolima_FIRMS_validation_statistics.csv
- Tolima_FIRMS_validation_summary.json

Authentication
--------------
Request a free NASA FIRMS MAP_KEY and expose it as an environment variable:

    export FIRMS_MAP_KEY="..."

Official key page:
https://firms.modaps.eosdis.nasa.gov/api/map_key/

Dependencies
------------
    requests, pandas, geopandas, shapely, numpy
"""

from __future__ import annotations

import io
import json
import math
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from shapely.geometry import Point


# =============================================================================
# USER CONFIGURATION
# =============================================================================

SCRIPT_DIR = Path(__file__).resolve().parent

AOI_PATH = SCRIPT_DIR / "aoi" / "Incendios_Tolima.shp"
MUNICIPALITY_FIELD = "MpNombre"
DEPARTMENT_FIELD = "Depto"

RESULTS_DIR = SCRIPT_DIR / "tolima_fire_results"
CANDIDATE_GPKG = RESULTS_DIR / "Tolima_burn_candidates.gpkg"
CANDIDATE_LAYER = "burn_candidates"
OUTPUT_PREFIX = "Fire"

# Fire-reporting window. None means today.
FIRE_START = "2026-08-01"
FIRE_END: Optional[str] = None

# Global VIIRS NRT feeds. FIRMS Area API supports a maximum DAY_RANGE of 5,
# therefore the script automatically queries the date interval in 5-day chunks.
FIRMS_SOURCES: Sequence[str] = (
    "VIIRS_SNPP_NRT",
    "VIIRS_NOAA20_NRT",
    "VIIRS_NOAA21_NRT",
)
FIRMS_API_BASE = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
FIRMS_MAP_KEY_ENV = "FIRMS_MAP_KEY"
FIRMS_MAX_DAY_RANGE = 5

# Only nominal/high VIIRS confidence contributes to confidence scoring. Low
# confidence detections are retained in the hotspot layer for transparency.
VALIDATION_FIRMS_CONFIDENCE = {"n", "h"}

# VIIRS fire pixels are nominally ~375 m at nadir and can be larger off-nadir.
# HIGH requires stronger spatial support (<=500 m). Detections between 500 and
# 750 m can still support MEDIUM, but never HIGH by proximity alone.
HIGH_HOTSPOT_DISTANCE_M = 500.0
MEDIUM_HOTSPOT_DISTANCE_M = 750.0

# Query/retain an extra margin around the AOI so a hotspot close to a municipal
# boundary can still support a candidate near that boundary.
AOI_QUERY_BUFFER_M = 1000.0

# Confidence rules. These are intentionally simple and transparent.
DNBR_REFERENCE = 0.20
DNBR_STRONG = 0.27
PCT_REFERENCE_FOR_MEDIUM = 50.0

# Final "recommended" layer contains HIGH + MEDIUM confidence. It remains a
# remotely-sensed prioritisation product and should still be visually reviewed.
RECOMMENDED_CONFIDENCE = {"HIGH", "MEDIUM"}

SCRIPT_VERSION = "2026-09-03-firms-mndwi-v6"

HOTSPOTS_GPKG = RESULTS_DIR / "Fire_FIRMS_VIIRS_hotspots.gpkg"
VALIDATED_GPKG = RESULTS_DIR / "Fire_burn_candidates_validated.gpkg"
RECOMMENDED_GPKG = RESULTS_DIR / "Fire_burned_area_recommended.gpkg"
STATS_CSV = RESULTS_DIR / "Fire_FIRMS_validation_statistics.csv"
SUMMARY_JSON = RESULTS_DIR / "Fire_FIRMS_validation_summary.json"


def _refresh_output_paths() -> None:
    global HOTSPOTS_GPKG, VALIDATED_GPKG, RECOMMENDED_GPKG, STATS_CSV, SUMMARY_JSON, CANDIDATE_GPKG
    prefix = OUTPUT_PREFIX or "Fire"
    HOTSPOTS_GPKG = RESULTS_DIR / f"{prefix}_FIRMS_VIIRS_hotspots.gpkg"
    VALIDATED_GPKG = RESULTS_DIR / f"{prefix}_burn_candidates_validated.gpkg"
    RECOMMENDED_GPKG = RESULTS_DIR / f"{prefix}_burned_area_recommended.gpkg"
    STATS_CSV = RESULTS_DIR / f"{prefix}_FIRMS_validation_statistics.csv"
    SUMMARY_JSON = RESULTS_DIR / f"{prefix}_FIRMS_validation_summary.json"
    # Prefer Fire_* candidates, fall back to Tolima_* for compatibility.
    preferred = RESULTS_DIR / f"{prefix}_burn_candidates.gpkg"
    legacy = RESULTS_DIR / "Tolima_burn_candidates.gpkg"
    CANDIDATE_GPKG = preferred if preferred.exists() or not legacy.exists() else legacy



# =============================================================================
# HELPERS
# =============================================================================

def parse_iso_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def resolve_end_date() -> str:
    return FIRE_END if FIRE_END else date.today().isoformat()


def choose_utm_crs(aoi: gpd.GeoDataFrame) -> str:
    aoi4326 = aoi.to_crs(4326)
    centroid = aoi4326.geometry.unary_union.centroid
    zone = int(math.floor((centroid.x + 180.0) / 6.0) + 1)
    epsg = (32600 if centroid.y >= 0 else 32700) + zone
    return f"EPSG:{epsg}"


def load_aoi(path: Path) -> gpd.GeoDataFrame:
    if not path.exists():
        raise FileNotFoundError(f"AOI not found: {path}")
    gdf = gpd.read_file(path)
    if gdf.empty or gdf.crs is None:
        raise RuntimeError("AOI is empty or has no CRS.")

    for field in (MUNICIPALITY_FIELD, DEPARTMENT_FIELD):
        if field not in gdf.columns:
            raise KeyError(f"Required AOI field '{field}' not found: {list(gdf.columns)}")

    gdf = gdf[gdf.geometry.notna() & (~gdf.geometry.is_empty)].copy()
    invalid = ~gdf.geometry.is_valid
    if invalid.any():
        gdf.loc[invalid, "geometry"] = gdf.loc[invalid, "geometry"].buffer(0)

    return (
        gdf[[DEPARTMENT_FIELD, MUNICIPALITY_FIELD, gdf.geometry.name]]
        .dissolve(by=[DEPARTMENT_FIELD, MUNICIPALITY_FIELD], as_index=False)
        .reset_index(drop=True)
    )


def load_candidates(path: Path, target_crs: str) -> gpd.GeoDataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"Candidate layer not found: {path}\nRun 02_process_dnbr_tolima_RGB_v4.py first."
        )
    try:
        gdf = gpd.read_file(path, layer=CANDIDATE_LAYER)
    except Exception:
        gdf = gpd.read_file(path)

    if gdf.empty:
        print("[WARNING] Candidate layer is empty. FIRMS will still be downloaded.")
    if gdf.crs is None:
        raise RuntimeError("Candidate layer has no CRS.")

    required_metrics = {
        "candidate_id", "municipality", "department", "area_ha",
        "dnbr_mean", "dnbr_median", "dnbr_p90", "dnbr_max",
        "pct_ge_020", "pct_ge_027", "spectral_evidence",
    }
    missing = sorted(required_metrics - set(gdf.columns))
    if missing:
        raise KeyError(
            "Candidate layer is missing v4 fields: " + ", ".join(missing) +
            "\nRun script 02 v4 to recreate Tolima_burn_candidates.gpkg."
        )
    return gdf.to_crs(target_crs)


def iter_date_chunks(start: date, end: date, max_days: int = 5) -> Iterable[Tuple[date, int]]:
    if end < start:
        raise ValueError("FIRE_END is before FIRE_START")
    current = start
    while current <= end:
        remaining = (end - current).days + 1
        day_range = min(max_days, remaining)
        yield current, day_range
        current += timedelta(days=day_range)


def query_bbox_from_aoi(aoi_projected: gpd.GeoDataFrame) -> Tuple[float, float, float, float]:
    buffered = aoi_projected.geometry.unary_union.buffer(AOI_QUERY_BUFFER_M)
    g = gpd.GeoSeries([buffered], crs=aoi_projected.crs).to_crs(4326).iloc[0]
    west, south, east, north = g.bounds
    return west, south, east, north


def request_firms_chunk(
    session: requests.Session,
    map_key: str,
    source: str,
    bbox: Tuple[float, float, float, float],
    start_date: date,
    day_range: int,
) -> pd.DataFrame:
    west, south, east, north = bbox
    area = f"{west:.6f},{south:.6f},{east:.6f},{north:.6f}"
    url = (
        f"{FIRMS_API_BASE}/{map_key}/{source}/{area}/{day_range}/"
        f"{start_date.isoformat()}"
    )

    response = session.get(url, timeout=120)
    response.raise_for_status()
    text = response.text.strip()
    if not text:
        return pd.DataFrame()
    if text.lower().startswith(("invalid", "error")):
        raise RuntimeError(f"FIRMS API error for {source}: {text[:500]}")

    try:
        df = pd.read_csv(io.StringIO(text))
    except Exception as exc:
        raise RuntimeError(
            f"Could not parse FIRMS CSV for {source}, {start_date}, {day_range} days.\n"
            f"Response starts with: {text[:300]}"
        ) from exc

    if df.empty:
        return df
    df["firms_source"] = source
    return df


def download_firms_hotspots(
    map_key: str,
    bbox: Tuple[float, float, float, float],
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    frames: List[pd.DataFrame] = []
    with requests.Session() as session:
        session.headers.update({"User-Agent": "Tolima-fire-validation/1.0"})
        for source in FIRMS_SOURCES:
            print(f"\n[FIRMS] Source: {source}")
            for chunk_start, day_range in iter_date_chunks(start_date, end_date, FIRMS_MAX_DAY_RANGE):
                chunk_end = chunk_start + timedelta(days=day_range - 1)
                print(f"[FIRMS]   {chunk_start} .. {chunk_end}")
                df = request_firms_chunk(
                    session, map_key, source, bbox, chunk_start, day_range
                )
                if not df.empty:
                    frames.append(df)

    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True, sort=False)
    for col in ("latitude", "longitude", "frp"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["latitude", "longitude"]).copy()

    # Duplicate rows can occasionally be returned across overlapping/updated NRT
    # requests. Keep detections from different satellites/sources distinct.
    dedup_cols = [
        c for c in (
            "latitude", "longitude", "acq_date", "acq_time", "satellite",
            "firms_source", "version"
        ) if c in df.columns
    ]
    if dedup_cols:
        df = df.drop_duplicates(subset=dedup_cols).reset_index(drop=True)
    return df


def hotspots_to_gdf(
    df: pd.DataFrame,
    target_crs: str,
    aoi_projected: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    if df.empty:
        cols = list(df.columns) + ["validation_ok", "municipality", "department"]
        return gpd.GeoDataFrame({c: [] for c in cols}, geometry=[], crs=target_crs)

    geometry = [Point(xy) for xy in zip(df["longitude"], df["latitude"])]
    gdf = gpd.GeoDataFrame(df.copy(), geometry=geometry, crs="EPSG:4326").to_crs(target_crs)

    # Retain only detections close enough to the study municipalities to be useful.
    query_zone = aoi_projected.geometry.unary_union.buffer(AOI_QUERY_BUFFER_M)
    gdf = gdf[gdf.geometry.intersects(query_zone)].copy().reset_index(drop=True)

    conf = gdf.get("confidence", pd.Series(index=gdf.index, dtype=object)).astype(str).str.lower()
    gdf["validation_ok"] = conf.isin(VALIDATION_FIRMS_CONFIDENCE)

    gdf["municipality"] = None
    gdf["department"] = None
    for idx, hotspot in gdf.iterrows():
        for _, muni in aoi_projected.iterrows():
            if hotspot.geometry.within(muni.geometry):
                gdf.at[idx, "municipality"] = str(muni[MUNICIPALITY_FIELD])
                gdf.at[idx, "department"] = str(muni[DEPARTMENT_FIELD])
                break
    return gdf


def normalize_acq_datetime(row: pd.Series) -> Optional[str]:
    if pd.isna(row.get("acq_date")):
        return None
    d = str(row.get("acq_date"))
    t = str(row.get("acq_time", "")).split(".")[0].zfill(4)
    if len(t) >= 4 and t[:4].isdigit():
        return f"{d}T{t[:2]}:{t[2:4]}Z"
    return d


def classify_confidence(row: pd.Series) -> Tuple[str, str]:
    """Transparent fusion of dNBR strength and independent VIIRS support."""
    n_hot_500 = int(row.get("hotspots_500m", 0) or 0)
    n_hot_750 = int(row.get("hotspots_750m", 0) or 0)
    median = float(row.get("dnbr_median", np.nan))
    p90 = float(row.get("dnbr_p90", np.nan))
    pct20 = float(row.get("pct_ge_020", 0.0) or 0.0)

    supports_reference = (
        (np.isfinite(median) and median >= DNBR_REFERENCE)
        or (np.isfinite(p90) and p90 >= DNBR_STRONG)
    )
    strong_spectral = (
        (np.isfinite(median) and median >= DNBR_STRONG)
        or pct20 >= PCT_REFERENCE_FOR_MEDIUM
    )

    if n_hot_500 > 0 and supports_reference:
        return "HIGH", "VIIRS<=500m + dNBR>=reference"
    if n_hot_750 > 0:
        return "MEDIUM", "VIIRS<=750m + candidate dNBR evidence"
    if strong_spectral:
        return "MEDIUM", "strong dNBR evidence; no VIIRS detection"
    return "LOW", "weak dNBR evidence; no VIIRS detection"


def validate_candidates(
    candidates: gpd.GeoDataFrame,
    hotspots: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    if candidates.empty:
        out = candidates.copy()
        for col in (
            "hotspots_inside", "hotspots_500m", "hotspots_750m", "nearest_hotspot_m",
            "max_frp_750m", "first_hotspot", "last_hotspot", "firms_sensors",
            "confidence", "confidence_reason",
        ):
            out[col] = []
        return out

    validation_hotspots = hotspots[hotspots["validation_ok"]].copy() if not hotspots.empty else hotspots.copy()
    rows = []

    for _, candidate in candidates.iterrows():
        row = candidate.to_dict()
        geom = candidate.geometry

        if validation_hotspots.empty:
            distances = np.array([], dtype=float)
            near = validation_hotspots
            inside = validation_hotspots
        else:
            distances = validation_hotspots.geometry.distance(geom).to_numpy(dtype=float)
            near500_mask = distances <= HIGH_HOTSPOT_DISTANCE_M
            near750_mask = distances <= MEDIUM_HOTSPOT_DISTANCE_M
            near500 = validation_hotspots.loc[near500_mask].copy()
            near = validation_hotspots.loc[near750_mask].copy()
            inside = validation_hotspots[validation_hotspots.geometry.within(geom)].copy()

        if validation_hotspots.empty:
            near500 = validation_hotspots

        row["hotspots_inside"] = int(len(inside))
        row["hotspots_500m"] = int(len(near500))
        row["hotspots_750m"] = int(len(near))
        row["nearest_hotspot_m"] = (
            float(np.min(distances)) if distances.size else np.nan
        )
        row["max_frp_750m"] = (
            float(pd.to_numeric(near["frp"], errors="coerce").max())
            if (not near.empty and "frp" in near.columns)
            else np.nan
        )

        if not near.empty:
            times = [normalize_acq_datetime(r) for _, r in near.iterrows()]
            times = sorted(t for t in times if t)
            row["first_hotspot"] = times[0] if times else None
            row["last_hotspot"] = times[-1] if times else None
            sensors = sorted(set(str(v) for v in near.get("satellite", pd.Series(dtype=object)).dropna()))
            row["firms_sensors"] = ",".join(sensors)
        else:
            row["first_hotspot"] = None
            row["last_hotspot"] = None
            row["firms_sensors"] = None

        confidence, reason = classify_confidence(pd.Series(row))
        row["confidence"] = confidence
        row["confidence_reason"] = reason
        rows.append(row)

    return gpd.GeoDataFrame(rows, geometry="geometry", crs=candidates.crs)


def write_statistics(validated: gpd.GeoDataFrame, output_csv: Path) -> pd.DataFrame:
    if validated.empty:
        df = pd.DataFrame(
            columns=[
                "department", "municipality", "high_ha", "medium_ha", "low_candidate_ha",
                "recommended_high_medium_ha", "candidate_total_ha"
            ]
        )
        df.to_csv(output_csv, index=False)
        return df

    rows = []
    for (department, municipality), group in validated.groupby(
        ["department", "municipality"], dropna=False
    ):
        high = float(group.loc[group["confidence"] == "HIGH", "area_ha"].sum())
        medium = float(group.loc[group["confidence"] == "MEDIUM", "area_ha"].sum())
        low = float(group.loc[group["confidence"] == "LOW", "area_ha"].sum())
        rows.append(
            {
                "department": department,
                "municipality": municipality,
                "high_ha": high,
                "medium_ha": medium,
                "low_candidate_ha": low,
                "recommended_high_medium_ha": high + medium,
                "candidate_total_ha": high + medium + low,
            }
        )

    df = pd.DataFrame(rows).sort_values(
        ["department", "recommended_high_medium_ha"], ascending=[True, False]
    )
    df.to_csv(output_csv, index=False, encoding="utf-8")
    return df


def safe_unlink(path: Path) -> None:
    if path.exists():
        path.unlink()


# =============================================================================
# MAIN
# =============================================================================

def main() -> dict:
    t0 = time.perf_counter()
    _refresh_output_paths()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    map_key = os.environ.get(FIRMS_MAP_KEY_ENV)
    if not map_key:
        raise RuntimeError(
            f"NASA FIRMS MAP_KEY not found. Set environment variable {FIRMS_MAP_KEY_ENV}.\n"
            "Request a free key at https://firms.modaps.eosdis.nasa.gov/api/map_key/"
        )

    start = parse_iso_date(FIRE_START)
    end = parse_iso_date(resolve_end_date())

    print("=" * 80)
    print("NASA FIRMS / VIIRS VALIDATION OF dNBR CANDIDATES (Fire module)")
    print("=" * 80)
    print(f"[INFO] Script version: {SCRIPT_VERSION}")
    print(f"[INFO] AOI: {AOI_PATH}")
    print(f"[INFO] Candidates: {CANDIDATE_GPKG}")
    print(f"[INFO] FIRMS dates: {start} .. {end}")
    print(f"[INFO] FIRMS sources: {', '.join(FIRMS_SOURCES)}")
    print(f"[INFO] Validation confidence accepted: {sorted(VALIDATION_FIRMS_CONFIDENCE)}")
    print(f"[INFO] HIGH hotspot distance: <={HIGH_HOTSPOT_DISTANCE_M:.0f} m")
    print(f"[INFO] MEDIUM support distance: <={MEDIUM_HOTSPOT_DISTANCE_M:.0f} m")

    aoi = load_aoi(AOI_PATH)
    target_crs = choose_utm_crs(aoi)
    aoi_projected = aoi.to_crs(target_crs)
    candidates = load_candidates(CANDIDATE_GPKG, target_crs)
    bbox = query_bbox_from_aoi(aoi_projected)
    print(f"[INFO] Query bbox (W,S,E,N): {bbox}")

    raw_hotspots = download_firms_hotspots(map_key, bbox, start, end)
    hotspots = hotspots_to_gdf(raw_hotspots, target_crs, aoi_projected)
    print(f"[FIRMS] Hotspots retained near AOI: {len(hotspots)}")
    if not hotspots.empty:
        print(f"[FIRMS] Nominal/high validation hotspots: {int(hotspots['validation_ok'].sum())}")

    validated = validate_candidates(candidates, hotspots)
    recommended = validated[validated["confidence"].isin(RECOMMENDED_CONFIDENCE)].copy()

    safe_unlink(HOTSPOTS_GPKG)
    hotspots.to_file(HOTSPOTS_GPKG, layer="viirs_hotspots", driver="GPKG")

    safe_unlink(VALIDATED_GPKG)
    validated.to_file(VALIDATED_GPKG, layer="burn_candidates_validated", driver="GPKG")

    safe_unlink(RECOMMENDED_GPKG)
    recommended.to_file(RECOMMENDED_GPKG, layer="recommended_burned_area", driver="GPKG")

    write_statistics(validated, STATS_CSV)

    summary: Dict = {
        "script_version": SCRIPT_VERSION,
        "firms_api": "NASA FIRMS Area API",
        "firms_sources": list(FIRMS_SOURCES),
        "fire_start": start.isoformat(),
        "fire_end": end.isoformat(),
        "validation_confidence_values": sorted(VALIDATION_FIRMS_CONFIDENCE),
        "high_hotspot_distance_m": HIGH_HOTSPOT_DISTANCE_M,
        "medium_hotspot_distance_m": MEDIUM_HOTSPOT_DISTANCE_M,
        "aoi_query_buffer_m": AOI_QUERY_BUFFER_M,
        "confidence_logic": {
            "HIGH": "VIIRS nominal/high <=500 m AND (median dNBR >=0.20 OR p90 dNBR >=0.27)",
            "MEDIUM": "VIIRS nominal/high <=750 m OR strong spectral dNBR evidence without VIIRS",
            "LOW": "weak spectral candidate and no nominal/high VIIRS support",
            "note": "No VIIRS detection is never used as proof that an area did not burn.",
        },
        "candidate_count": int(len(validated)),
        "high_count": int((validated["confidence"] == "HIGH").sum()) if not validated.empty else 0,
        "medium_count": int((validated["confidence"] == "MEDIUM").sum()) if not validated.empty else 0,
        "low_count": int((validated["confidence"] == "LOW").sum()) if not validated.empty else 0,
        "recommended_count": int(len(recommended)),
        "hotspots_total_near_aoi": int(len(hotspots)),
        "hotspots_validation_nominal_high": int(hotspots["validation_ok"].sum()) if not hotspots.empty else 0,
        "outputs": {
            "hotspots": str(HOTSPOTS_GPKG),
            "validated_candidates": str(VALIDATED_GPKG),
            "recommended_area": str(RECOMMENDED_GPKG),
            "statistics": str(STATS_CSV),
            "summary": str(SUMMARY_JSON),
        },
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    elapsed = time.perf_counter() - t0
    print("\n" + "=" * 80)
    print("FINISHED")
    print("=" * 80)
    print(f"[RESULT] FIRMS hotspots: {HOTSPOTS_GPKG}")
    print(f"[RESULT] Validated candidates: {VALIDATED_GPKG}")
    print(f"[RESULT] Recommended HIGH+MEDIUM: {RECOMMENDED_GPKG}")
    print(f"[RESULT] Statistics: {STATS_CSV}")
    print(f"[RESULT] Summary: {SUMMARY_JSON}")
    print(f"[TIME] Total: {elapsed / 60:.1f} min")
    print("[NOTE] HIGH/MEDIUM is a prioritisation product, not a substitute for RGB/field validation.")

    return {
        "ok": True,
        "elapsed_min": round(elapsed / 60.0, 2),
        "results_dir": str(RESULTS_DIR),
        **summary,
    }


def run_firms_pipeline(
    *,
    aoi_path: str | Path,
    results_dir: str | Path,
    fire_start: str,
    fire_end: str | None = None,
    output_prefix: str = "Fire",
    municipality_field: str = "MpNombre",
    department_field: str = "Depto",
    map_key: str | None = None,
) -> dict:
    """
    Run script-03 methodology for one Fire order.
    Expects ``{prefix}_burn_candidates.gpkg`` from script 02 in results_dir.
    """
    global AOI_PATH, RESULTS_DIR, FIRE_START, FIRE_END, OUTPUT_PREFIX
    global MUNICIPALITY_FIELD, DEPARTMENT_FIELD

    AOI_PATH = Path(aoi_path)
    RESULTS_DIR = Path(results_dir)
    FIRE_START = fire_start
    FIRE_END = fire_end
    OUTPUT_PREFIX = output_prefix or "Fire"
    MUNICIPALITY_FIELD = municipality_field
    DEPARTMENT_FIELD = department_field
    if map_key:
        os.environ[FIRMS_MAP_KEY_ENV] = map_key
    _refresh_output_paths()
    return main()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("\n[ERROR]", exc)
        sys.exit(1)
