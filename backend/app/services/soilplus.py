"""
Soil+ DEM / CV / sampling helpers (pure computation + DEM load).

Extracted from ``app.api.v1.preprocess`` so routes stay thin.
"""
from __future__ import annotations

import io
import json
import logging
import math
from pathlib import Path

import numpy as np
import rasterio
from matplotlib import colormaps
from matplotlib.path import Path as MplPath
from PIL import Image
from fastapi import HTTPException
from rasterio.transform import xy
from shapely.geometry import Polygon

from app.api.v1.helpers import _tenant_storage

logger = logging.getLogger(__name__)

_SOILPLUS_DEM_PREFERRED = (
    "band_1.img",
    "band_1.tif",
    "band_1.tiff",
    "band_1.geotiff",
)

_SOILPLUS_DEM_EXTS = {".img", ".tif", ".tiff", ".geotiff"}


def _resolve_soilplus_dem_path(dem_dir: Path) -> Path | None:
    """
    Localiza el DEM de entrada en ``dem/``.

    Prioridad: ``band_1.img`` (legado ENVI), luego ``band_1.tif`` / ``.tiff``,
    y por último cualquier GeoTIFF DEM en la carpeta (p. ej. ``DEM_*.tif``),
    excluyendo salidas ``soilplus_saved_*``.
    """
    dem_dir = Path(dem_dir)
    if not dem_dir.is_dir():
        return None
    for name in _SOILPLUS_DEM_PREFERRED:
        p = dem_dir / name
        if p.is_file():
            return p
    candidates: list[tuple[int, str, Path]] = []
    for p in dem_dir.iterdir():
        if not p.is_file():
            continue
        low = p.name.lower()
        if low.startswith("soilplus_saved_"):
            continue
        if p.suffix.lower() not in _SOILPLUS_DEM_EXTS:
            continue
        # Preferir nombres con "dem" cuando hay varios GeoTIFF sueltos.
        score = 0 if "dem" in low else 1
        candidates.append((score, low, p))
    if not candidates:
        return None
    candidates.sort(key=lambda t: (t[0], t[1]))
    return candidates[0][2]


def _load_soilplus_dem_band1(
    project_id: int, tenant_id: int
) -> tuple[Path, np.ndarray, np.ndarray, rasterio.Affine]:
    dem_dir = _tenant_storage(tenant_id, project_id, "dem")
    dem_path = _resolve_soilplus_dem_path(dem_dir)
    if dem_path is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No existe imagen DEM de entrada para Soil+ en {dem_dir} "
                "(busca band_1.img / band_1.tif o un GeoTIFF DEM)."
            ),
        )
    try:
        with rasterio.open(dem_path) as src:
            arr = src.read(1).astype(np.float64)
            transform = src.transform
            nd = src.nodatavals[0] if src.nodatavals else None
            if nd is not None and np.isfinite(nd):
                arr = np.where(arr == float(nd), np.nan, arr)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"No se pudo leer DEM de entrada: {exc}") from exc
    arr = np.where(np.isfinite(arr), arr, np.nan)
    arr = np.where(arr < 0, 0.0, arr)
    mask = np.isfinite(arr) & (arr > 0)
    if int(np.count_nonzero(mask)) <= 0:
        raise HTTPException(status_code=400, detail="DEM sin píxeles válidos (>0).")
    return dem_path, arr, mask, transform


def _soilplus_aspect_slope_deg(
    arr: np.ndarray, mask: np.ndarray, transform: rasterio.Affine
) -> tuple[np.ndarray, np.ndarray]:
    """
    Aspecto (grados, 0=N, 90=E, horario) y pendiente (grados) con gradiente de NumPy y paso del geotransform.
    """
    res_x = abs(float(transform.a))
    res_y = abs(float(transform.e))
    if res_x <= 0 or res_y <= 0:
        res_x = max(res_x, 1.0)
        res_y = max(res_y, 1.0)
    z = np.where(mask, arr, np.nan)
    gy, gx = np.gradient(z, res_y, res_x)
    slope_deg = np.degrees(np.arctan(np.hypot(gx, gy)))
    aspect_deg = np.degrees(np.arctan2(-gx, gy))
    aspect_deg = np.where(np.isfinite(aspect_deg), (aspect_deg + 360.0) % 360.0, np.nan)
    slope_deg = np.where(mask, slope_deg, np.nan)
    aspect_deg = np.where(mask, aspect_deg, np.nan)
    return aspect_deg, slope_deg


