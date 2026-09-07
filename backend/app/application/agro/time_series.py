"""Casos de uso Agro: series temporales ópticas, SAR S1 y agroclima de proyecto."""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from app.application.agro import agroclimate as _agroclimate
from app.schemas.schemas import RoiSelectionNormalized
from app.services.preprocess_pipeline_variant import indices_dir_name, normalize_pipeline_variant


def roi_mask_for_polygon(points: list, h: int, w: int) -> np.ndarray:
    if len(points) < 3:
        return np.zeros((h, w), dtype=bool)
    px = np.array([float(p.x) for p in points], dtype=np.float64)
    py = np.array([float(p.y) for p in points], dtype=np.float64)
    cols = (np.arange(w, dtype=np.float64) + 0.5) / max(w, 1)
    rows = (np.arange(h, dtype=np.float64) + 0.5) / max(h, 1)
    xg, yg = np.meshgrid(cols, rows)
    inside = np.zeros((h, w), dtype=bool)
    j = len(points) - 1
    eps = 1e-12
    for i in range(len(points)):
        xi, yi = px[i], py[i]
        xj, yj = px[j], py[j]
        dy = yj - yi
        denom = dy if abs(dy) > eps else eps
        cross = xi + ((yg - yi) * (xj - xi) / denom)
        intersects = ((yi > yg) != (yj > yg)) & (xg < cross)
        inside ^= intersects
        j = i
    return inside


def roi_mask_from_selection(roi_selection: RoiSelectionNormalized, h: int, w: int) -> np.ndarray:
    if roi_selection.polygon_points:
        return roi_mask_for_polygon(roi_selection.polygon_points, h, w)
    c0 = int(np.floor(float(roi_selection.x1) * w))
    c1 = int(np.ceil(float(roi_selection.x2) * w))
    r0 = int(np.floor(float(roi_selection.y1) * h))
    r1 = int(np.ceil(float(roi_selection.y2) * h))
    c0 = min(max(c0, 0), w - 1)
    c1 = min(max(c1, c0 + 1), w)
    r0 = min(max(r0, 0), h - 1)
    r1 = min(max(r1, r0 + 1), h)
    roi_mask = np.zeros((h, w), dtype=bool)
    roi_mask[r0:r1, c0:c1] = True
    return roi_mask


def _points_and_stats(
    stacked: dict[str, np.ndarray],
    index_list: tuple[str, ...],
    wanted_sorted: list[str],
    roi_selection: RoiSelectionNormalized | None,
) -> tuple[list[dict], dict]:
    points: list[dict] = []
    first = stacked[index_list[0]]
    _, h, w = first.shape
    roi_mask = np.ones((h, w), dtype=bool)
    if roi_selection is not None:
        roi_mask = roi_mask_from_selection(roi_selection, h, w)

    for t, date in enumerate(wanted_sorted):
        row: dict = {"date": date, "raster_layer_id": t + 1, "by_index": {}}
        for ix in index_list:
            plane = stacked[ix][t]
            fin = plane[np.isfinite(plane) & roi_mask]
            if fin.size == 0:
                row["by_index"][ix] = {
                    "mean": None,
                    "std": None,
                    "n_pixels": 0,
                    "n_pixels_raw": 0,
                }
            else:
                npx = int(fin.size)
                row["by_index"][ix] = {
                    "mean": float(np.nanmean(plane)),
                    "std": float(np.nanstd(plane)),
                    "n_pixels": npx,
                    "n_pixels_raw": npx,
                }
        points.append(row)

    temporal_stats: dict = {}
    for ix in index_list:
        vals = [p["by_index"][ix]["mean"] for p in points if p["by_index"][ix]["mean"] is not None]
        if not vals:
            temporal_stats[ix] = {"mean": None, "std": None}
        else:
            a = np.array(vals, dtype=np.float64)
            temporal_stats[ix] = {
                "mean": float(np.mean(a)),
                "std": float(np.std(a, ddof=1)) if len(vals) > 1 else 0.0,
            }
    return points, temporal_stats


