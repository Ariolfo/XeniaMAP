"""Series temporales desde stacks multibanda en ``indices/`` (S2) o ``indecesPS/`` (PS)."""

from __future__ import annotations

import json
from pathlib import Path

import rasterio

from app.core.storage_paths import _tenant_storage
from app.services.preprocess_pipeline_variant import indices_dir_name, normalize_pipeline_variant
from app.services.s1_sar_indices import _safe_relative_under
from app.services.s1_sar_time_series import (
    band_index_for_iso,
    build_normalized_sar_volumes_for_dates,
    sample_pixel_series_from_stacks,
)

# Claves esperadas por variante (solo se usan las que existan en disco).
S2_TS_INDEX_KEYS = ("NDVI", "EVI", "NDWI", "CIre", "MCARI")
PS_TS_INDEX_KEYS = (
    "NDVI",
    "EVI",
    "NDWI",
    "MSAVI2",
    "MTVI2",
    "VARI",
    "TGI",
    "KNDVI",
    "GIYI",
    "MCARI",
    "NDRE",
    "RSTRUCTURE",
)


def _norm_iso_date(s: str) -> str:
    t = str(s).strip()
    return t[:10] if len(t) >= 10 else t


def optical_ts_index_keys(pipeline_variant: str) -> tuple[str, ...]:
    return PS_TS_INDEX_KEYS if normalize_pipeline_variant(pipeline_variant) == "ps" else S2_TS_INDEX_KEYS


def discover_primary_optical_index_stacks(
    tenant_id: int,
    project_id: int,
    pipeline_variant: str = "s2",
) -> dict[str, tuple[Path, list[str]]]:
    """
    Por cada índice estimado bajo ``indices/<CLAVE>/`` o ``indecesPS/<CLAVE>/``,
    elige el GeoTIFF con más bandas. Retorna ``clave -> (path, fechas_por_banda)``.
    """
    pv = normalize_pipeline_variant(pipeline_variant)
    wanted = set(optical_ts_index_keys(pv))
    root = _tenant_storage(tenant_id, project_id, indices_dir_name(pv))
    if not root.is_dir():
        return {}

    candidates: dict[str, list[tuple[Path, int, list[str]]]] = {k: [] for k in wanted}

    for p in sorted(root.rglob("*.tif")):
        if "_cog" in p.name.lower() or not p.is_file():
            continue
        rel = _safe_relative_under(root, p)
        if rel is None:
            continue
        parts = Path(rel).parts
        if len(parts) < 2:
            continue
        key = parts[0].strip().upper().replace("/", "_")
        if key == "R_STRUCTURE":
            key = "RSTRUCTURE"
        if key not in candidates:
            continue
        try:
            with rasterio.open(p) as src:
                n = int(src.count)
                tags = src.tags()
        except Exception:
            continue
        dates: list[str] = []
        jd = tags.get("BAND_DATES_JSON")
        if isinstance(jd, str) and jd.strip():
            try:
                parsed = json.loads(jd)
                if isinstance(parsed, list):
                    dates = [str(x) for x in parsed]
            except json.JSONDecodeError:
                dates = []
        if n < 1:
            continue
        candidates[key].append((p, n, dates))

    out: dict[str, tuple[Path, list[str]]] = {}
    for key in optical_ts_index_keys(pv):
        cand = candidates.get(key) or []
        if not cand:
            continue
        path, _n_bands, dates = max(cand, key=lambda x: x[1])
        out[key] = (path, dates)
    return out


def intersection_sorted_dates(stacks: dict[str, tuple[Path, list[str]]]) -> list[str]:
    """Fechas presentes en **todos** los stacks descubiertos (normalizadas YYYY-MM-DD)."""
    if not stacks:
        return []
    sets: list[set[str]] = []
    for _path, dates in stacks.values():
        sets.append({_norm_iso_date(d) for d in dates if str(d).strip()})
    if not sets:
        return []
    inter = set.intersection(*sets)
    return sorted(inter)


# Reexport para el endpoint óptico (misma normalización / muestreo que S1).
__all__ = (
    "S2_TS_INDEX_KEYS",
    "PS_TS_INDEX_KEYS",
    "optical_ts_index_keys",
    "discover_primary_optical_index_stacks",
    "intersection_sorted_dates",
    "band_index_for_iso",
    "build_normalized_sar_volumes_for_dates",
    "sample_pixel_series_from_stacks",
)