def _soilplus_f123_from_roi_dem(
    arr: np.ndarray,
    mask: np.ndarray,
    eff: np.ndarray,
    transform: rasterio.Affine,
) -> dict[str, float]:
    """
    f1 = DEM en ROI (media de elevación normalizada 0–1 en ROI);
    f2 = aspecto; f3 = pendiente — mismas normalizaciones por min-max en ROI.
    """
    dem_flat = arr[eff].astype(np.float64)
    if dem_flat.size <= 0:
        raise HTTPException(status_code=400, detail="ROI sin píxeles DEM válidos.")
    aspect_map, slope_map = _soilplus_aspect_slope_deg(arr, mask, transform)
    # Calcular derivadas en máscara DEM completa; leer solo ROI
    aspect_flat = aspect_map[eff]
    slope_flat = slope_map[eff]
    aspect_flat = aspect_flat[np.isfinite(aspect_flat)]
    slope_flat = slope_flat[np.isfinite(slope_flat)]
    if aspect_flat.size == 0:
        aspect_flat = np.array([0.0], dtype=np.float64)
    if slope_flat.size == 0:
        slope_flat = np.array([0.0], dtype=np.float64)

    def _mean_minmax(flat: np.ndarray) -> float:
        lo = float(np.min(flat))
        hi = float(np.max(flat))
        den = max(hi - lo, 1e-12)
        return float(np.mean((flat - lo) / den))

    f1 = _mean_minmax(dem_flat)
    f2 = _mean_minmax(aspect_flat)
    f3 = _mean_minmax(slope_flat)
    return {
        "f1": f1,
        "f2": f2,
        "f3": f3,
        "dem_roi_mean": float(np.mean(dem_flat)),
        "dem_roi_min": float(np.min(dem_flat)),
        "dem_roi_max": float(np.max(dem_flat)),
        "aspect_roi_mean_deg": float(
            np.mean(aspect_map[eff][np.isfinite(aspect_map[eff])])
        )
        if np.any(np.isfinite(aspect_map[eff]))
        else 0.0,
        "slope_roi_mean_deg": float(
            np.mean(slope_map[eff][np.isfinite(slope_map[eff])])
        )
        if np.any(np.isfinite(slope_map[eff]))
        else 0.0,
    }


def _soilplus_box_sum(arr2d: np.ndarray, radius: int) -> np.ndarray:
    pad = np.pad(arr2d, ((radius, radius), (radius, radius)), mode="constant", constant_values=0.0)
    integ = np.pad(pad, ((1, 0), (1, 0)), mode="constant", constant_values=0.0).cumsum(axis=0).cumsum(axis=1)
    k = 2 * radius + 1
    return integ[k:, k:] - integ[:-k, k:] - integ[k:, :-k] + integ[:-k, :-k]


def _soilplus_parse_roi_polygon(raw: str | None) -> np.ndarray | None:
    if raw is None or not str(raw).strip():
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"roi_polygon JSON invalido: {exc}") from exc
    if not isinstance(data, list) or len(data) < 3:
        raise HTTPException(status_code=400, detail="roi_polygon requiere al menos 3 vertices [x,y] en pixeles DEM")
    pts: list[list[float]] = []
    for p in data:
        if not isinstance(p, (list, tuple)) or len(p) < 2:
            raise HTTPException(status_code=400, detail="cada vertice roi_polygon debe ser [x,y]")
        pts.append([float(p[0]), float(p[1])])
    return np.asarray(pts, dtype=np.float64)


def _soilplus_polygon_mask(h: int, w: int, verts: np.ndarray) -> np.ndarray:
    if verts.shape[0] < 3:
        return np.zeros((h, w), dtype=bool)
    yy, xx = np.mgrid[0:h, 0:w]
    grid = np.column_stack([xx.ravel(), yy.ravel()])
    path = MplPath(verts, closed=True)
    inside = path.contains_points(grid, radius=0)
    return inside.reshape(h, w)