def _resolve_wanted_dates(
    requested: Sequence[str] | None,
    available: set[str],
    *,
    missing_fmt: str,
) -> list[str]:
    wanted_sorted: list[str] = []
    seen: set[str] = set()
    for d in requested or []:
        nd = _agroclimate.norm_iso_date(str(d))
        if nd not in available:
            raise ValueError(missing_fmt.format(nd=nd))
        if nd not in seen:
            seen.add(nd)
            wanted_sorted.append(nd)
    if wanted_sorted:
        wanted_sorted.sort()
        return wanted_sorted
    return sorted(available)


class BuildVegetationTimeSeries:
    """Series desde stacks ópticos en ``indices/`` o ``indecesPS/``."""

    def execute(
        self,
        *,
        tenant_id: int,
        project_id: int,
        pipeline_variant: str,
        dates: Sequence[str] | None,
        max_pixel_series: int,
        random_seed: int,
        roi_selection: RoiSelectionNormalized | None,
    ) -> dict[str, Any]:
        from app.services.optical_index_time_series import (
            build_normalized_sar_volumes_for_dates,
            discover_primary_optical_index_stacks,
            intersection_sorted_dates,
            sample_pixel_series_from_stacks,
        )

        pv = normalize_pipeline_variant(pipeline_variant)
        idx_dir = indices_dir_name(pv)
        stacks = discover_primary_optical_index_stacks(tenant_id, project_id, pv)
        if not stacks:
            raise ValueError(
                f"No hay stacks de índices en {idx_dir}/. Ejecuta antes el paso 3 (Estimar índices)."
            )

        available = set(intersection_sorted_dates(stacks))
        if not available:
            raise ValueError(
                f"No hay fechas comunes entre los stacks en {idx_dir}/ "
                "(revisa BAND_DATES_JSON de cada índice estimado)."
            )

        wanted_sorted = _resolve_wanted_dates(
            dates,
            available,
            missing_fmt=(
                "La fecha {nd} no está en la intersección de fechas de los stacks en " + idx_dir + "/."
            ),
        )
        index_list = tuple(stacks.keys())

        try:
            stacked, _ref = build_normalized_sar_volumes_for_dates(stacks, wanted_sorted, index_list)
        except Exception as exc:
            raise RuntimeError(f"No se pudieron leer los stacks de índices: {exc!s}") from exc

        points, temporal_stats = _points_and_stats(stacked, index_list, wanted_sorted, roi_selection)
        series_by_index, n_sampled, n_valid = sample_pixel_series_from_stacks(
            stacked,
            index_list,
            max_pixel_series,
            random_seed,
            roi_selection.model_dump() if roi_selection is not None else None,
        )

        agg_desc = (
            f"Índices desde stacks en {idx_dir}/ (una banda por fecha); normalización min-max por fecha. "
            "Muestreo aleatorio de píxeles válidos en todas las fechas e índices estimados."
        )
        if roi_selection is not None:
            agg_desc = f"{agg_desc} Filtrado espacial por ROI normalizado."

        return {
            "source": "optical_index_stacks",
            "project_id": project_id,
            "pipeline_variant": pv,
            "roi_selection": roi_selection.model_dump() if roi_selection is not None else None,
            "dates": wanted_sorted,
            "indices": list(index_list),
            "points": points,
            "temporal_stats": temporal_stats,
            "spatial_aggregation": {
                "method": "all_valid_pixels_in_roi" if roi_selection is not None else "all_valid_pixels",
                "description": agg_desc,
            },
            "per_pixel": {
                "n_sampled": n_sampled,
                "n_valid_pixels": n_valid,
                "max_requested": max_pixel_series,
                "random_seed": random_seed,
                "series_by_index": series_by_index,
            },
        }