def _soilplus_resolve_cv_colormap(name: str) -> str:
    key = str(name or "jet").strip().lower()
    aliases = {
        "jet": "jet",
        "spectral": "Spectral",
        "spectral_r": "Spectral_r",
        "turbo": "turbo",
        "viridis": "viridis",
        "plasma": "plasma",
    }
    cmap_id = aliases.get(key, key)
    try:
        colormaps.get_cmap(cmap_id)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=f"Paleta de color no soportada: {name}") from exc
    return cmap_id


def _soilplus_compute_cv(
    arr: np.ndarray,
    mask: np.ndarray,
    window_size: int,
    *,
    stats_mask: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, int]:
    """
    CV local = std/mean en ventana. Solo los píxeles True en ``stats_mask`` (además DEM válido en ``mask``)
    entran en suma, conteo y suma de cuadrados de la ventana. Si ``stats_mask`` es None, se usa ``mask``.
    """
    ws = int(window_size)
    if ws % 2 == 0:
        ws += 1
    r = ws // 2
    incl = mask if stats_mask is None else (stats_mask.astype(bool) & mask)
    filled = np.where(incl, arr, 0.0)
    sum_w = _soilplus_box_sum(filled, r)
    cnt_w = _soilplus_box_sum(incl.astype(np.float64), r)
    sumsq_w = _soilplus_box_sum(filled * filled, r)
    mean_w = np.divide(sum_w, cnt_w, out=np.zeros_like(sum_w), where=cnt_w > 0)
    var_w = np.divide(sumsq_w, cnt_w, out=np.zeros_like(sumsq_w), where=cnt_w > 0) - (mean_w * mean_w)
    var_w = np.maximum(var_w, 0.0)
    std_w = np.sqrt(var_w)
    cv_w = np.divide(std_w, mean_w, out=np.zeros_like(std_w), where=mean_w > 1e-9)
    cv_w = np.where(incl, cv_w, np.nan)
    return cv_w, cv_w[incl], ws


def _normalize_soil_cv_engine(raw: str | None) -> str:
    s = (raw or "fast").strip().lower()
    if s in ("matlab", "mat", "matlab_cv", "matlab-cv"):
        return "matlab"
    return "fast"


def _soilplus_compute_cv_matlab(
    arr: np.ndarray,
    mask: np.ndarray,
    matlab_ws: int,
    *,
    stats_mask: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, int]:
    """
    Réplica de ``CV.m``: ``padarray(dem,[ws,ws],0)``, ventana (2*ws+1)²,
    ``nonzeros`` de la ventana, ``std/mean`` con std muestral (ddof=1).

    El parámetro ``matlab_ws`` es el mismo ``ws`` que en MATLAB (medio ancho);
    la ventana tiene lado ``2*matlab_ws+1`` (p. ej. ``ws=13`` → 27×27), distinto
    del modo ``fast`` donde ``window_size`` es el lado impar en píxeles.
    """
    ws = max(1, int(matlab_ws))
    ks = 2 * ws + 1
    incl = mask if stats_mask is None else (stats_mask.astype(bool) & mask)
    h, wdim = int(arr.shape[0]), int(arr.shape[1])
    dem_in = np.where(mask, arr, 0.0).astype(np.float64, copy=False)
    padded = np.pad(dem_in, ((ws, ws), (ws, ws)), mode="constant", constant_values=0.0)
    cv_w = np.full((h, wdim), np.nan, dtype=np.float64)
    rc = np.argwhere(incl)
    for r, c in rc:
        r = int(r)
        c = int(c)
        if padded[r + ws, c + ws] == 0.0:
            cv_w[r, c] = 0.0
            continue
        win = padded[r : r + ks, c : c + ks]
        nz = win.ravel()
        nz = nz[nz != 0.0]
        if nz.size < 2:
            cv_w[r, c] = 0.0
            continue
        mu = float(np.mean(nz))
        if mu <= 1e-12:
            cv_w[r, c] = 0.0
            continue
        sig = float(np.std(nz, ddof=1))
        cv_w[r, c] = sig / mu
    flat = cv_w[incl].astype(np.float64)
    flat = flat[np.isfinite(flat)]
    return cv_w, flat, ws


def _soilplus_compute_cv_dispatch(
    arr: np.ndarray,
    mask: np.ndarray,
    window_size: int,
    *,
    stats_mask: np.ndarray | None,
    cv_engine: str,
) -> tuple[np.ndarray, np.ndarray, int, dict]:
    """
    CV local: modo ``fast`` (sumas en caja, ventana lado impar) o ``matlab`` (CV.m).

    Para ``matlab``, ``window_size`` se interpreta como ``ws`` (medio radio MATLAB).
    """
    eng = _normalize_soil_cv_engine(cv_engine)
    meta: dict[str, object] = {"cv_engine": eng}
    if eng == "matlab":
        cv_w, vec, mw = _soilplus_compute_cv_matlab(arr, mask, window_size, stats_mask=stats_mask)
        meta["matlab_ws"] = int(window_size)
        meta["cv_window_side_px"] = int(2 * mw + 1)
        return cv_w, vec, mw, meta
    cv_w, vec, ws = _soilplus_compute_cv(arr, mask, window_size, stats_mask=stats_mask)
    meta["fast_window_px"] = int(ws)
    return cv_w, vec, ws, meta


def _soilplus_png_from_array(arr: np.ndarray, mask: np.ndarray) -> bytes:
    vals = arr[mask]
    if vals.size <= 0:
        raise HTTPException(status_code=400, detail="No hay píxeles válidos para render.")
    lo = float(np.nanmin(vals))
    hi = float(np.nanmax(vals))
    den = max(hi - lo, 1e-12)
    norm = np.clip((arr - lo) / den, 0.0, 1.0)
    u8 = np.where(mask, (norm * 255.0).astype(np.uint8), 0)
    rgb = np.stack([u8, u8, u8], axis=-1)
    img = Image.fromarray(rgb, mode="RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _soilplus_png_cv_colormap(arr: np.ndarray, mask: np.ndarray, cmap_name: str) -> bytes:
    """CV en color: min-max en ROI; fuera de máscara transparente (PNG RGBA)."""
    vals = arr[mask]
    if vals.size <= 0:
        raise HTTPException(status_code=400, detail="No hay píxeles válidos para CV en la ROI.")
    lo = float(np.nanmin(vals))
    hi = float(np.nanmax(vals))
    den = max(hi - lo, 1e-12)
    t = np.clip((arr - lo) / den, 0.0, 1.0)
    cmap = colormaps.get_cmap(cmap_name)
    rgba = cmap(t)
    rgb = (np.clip(rgba[:, :, :3], 0.0, 1.0) * 255.0).astype(np.uint8)
    alpha = np.where(mask, 255, 0).astype(np.uint8)
    out = np.dstack((rgb, alpha))
    img = Image.fromarray(out, mode="RGBA")
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _soilplus_png_aspect_masked(aspect_deg: np.ndarray, eff: np.ndarray) -> bytes:
    """Aspecto 0–360° en HSV cíclico; fuera de ROI transparente (PNG RGBA)."""
    finite = eff & np.isfinite(aspect_deg)
    if int(np.count_nonzero(finite)) <= 0:
        raise HTTPException(status_code=400, detail="Sin aspecto válido en la ROI.")
    t = np.where(finite, (np.mod(aspect_deg, 360.0)) / 360.0, 0.0)
    cmap = colormaps.get_cmap("hsv")
    rgba = cmap(t)
    rgb = (np.clip(rgba[:, :, :3], 0.0, 1.0) * 255.0).astype(np.uint8)
    alpha = np.where(finite, 255, 0).astype(np.uint8)
    out = np.dstack((rgb, alpha))
    img = Image.fromarray(out, mode="RGBA")
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _soilplus_png_slope_masked(slope_deg: np.ndarray, eff: np.ndarray) -> bytes:
    """Pendiente en grados, paleta inferno; fuera de ROI transparente (PNG RGBA)."""
    finite = eff & np.isfinite(slope_deg)
    if int(np.count_nonzero(finite)) <= 0:
        raise HTTPException(status_code=400, detail="Sin pendiente válida en la ROI.")
    vals = slope_deg[finite]
    lo = float(np.min(vals))
    hi = float(np.max(vals))
    den = max(hi - lo, 1e-12)
    t = np.clip((slope_deg - lo) / den, 0.0, 1.0)
    t = np.where(finite, t, 0.0)
    cmap = colormaps.get_cmap("inferno")
    rgba = cmap(t)
    rgb = (np.clip(rgba[:, :, :3], 0.0, 1.0) * 255.0).astype(np.uint8)
    alpha = np.where(finite, 255, 0).astype(np.uint8)
    out = np.dstack((rgb, alpha))
    img = Image.fromarray(out, mode="RGBA")
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _soilplus_effective_roi_mask(arr: np.ndarray, mask: np.ndarray, roi_verts: np.ndarray | None) -> np.ndarray:
    if roi_verts is None:
        return mask
    h, w = int(arr.shape[0]), int(arr.shape[1])
    poly = _soilplus_polygon_mask(h, w, roi_verts)
    return mask & poly


def _soilplus_roi_planar_area_m2(
    roi_verts: np.ndarray | None,
    mask: np.ndarray,
    transform: rasterio.Affine,
) -> float:
    """Área en m² si el DEM está en CRS proyectada (típico). Sin polígono: píxeles válidos × tamaño de píxel."""
    pixel_area = abs(float(transform.a) * float(transform.e))
    if roi_verts is None or roi_verts.shape[0] < 3:
        return float(np.count_nonzero(mask) * pixel_area)
    coords: list[tuple[float, float]] = []
    for col, row in roi_verts:
        gx, gy = xy(transform, float(row), float(col), offset="center")
        coords.append((float(gx), float(gy)))
    poly = Polygon(coords)
    if not poly.is_valid:
        poly = poly.buffer(0)
    return float(poly.area)


def _soilplus_eff_pixel_rc_column_major(eff: np.ndarray) -> np.ndarray:
    """Índices (row, col) recorriendo la máscara en orden columna-primero (como I(mask) en MATLAB)."""
    h, w = int(eff.shape[0]), int(eff.shape[1])
    cols = np.repeat(np.arange(w, dtype=np.int64), h)
    rows = np.tile(np.arange(h, dtype=np.int64), w)
    m = eff[rows, cols]
    return np.column_stack([rows[m], cols[m]])


def _soilplus_allocate_samples_per_cluster_dem(
    dem: np.ndarray,
    lab_map: np.ndarray,
    eff: np.ndarray,
    k: int,
    snc: int,
) -> tuple[np.ndarray, np.ndarray, list[int]]:
    """
    Reparto SNComp: snh = n·std/mean del DEM por zona (std muestral); SN = round(SNC·snh/sum(snh)),
    ajustado para que la suma sea exactamente SNC.
    """
    k = int(k)
    snc = int(max(1, snc))
    snh = np.zeros(k, dtype=np.float64)
    pix_counts: list[int] = []
    for h in range(k):
        m = eff & (lab_map == h)
        pc = int(np.count_nonzero(m))
        pix_counts.append(pc)
        sec = dem[m]
        if sec.size == 0:
            continue
        mu = float(np.mean(sec))
        if mu <= 1e-9:
            continue
        std_s = float(np.std(sec, ddof=1)) if sec.size > 1 else 0.0
        snh[h] = float(sec.size) * std_s / mu
    tot = float(np.sum(snh))
    if tot <= 1e-12:
        base = snc // k
        alloc = np.full(k, base, dtype=np.int64)
        for i in range(snc - base * k):
            alloc[i % k] += 1
        return alloc, snh, pix_counts
    raw = snc * snh / tot
    alloc = np.rint(raw).astype(np.int64)
    alloc = np.maximum(alloc, 0)
    diff = int(snc - int(alloc.sum()))
    if diff != 0:
        frac = raw - alloc.astype(np.float64)
        order = np.argsort(-frac) if diff > 0 else np.argsort(frac)
        step = 0
        while diff != 0 and step < k * max(abs(diff), 1) * 4:
            j = int(order[step % k])
            if diff > 0:
                alloc[j] += 1
                diff -= 1
            elif alloc[j] > 0:
                alloc[j] -= 1
                diff += 1
            step += 1
    return alloc.astype(np.int64), snh, pix_counts


def _soilplus_fishnet_origin_1based(window_size: int) -> int:
    """
    Origen MATLAB ``init = round(windowSize/2)`` índices en base 1; ``round``
    aleja ties de cero para positivos (= ``floor(ws/2+0.5)``), sin ser ``numpy.round``.
    """
    ws = float(int(window_size))
    return int(math.floor(ws / 2.0 + 0.5))


def _soilplus_fishnet_candidates(lab_map: np.ndarray, eff: np.ndarray, fishnet_step: int) -> np.ndarray:
    """
    Equivalente a ``fishNet.m``: rejilla desde ``init:step:size`` en base 1; empares
    (Y,X) ordenados como ``labels(y,x)(:)`` (**column-major**), no como ``np.ravel`` C.

    Solo celdas en ``eff`` con etiqueta de zona válida (>= 0).
    """
    h, wdim = lab_map.shape
    w = int(fishnet_step)
    init_1b = max(1, _soilplus_fishnet_origin_1based(w))
    init0 = max(0, init_1b - 1)
    xs = np.arange(init0, wdim, w, dtype=np.int64)
    ys = np.arange(init0, h, w, dtype=np.int64)
    rows_cols: list[tuple[int, int]] = []
    for j in range(xs.shape[0]):
        ccol = int(xs[j])
        for i in range(ys.shape[0]):
            rrow = int(ys[i])
            if not eff[rrow, ccol]:
                continue
            L = lab_map[rrow, ccol]
            if L >= 0:
                rows_cols.append((rrow, ccol))
    if not rows_cols:
        return np.zeros((0, 2), dtype=np.int64)
    return np.array(rows_cols, dtype=np.int64)


def _soilplus_sample_points_hoya_rs(
    dem: np.ndarray,
    aspect_deg: np.ndarray,
    lab_map: np.ndarray,
    eff: np.ndarray,
    alloc: np.ndarray,
    fishnet_step: int,
    *,
    m: float = 2.0,
    seed: int = 42,
) -> list[dict[str, int]]:
    """
    Muestreo fishNet + selectPoints: candidatos en rejilla; por zona, FCM 2D sobre
    covariables DEM y aspecto (0–1 en ROI) y asignación greedy sobre columnas de U
    (mismas filas que candidatos de fishNet en esa zona).
    """
    try:
        import skfuzzy as fuzz
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "Falta la dependencia scikit-fuzzy en el servidor. "
                "Instala scikit-fuzzy (p. ej. pip install scikit-fuzzy==0.4.2). "
                f"Detalle: {exc}"
            ),
        ) from exc

    hh, ww = lab_map.shape
    points_map = np.zeros((hh, ww), dtype=np.uint8)
    for r, c in _soilplus_fishnet_candidates(lab_map, eff, fishnet_step):
        points_map[int(r), int(c)] = 1

    rc_cm = _soilplus_eff_pixel_rc_column_major(eff)
    if rc_cm.size == 0:
        return []
    rs, cs = rc_cm[:, 0], rc_cm[:, 1]
    dem_v = dem[rs, cs].astype(np.float64)
    asp_v = np.nan_to_num(aspect_deg[rs, cs].astype(np.float64), nan=0.0, posinf=0.0, neginf=0.0)
    lo_d, hi_d = float(np.min(dem_v)), float(np.max(dem_v))
    lo_a, hi_a = float(np.min(asp_v)), float(np.max(asp_v))
    den_d = max(hi_d - lo_d, 1e-12)
    den_a = max(hi_a - lo_a, 1e-12)
    f1 = (dem_v - lo_d) / den_d
    f2 = (asp_v - lo_a) / den_a
    features_cm = np.column_stack([f1, f2])
    lab_vec = lab_map[rs, cs]

    k = int(alloc.size)
    for subr in range(k):
        sub_clusters = int(alloc[subr])
        if sub_clusters <= 0:
            continue
        reg = lab_vec == subr
        if not np.any(reg):
            continue
        sub_feat = features_cm[reg]
        n_region = int(sub_feat.shape[0])
        rs_r = rs[reg]
        cs_r = cs[reg]
        sub_pts = np.zeros(n_region, dtype=np.int8)
        for t in range(n_region):
            sub_pts[t] = points_map[int(rs_r[t]), int(cs_r[t])]

        n_cand = int(np.sum(sub_pts == 1))
        if n_cand == 0:
            logger.warning(
                "Soil+ fishNet: zona %s sin candidatos en rejilla; no se ubican %s puntos.",
                subr,
                sub_clusters,
            )
            continue

        c_fcm = max(1, min(sub_clusters, n_region))
        try:
            _cntr, u, _u0, _d, _jm, _p, _fpc = fuzz.cluster.cmeans(
                sub_feat.T,
                c=c_fcm,
                m=float(m),
                error=0.005,
                maxiter=1000,
                init=None,
                seed=int(seed) + subr,
            )
        except Exception:
            logger.warning("Soil+ selectPoints: FCM interno falló en zona %s", subr)
            continue

        coef = u[:, sub_pts == 1]
        if coef.size == 0:
            continue
        work = coef.astype(np.float64).copy()
        selected_local_cols: list[int] = []
        for _it in range(sub_clusters):
            if work.size == 0 or not np.any(work > 1e-18):
                break
            flat_i = int(np.argmax(work))
            rr, cc = np.unravel_index(flat_i, work.shape)
            selected_local_cols.append(int(cc))
            work[rr, :] = 0.0
            work[:, cc] = 0.0

        indx = np.flatnonzero(sub_pts == 1)
        for loc_col in selected_local_cols:
            if loc_col < 0 or loc_col >= len(indx):
                continue
            li = int(indx[loc_col])
            points_map[int(rs_r[li]), int(cs_r[li])] = 2

    ys, xs = np.nonzero(points_map == 2)
    out: list[dict[str, int]] = []
    seq = 0
    for yi, xi in zip(ys.tolist(), xs.tolist()):
        cid = int(lab_map[int(yi), int(xi)])
        out.append({"index": seq, "cluster": cid, "row": int(yi), "col": int(xi)})
        seq += 1
    return out