class BuildS1SarTimeSeries:
    """Series desde stacks SAR en ``s1indices/``."""

    def execute(
        self,
        *,
        tenant_id: int,
        project_id: int,
        dates: Sequence[str] | None,
        max_pixel_series: int,
        random_seed: int,
        roi_selection: RoiSelectionNormalized | None,
    ) -> dict[str, Any]:
        from app.services.s1_sar_indices import S1_SAR_INDEX_KEYS
        from app.services.s1_sar_time_series import (
            build_normalized_sar_volumes_for_dates,
            discover_primary_s1_sar_stacks,
            intersection_sorted_dates,
            sample_pixel_series_from_stacks,
        )

        stacks = discover_primary_s1_sar_stacks(tenant_id, project_id)
        if len(stacks) < len(S1_SAR_INDEX_KEYS):
            raise ValueError(
                "No hay stacks completos para los cinco índices SAR en s1indices/. "
                "Ejecuta «Estimar índices SAR»."
            )

        available = set(intersection_sorted_dates(stacks))
        if not available:
            raise ValueError("No hay fechas comunes entre todos los stacks en s1indices/.")

        wanted_sorted = _resolve_wanted_dates(
            dates,
            available,
            missing_fmt=(
                "La fecha {nd} no está en la intersección de fechas de todos los índices SAR (s1indices/)."
            ),
        )
        index_list = tuple(S1_SAR_INDEX_KEYS)

        try:
            stacked, _ref = build_normalized_sar_volumes_for_dates(stacks, wanted_sorted, index_list)
        except Exception as exc:
            raise RuntimeError(f"No se pudieron leer los stacks SAR: {exc!s}") from exc

        points, temporal_stats = _points_and_stats(stacked, index_list, wanted_sorted, roi_selection)
        series_by_index, n_sampled, n_valid = sample_pixel_series_from_stacks(
            stacked,
            index_list,
            max_pixel_series,
            random_seed,
            roi_selection.model_dump() if roi_selection is not None else None,
        )

        return {
            "source": "s1_sar",
            "project_id": project_id,
            "roi_selection": roi_selection.model_dump() if roi_selection is not None else None,
            "dates": wanted_sorted,
            "indices": list(index_list),
            "points": points,
            "temporal_stats": temporal_stats,
            "spatial_aggregation": {
                "method": "all_valid_pixels_in_roi" if roi_selection is not None else "all_valid_pixels",
                "description": (
                    "Índices SAR por fecha desde s1indices/; normalización min-max por fecha en cada índice. "
                    "Muestreo aleatorio de píxeles válidos en todas las fechas e índices."
                    + (" Filtrado espacial por ROI normalizado." if roi_selection is not None else "")
                ),
            },
            "per_pixel": {
                "n_sampled": n_sampled,
                "n_valid_pixels": n_valid,
                "max_requested": max_pixel_series,
                "random_seed": random_seed,
                "series_by_index": series_by_index,
            },
        }


class BuildAgroclimateSeries:
    """Open-Meteo alineado a fechas de escena S1/S2/PS (centroide del AOI)."""

    def execute(
        self,
        *,
        project_id: int,
        wkt: str | None,
        s1_dates: list[str],
        s2_dates: list[str],
        ps_dates: list[str],
    ) -> dict[str, Any]:
        from shapely import wkt as shapely_wkt

        empty_sensors = {"s1": [], "s2": [], "ps": []}
        if not wkt:
            return {
                "project_id": project_id,
                "source": "open-meteo",
                "centroid": None,
                "date_range": None,
                "by_sensor": empty_sensors,
                "monthly_source_dates": [],
            }

        try:
            geom = shapely_wkt.loads(wkt)
            c = geom.centroid
            lon = float(c.x)
            lat = float(c.y)
        except Exception as exc:
            raise ValueError(f"No se pudo calcular centroide del AOI: {exc!s}") from exc

        all_dates = sorted({*s1_dates, *s2_dates, *ps_dates})
        if not all_dates:
            return {
                "project_id": project_id,
                "source": "open-meteo",
                "centroid": {"lat": lat, "lon": lon},
                "date_range": None,
                "by_sensor": empty_sensors,
                "monthly_source_dates": [],
            }

        start_date = all_dates[0]
        end_date = all_dates[-1]
        daily_rows = _agroclimate.fetch_open_meteo_daily(lat, lon, start_date, end_date)
        monthly_means = _agroclimate.monthly_means_from_daily(daily_rows)

        return {
            "project_id": project_id,
            "source": "open-meteo",
            "centroid": {"lat": lat, "lon": lon},
            "date_range": {"start": start_date, "end": end_date},
            "by_sensor": {
                "s1": _agroclimate.series_from_scene_dates(s1_dates, monthly_means),
                "s2": _agroclimate.series_from_scene_dates(s2_dates, monthly_means),
                "ps": _agroclimate.series_from_scene_dates(ps_dates, monthly_means),
            },
            "monthly_source_dates": sorted(monthly_means.keys()),
        }