def _soilplus_cluster_png(labels: np.ndarray, mask: np.ndarray, n_clusters: int) -> bytes:
    palette = np.array(
        [
            [228, 26, 28],
            [55, 126, 184],
            [77, 175, 74],
            [152, 78, 163],
            [255, 127, 0],
            [255, 255, 51],
            [166, 86, 40],
            [247, 129, 191],
            [141, 211, 199],
            [179, 222, 105],
            [128, 177, 211],
            [253, 180, 98],
        ],
        dtype=np.uint8,
    )
    rgb = np.zeros((labels.shape[0], labels.shape[1], 3), dtype=np.uint8)
    rgb[:] = (255, 255, 255)
    valid_labels = np.where(mask, labels, -1)
    for k in range(int(n_clusters)):
        color = palette[k % len(palette)]
        rgb[valid_labels == k] = color
    img = Image.fromarray(rgb, mode="RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _soilplus_saved_variant_slug(cv_engine: str) -> str:
    """Nombre de archivo: ``fast`` vs ``matlab``."""
    return "matlab" if _normalize_soil_cv_engine(cv_engine) == "matlab" else "fast"


def _soilplus_qcomp_from_cv_flat(
    cv_flat: np.ndarray,
    n_clusters: int,
    *,
    m: float = 2.0,
    seed: int = 42,
) -> float:
    """
    Estadístico Q tras FCM sobre el vector CV (valores en ROI): Q = 1 - sum_k n_k var_k / (N var_total),
    con varianza muestral (ddof=1), alineado con el flujo típico de selección de K.
    """
    try:
        import skfuzzy as fuzz
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "Falta la dependencia scikit-fuzzy en el servidor. "
                "En Docker: docker compose exec backend pip install scikit-fuzzy==0.4.2 "
                "o reinicia el backend (pip install -r requirements.txt al arrancar). "
                f"Detalle: {exc}"
            ),
        ) from exc

    cv_flat = np.asarray(cv_flat, dtype=np.float64).ravel()
    if not np.all(np.isfinite(cv_flat)):
        cv_flat = np.nan_to_num(cv_flat, nan=0.0, posinf=0.0, neginf=0.0)
    n_pix = int(cv_flat.size)
    c = int(n_clusters)
    if n_pix < c or c < 2:
        return float("nan")

    def _var_sample(z: np.ndarray) -> float:
        if z.size <= 1:
            return 0.0
        return float(np.var(z, ddof=1))

    nt = float(n_pix) * _var_sample(cv_flat)
    if nt <= 1e-18:
        return float("nan")

    x = cv_flat.reshape(1, -1)
    try:
        _cntr, u, _u0, _d, _jm, _p, _fpc = fuzz.cluster.cmeans(
            x,
            c=c,
            m=float(m),
            error=0.005,
            maxiter=1000,
            init=None,
            seed=int(seed),
        )
    except Exception:
        logger.warning("Q-comp: FCM no convergió o falló para K=%s", c)
        return float("nan")

    labels = np.argmax(u, axis=0)
    nv_sum = 0.0
    for ss in range(c):
        sec = cv_flat[labels == ss]
        if sec.size == 0:
            continue
        nv_sum += float(sec.size) * _var_sample(sec)

    return float(1.0 - nv_sum / nt)


def _soilplus_fcm_labels_from_cv_norm(
    cv_w: np.ndarray,
    eff: np.ndarray,
    n_clusters: int,
    *,
    m: float = 2.0,
) -> np.ndarray:
    """
    FCM sobre valores de CV en la ROI, normalizados por max(CV) en la ROI.

    Mismo orden column-major sobre la ROI que la curva Q y ``_soilplus_sample_points_hoya_rs``
    (`I(mask)` en MATLAB). Usar orden fila-major (np.where) cambia las columnas de entrada
    a ``cmeans`` y con semilla aleatoria altera las particiones respecto al flujo de referencia.
    """
    try:
        import skfuzzy as fuzz
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "Falta la dependencia scikit-fuzzy en el servidor. "
                "En Docker: docker compose exec backend pip install scikit-fuzzy==0.4.2 "
                "o reinicia el backend (pip install -r requirements.txt al arrancar). "
                f"Detalle: {exc}"
            ),
        ) from exc

    rc_cm = _soilplus_eff_pixel_rc_column_major(eff)
    if rc_cm.size == 0:
        raise HTTPException(status_code=400, detail="ROI vacía; FCM no aplicable.")
    rs, cs = rc_cm[:, 0], rc_cm[:, 1]
    vals = cv_w[rs, cs].astype(np.float64)
    if not np.all(np.isfinite(vals)):
        vals = np.nan_to_num(vals, nan=0.0, posinf=0.0, neginf=0.0)
    n_pix = int(vals.size)
    c = int(n_clusters)
    if n_pix < c:
        raise HTTPException(
            status_code=400,
            detail=f"ROI con {n_pix} píxeles: se necesitan al menos K={c} para FCM.",
        )
    vmax = float(np.max(vals))
    if vmax <= 1e-12:
        raise HTTPException(status_code=400, detail="CV nulo o constante en la ROI; FCM no aplicable.")
    x = (vals / vmax).reshape(1, -1)
    try:
        _cntr, u, _u0, _d, _jm, _p, _fpc = fuzz.cluster.cmeans(
            x,
            c=c,
            m=float(m),
            error=0.005,
            maxiter=1000,
            init=None,
            seed=42,
        )
    except Exception as exc:
        logger.exception("FCM (skfuzzy.cmeans) falló")
        raise HTTPException(
            status_code=400,
            detail=f"FCM no convergió o datos inválidos: {exc}",
        ) from exc
    ord = np.argsort(_cntr.ravel())
    u_ord = u[ord, :]
    labels_flat = np.argmax(u_ord, axis=0).astype(np.int16)
    lab_map = np.full(cv_w.shape, -1, dtype=np.int16)
    lab_map[rs, cs] = labels_flat
    return lab_map
