"""SoilPlus + dashboard IA Planet — casos de uso (extraídos del router HTTP)."""
from __future__ import annotations

import io
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.enums import Resampling
from matplotlib import colormaps
from PIL import Image
from sklearn.cluster import KMeans

from app.core.storage_paths import _tenant_storage
from app.services.preprocess_pipeline_variant import (
    is_planetscope_ps_recorte_filename,
    recortes_dir_name,
)
from app.services.soilplus import (
    _load_soilplus_dem_band1,
    _soilplus_allocate_samples_per_cluster_dem,
    _soilplus_aspect_slope_deg,
    _soilplus_cluster_png,
    _soilplus_compute_cv_dispatch,
    _soilplus_eff_pixel_rc_column_major,
    _soilplus_effective_roi_mask,
    _soilplus_f123_from_roi_dem,
    _soilplus_fcm_labels_from_cv_norm,
    _soilplus_parse_roi_polygon,
    _soilplus_png_aspect_masked,
    _soilplus_png_cv_colormap,
    _soilplus_png_from_array,
    _soilplus_png_slope_masked,
    _soilplus_qcomp_from_cv_flat,
    _soilplus_resolve_cv_colormap,
    _soilplus_roi_planar_area_m2,
    _soilplus_sample_points_hoya_rs,
    _soilplus_saved_variant_slug,
)

logger = logging.getLogger(__name__)


def _safe_relative_under(root: Path, p: Path) -> str | None:
    try:
        return p.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None


def pct_stretch01(x: np.ndarray) -> np.ndarray:
    finite = x[np.isfinite(x)]
    if finite.size < 16:
        return np.zeros_like(x, dtype=np.float64)
    lo, hi = np.percentile(finite, [2.0, 98.0])
    if hi <= lo + 1e-9:
        return np.clip(x - lo, 0.0, 1.0)
    return np.clip((x - lo) / (hi - lo), 0.0, 1.0)


def luma_laplace_var_from_rgb(r: np.ndarray, g: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    """Brillo percibencial tras estirado por percentiles y varianza del laplaciano (textura / bordes)."""
    nr = pct_stretch01(r.astype(np.float64))
    ng = pct_stretch01(g.astype(np.float64))
    nb = pct_stretch01(b.astype(np.float64))
    L = 0.299 * nr + 0.587 * ng + 0.114 * nb
    if not np.any(np.isfinite(L)):
        return float("nan"), float("nan")
    c = L[1:-1, 1:-1]
    lap = L[:-2, 1:-1] + L[2:, 1:-1] + L[1:-1, :-2] + L[1:-1, 2:] - 4.0 * c
    return float(np.mean(L[np.isfinite(L)])), float(np.var(lap[np.isfinite(lap)]))


def build_dashboard_ia_planet_integral(
    *,
    project_id: int,
    tenant_id: int,
    max_scenes: int = 36,
) -> dict:
    """Visión por computador subsampleada: NDVI, claros, textura RGB y laplaciano."""
    from app.services.s2_vegetation_indices import sort_key_from_path_or_meta

    rec_kind = recortes_dir_name("ps")
    recortes_root = _tenant_storage(tenant_id, project_id, rec_kind)
    if not recortes_root.is_dir():
        return {
            "scenes": [],
            "summary": {"n_scenes_analyzed": 0, "message": "Sin carpeta recortesPS"},
        }

    candidates: list[tuple[str, Path]] = []
    for p in sorted(recortes_root.rglob("*.tif")):
        if "_cog" in p.name.lower() or not p.is_file():
            continue
        if not is_planetscope_ps_recorte_filename(p.name):
            continue
        if _safe_relative_under(recortes_root, p) is None:
            continue
        try:
            with rasterio.open(p) as src:
                if int(src.count) < 8:
                    continue
        except Exception:
            continue
        sk = sort_key_from_path_or_meta(p, None) or "1900-01-01"
        candidates.append((str(sk), p.resolve()))

    candidates.sort(key=lambda x: (x[0], str(x[1])))
    candidates = candidates[: int(max_scenes)]

    sh = sw = 256
    rows: list[dict] = []
    for sk, p in candidates:
        rel = _safe_relative_under(recortes_root, p)
        try:
            with rasterio.open(p) as src:
                if int(src.count) < 8:
                    continue
                r = src.read(6, out_shape=(sh, sw), resampling=Resampling.average).astype(np.float32)
                ir = src.read(8, out_shape=(sh, sw), resampling=Resampling.average).astype(np.float32)
                g = src.read(4, out_shape=(sh, sw), resampling=Resampling.average).astype(np.float32)
                b_rgb = src.read(2, out_shape=(sh, sw), resampling=Resampling.average).astype(np.float32)
                ndvi = (ir - r) / (ir + r + 1e-6)
                ndvi = np.clip(ndvi, -1, 1)
                valid = np.isfinite(ndvi)
                if not np.any(valid):
                    rows.append({"sort_key": sk, "basename": p.name, "relative_path": rel, "error": "sin pixeles validos"})
                    continue
                v = ndvi[valid]
                gsub = g[valid]
                gmean = float(np.mean(gsub)) + 1e-6
                green_cv = float(np.std(gsub) / gmean)
                luma_mean, lap_var = luma_laplace_var_from_rgb(r, g, b_rgb)
                rows.append(
                    {
                        "sort_key": sk,
                        "basename": p.name,
                        "relative_path": rel,
                        "ndvi_mean": float(np.mean(v)),
                        "ndvi_std": float(np.std(v)),
                        "frac_low_ndvi": float(np.mean(v < 0.22)),
                        "frac_high_ndvi": float(np.mean(v > 0.55)),
                        "green_cv": green_cv,
                        "rgb_luma_mean": luma_mean,
                        "rgb_laplace_var": lap_var,
                        "sample_hw": [int(sh), int(sw)],
                    }
                )
        except Exception as exc:
            rows.append({"sort_key": sk, "basename": p.name, "relative_path": rel, "error": str(exc)[:160]})

    ok = [r for r in rows if "ndvi_mean" in r]
    summary: dict = {"n_scenes_analyzed": len(ok), "n_paths_seen": len(candidates)}
    narrative: list[str] = []
    if len(ok) >= 4:
        ok.sort(key=lambda x: x["sort_key"])
        n = len(ok)
        third = max(1, n // 3)
        early = ok[:third]
        late = ok[n - third :]
        fl_e = float(np.mean([float(x["frac_low_ndvi"]) for x in early]))
        fl_l = float(np.mean([float(x["frac_low_ndvi"]) for x in late]))
        summary["frac_low_ndvi_early_mean"] = fl_e
        summary["frac_low_ndvi_late_mean"] = fl_l
        summary["delta_frac_low_ndvi"] = fl_l - fl_e
        gc_e = float(np.mean([float(x["green_cv"]) for x in early]))
        gc_l = float(np.mean([float(x["green_cv"]) for x in late]))
        summary["green_cv_early_mean"] = gc_e
        summary["green_cv_late_mean"] = gc_l
        summary["delta_green_cv"] = gc_l - gc_e
        lap_e = float(np.mean([float(x["rgb_laplace_var"]) for x in early if np.isfinite(float(x.get("rgb_laplace_var", np.nan)))]))
        lap_l = float(np.mean([float(x["rgb_laplace_var"]) for x in late if np.isfinite(float(x.get("rgb_laplace_var", np.nan)))]))
        if np.isfinite(lap_e) and np.isfinite(lap_l):
            summary["rgb_laplace_early_mean"] = lap_e
            summary["rgb_laplace_late_mean"] = lap_l
            summary["delta_rgb_laplace"] = lap_l - lap_e
        dfl = fl_l - fl_e
        if dfl > 0.04:
            narrative.append(
                f"Proxy de claros/bajo dosel: la fracción de NDVI bajo (<0.22) en malla {sh}×{sw} **aumenta** "
                f"del tramo inicial (μ={fl_e:.3f}) al final (μ={fl_l:.3f}); Δ≈{dfl:+.3f}. "
                "Coherente con **más áreas despejadas o menor cobertura foliar** en escenas recientes; validar en RGB Planet."
            )
        elif dfl < -0.04:
            narrative.append(
                f"La fracción de NDVI bajo **disminuye** entre tramos (Δ≈{dfl:+.3f}), compatible con recuperación "
                "del dosel o menor exposición de suelo en las fechas recientes."
            )
        else:
            narrative.append(
                f"Cambio moderado en fracción de NDVI bajo entre tramos (Δ≈{dfl:+.3f}). "
                "Lucanas o huecos localizados pueden **diluirse** en el promedio agregado; la firma fina sigue apareciendo en la **secuencia RGB** escena a escena."
            )
        if (gc_l - gc_e) > 0.035:
            narrative.append(
                "Mayor variabilidad relativa del canal verde en escenas recientes sugiere **textura más irregular** "
                "(surcos, sombras o dosel menos homogéneo) frente al inicio de la serie."
            )
        dlap = summary.get("delta_rgb_laplace")
        if dlap is not None and np.isfinite(dlap):
            if dlap > 1.2e-4:
                narrative.append(
                    "La energía de borde en la composición RGB (laplaciano del brillo) **sube** en el tramo reciente "
                    "respecto al inicial: suele asociarse a **más discontinuidades finas** en el dosel (huecos, surcos, "
                    "bordes de copas o sombras móviles), coherente con revisión RGB fecha a fecha."
                )
            elif dlap < -1.2e-4:
                narrative.append(
                    "La energía de borde RGB **baja** hacia el final de la serie: imagen algo **más suave** "
                    "(dosel más homogéneo, atmósfera más uniforme o menor contraste escena a escena); contrastar con NDVI."
                )
    elif ok:
        narrative.append(
            f"Solo {len(ok)} escena(s) válidas para el análisis automático; la trayectoria es corta y los contrastes "
            "temporales deben interpretarse con cautela, apoyándose en RGB e índices del dashboard fecha a fecha."
        )
    else:
        narrative.append("No se pudieron calcular estadísticos NDVI en recortes PS (revisar archivos 8 bandas).")

    return {"scenes": rows, "summary": summary, "narrative": narrative}


def execute_save_bundle(
    project_id: int,
    tenant_id: int,
    *,
    window_size: int,
    cv_engine: str,
    n_clusters: int,
    fishnet_step: int,
    roi_polygon: str | None,
    total_samples: int | None,
    cmap: str,
    m: float,
) -> dict[str, object]:
    """
    Pipeline Soil+ completo + escritura JSON y PNG en ``dem/soilplus_saved_{fast|matlab}.*``.
    """
    dem_path, arr, mask, transform = _load_soilplus_dem_band1(project_id, tenant_id)
    verts = _soilplus_parse_roi_polygon(roi_polygon)
    eff = _soilplus_effective_roi_mask(arr, mask, verts)
    if int(np.count_nonzero(eff)) <= 0:
        raise ValueError("ROI vacía.")
    area_m2 = _soilplus_roi_planar_area_m2(verts, mask, transform)
    area_ha = area_m2 / 10000.0
    inferred = total_samples is None
    if total_samples is not None:
        snc = int(total_samples)
    else:
        snc = max(1, int(round(area_ha))) if area_ha > 0 else 60
    stats_mask = eff if verts is not None else None
    cv_w, _, _wu, cv_run_meta = _soilplus_compute_cv_dispatch(
        arr, mask, window_size, stats_mask=stats_mask, cv_engine=cv_engine
    )
    lab_map = _soilplus_fcm_labels_from_cv_norm(cv_w, eff, int(n_clusters), m=m)
    alloc, snh, pix_c = _soilplus_allocate_samples_per_cluster_dem(arr, lab_map, eff, int(n_clusters), snc)
    aspect_deg, slope_deg = _soilplus_aspect_slope_deg(arr, mask, transform)
    sample_points = _soilplus_sample_points_hoya_rs(
        arr,
        aspect_deg,
        lab_map,
        eff,
        alloc,
        int(fishnet_step),
        m=m,
        seed=42,
    )
    nk = int(n_clusters)
    actual = np.zeros(nk, dtype=np.int64)
    for pt in sample_points:
        cid = int(pt.get("cluster", -1))
        if 0 <= cid < nk:
            actual[cid] += 1
    placed = int(actual.sum())

    rc_cm = _soilplus_eff_pixel_rc_column_major(eff)
    cv_flat = cv_w[rc_cm[:, 0], rc_cm[:, 1]].astype(np.float64)
    if not np.all(np.isfinite(cv_flat)):
        cv_flat = np.nan_to_num(cv_flat, nan=0.0, posinf=0.0, neginf=0.0)
    vmax = float(np.max(cv_flat))
    if vmax > 1e-12:
        cv_flat = cv_flat / vmax

    ks_q: list[int] = []
    q_list: list[float | None] = []
    for k in range(2, 12):
        ks_q.append(int(k))
        qv = _soilplus_qcomp_from_cv_flat(cv_flat, k, m=float(m), seed=42)
        q_list.append(float(qv) if np.isfinite(qv) else None)

    cmap_id = _soilplus_resolve_cv_colormap(cmap)
    dem_png = _soilplus_png_from_array(arr, mask)
    cv_png = _soilplus_png_cv_colormap(cv_w, eff, cmap_id)
    aspect_png = _soilplus_png_aspect_masked(aspect_deg, eff)
    slope_png = _soilplus_png_slope_masked(slope_deg, eff)
    fcm_png = _soilplus_cluster_png(lab_map, eff, int(n_clusters))

    slug = _soilplus_saved_variant_slug(cv_engine)
    ts = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

    roi_applied = bool(verts is not None)
    dem_mean = float(np.mean(arr[mask])) if np.count_nonzero(mask) else 0.0
    dem_roi_mean = float(np.mean(arr[eff])) if np.count_nonzero(eff) else 0.0

    bundle: dict[str, object] = {
        "saved_at": ts,
        "project_id": int(project_id),
        "cv_engine_slug": slug,
        "cv_run": cv_run_meta,
        "window_size": int(window_size),
        "n_clusters": int(n_clusters),
        "fishnet_step": int(fishnet_step),
        "roi_polygon_applied": roi_applied,
        "roi_polygon": roi_polygon if roi_applied else None,
        "roi_pixel_count": int(np.count_nonzero(eff)),
        "polygon_area_m2": float(area_m2),
        "polygon_area_ha": float(area_ha),
        "total_samples": int(snc),
        "total_samples_placed": placed,
        "total_samples_inferred": inferred,
        "samples_requested_per_cluster": [int(x) for x in alloc],
        "samples_per_cluster": [int(x) for x in actual],
        "pixels_per_cluster": pix_c,
        "dem_weight_per_cluster": [float(x) for x in snh],
        "raster_shape": {"height": int(arr.shape[0]), "width": int(arr.shape[1])},
        "sample_points": sample_points,
        "q_curve": {"k_values": ks_q, "q_values": q_list, "m": float(m)},
        "dem_input_image_path": str(dem_path),
        "dem_mean_snapshot": dem_mean,
        "dem_roi_mean_snapshot": dem_roi_mean,
        "cv_mean_snapshot": float(np.mean(cv_w[np.isfinite(cv_w)])) if np.any(np.isfinite(cv_w)) else 0.0,
        "cv_colormap": str(cmap),
        "fc_m": float(m),
    }
    terr: dict[str, float] = {}
    try:
        stats = _soilplus_f123_from_roi_dem(arr, mask, eff, transform)
        for key in ("f1", "f2", "f3"):
            if key in stats:
                terr[key] = float(stats[key])
        for key in ("aspect_roi_mean_deg", "slope_roi_mean_deg"):
            if key in stats:
                terr[key] = float(stats[key])
    except Exception:
        pass
    bundle["terrain"] = terr

    root = _tenant_storage(tenant_id, project_id, "dem")
    root.mkdir(parents=True, exist_ok=True)
    pref = f"soilplus_saved_{slug}"
    (root / f"{pref}.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    for kind, blob in (
        ("dem", dem_png),
        ("cv", cv_png),
        ("fcm", fcm_png),
        ("aspect", aspect_png),
        ("slope", slope_png),
    ):
        (root / f"{pref}_{kind}.png").write_bytes(blob)
    return bundle

def compute_ps_soilplus_f1_exact(*, project_id: int, tenant_id: int) -> dict:
    """f1 = media global banda 8 en GeoTIFF válidos de recortesPS/."""

    rec_root = _tenant_storage(tenant_id, project_id, recortes_dir_name("ps"))
    if not rec_root.is_dir():
        raise LookupError("No existe recortesPS/ para este proyecto.")

    total_sum = 0.0
    total_count = 0
    used_files = 0
    skipped_non_ps_name = 0
    skipped_not_8band = 0
    skipped_open_error = 0

    for p in sorted(rec_root.rglob("*.tif")):
        if "_cog" in p.name.lower() or not p.is_file():
            continue
        if not is_planetscope_ps_recorte_filename(p.name):
            skipped_non_ps_name += 1
            continue
        try:
            with rasterio.open(p) as src:
                if int(src.count) < 8:
                    skipped_not_8band += 1
                    continue
                band8 = src.read(8).astype(np.float64)
                nd = src.nodatavals[7] if src.nodatavals and len(src.nodatavals) >= 8 else None
                if nd is not None and np.isfinite(nd):
                    band8 = np.where(band8 == float(nd), np.nan, band8)
                band8 = np.where(np.isfinite(band8), band8, np.nan)
                valid = np.isfinite(band8)
                n_valid = int(np.count_nonzero(valid))
                if n_valid <= 0:
                    continue
                total_sum += float(np.nansum(band8))
                total_count += n_valid
                used_files += 1
        except Exception:
            skipped_open_error += 1
            continue

    if total_count <= 0:
        raise LookupError("No se encontraron píxeles válidos de banda 8 en recortesPS/.")

    return {
        "project_id": int(project_id),
        "f1_band8_mean": total_sum / total_count,
        "valid_pixel_count": total_count,
        "files_used": used_files,
        "files_skipped": {
            "non_ps_filename": skipped_non_ps_name,
            "less_than_8_bands": skipped_not_8band,
            "open_error": skipped_open_error,
        },
        "source_dir": "recortesPS",
        "method": "global_mean_of_band_8_across_all_valid_pixels",
    }

def png_dem_valid_only(arr: np.ndarray, mask: np.ndarray) -> Image.Image:
    """DEM en escala de grises solo donde hay valores; fondo transparente."""
    vals = arr[mask]
    if vals.size <= 0:
        raise ValueError("No hay píxeles DEM válidos.")
    lo = float(np.nanmin(vals))
    hi = float(np.nanmax(vals))
    den = max(hi - lo, 1e-12)
    norm = np.zeros(arr.shape, dtype=np.float64)
    norm[mask] = np.clip((vals - lo) / den, 0.0, 1.0)
    u8 = (norm * 255.0).astype(np.uint8)
    rgb = np.stack([u8, u8, u8], axis=-1)
    alpha = np.where(mask, 255, 0).astype(np.uint8)
    out = np.dstack((rgb, alpha))
    return Image.fromarray(out, mode="RGBA")


def png_dem_elevation_colorbar(arr: np.ndarray, mask: np.ndarray, *, max_dim: int = 420) -> Image.Image:
    """DEM con paleta de alturas + barra de color (unidades de altura)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    vals = arr[mask]
    if vals.size <= 0:
        raise ValueError("No hay píxeles DEM válidos.")
    lo = float(np.nanmin(vals))
    hi = float(np.nanmax(vals))
    data = np.ma.array(arr, mask=~mask)
    fig_w = max(4.2, max_dim / 100.0)
    fig_h = max(3.6, (max_dim * 0.85) / 100.0)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=120)
    try:
        cmap = colormaps["terrain"].copy()
    except Exception:
        cmap = colormaps.get_cmap("terrain")
    try:
        cmap.set_bad(color=(1.0, 1.0, 1.0, 0.0))
    except Exception:
        pass
    im = ax.imshow(data, cmap=cmap, vmin=lo, vmax=hi, interpolation="nearest")
    ax.set_axis_off()
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("Altura (m)", fontsize=10)
    cbar.ax.tick_params(labelsize=8)
    fig.tight_layout(pad=0.2)
    buf = io.BytesIO()
    fig.savefig(buf, format="PNG", dpi=140, bbox_inches="tight", facecolor="white", transparent=False)
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf).convert("RGBA")


def upscale_image(img: Image.Image, max_dim: int = 420, *, nearest: bool = False) -> Image.Image:
    w, h = img.size
    if max(w, h) <= 0:
        return img
    scale = float(max_dim) / max(w, h)
    if scale <= 1.01:
        return img
    resample_mod = getattr(Image, "Resampling", Image)
    resample = resample_mod.NEAREST if nearest else resample_mod.LANCZOS
    return img.resize((max(1, int(round(w * scale))), max(1, int(round(h * scale)))), resample)


def overlay_sample_triangles(
    img: Image.Image,
    sample_points: list | None,
    *,
    grid_h: int,
    grid_w: int,
) -> Image.Image:
    """Dibuja triángulos de muestreo (mismo criterio visual que Smart Soil) sobre el cluster."""
    from PIL import ImageDraw

    points = sample_points if isinstance(sample_points, list) else []
    if not points or grid_h <= 0 or grid_w <= 0:
        return img

    out = img.convert("RGBA")
    out_w, out_h = out.size
    sx = out_w / float(grid_w)
    sy = out_h / float(grid_h)
    radius = max(6, int(round(min(sx, sy) * 0.42)))
    draw = ImageDraw.Draw(out)
    for point in points:
        try:
            col = float(point["col"])
            row = float(point["row"])
        except (KeyError, TypeError, ValueError):
            continue
        x = (col + 0.5) * sx
        y = (row + 0.5) * sy
        triangle = [
            (x, y - radius),
            (x - radius * 0.92, y + radius * 0.58),
            (x + radius * 0.92, y + radius * 0.58),
        ]
        # Amarillo alto contraste (como en Smart Soil / Markdown) para no fundirse con el cluster.
        draw.polygon(triangle, fill=(255, 241, 118, 240), outline=(255, 255, 255, 255))
        # Contorno oscuro fino para legibilidad sobre zonas claras.
        draw.line(triangle + [triangle[0]], fill=(40, 40, 40, 220), width=max(1, radius // 5))
    return out


def label_panel(img: Image.Image, title: str, cell_w: int, cell_h: int) -> Image.Image:
    """Centra el panel en una celda blanca con título superior."""
    from PIL import ImageDraw, ImageFont

    canvas = Image.new("RGBA", (cell_w, cell_h), (255, 255, 255, 255))
    title_h = 28
    avail_w = cell_w - 16
    avail_h = cell_h - title_h - 16
    panel = img.convert("RGBA")
    scale = min(avail_w / max(panel.width, 1), avail_h / max(panel.height, 1), 1.0)
    if scale < 0.999:
        resample = getattr(Image, "Resampling", Image).LANCZOS
        panel = panel.resize(
            (max(1, int(panel.width * scale)), max(1, int(panel.height * scale))),
            resample,
        )
    x0 = (cell_w - panel.width) // 2
    y0 = title_h + (avail_h - panel.height) // 2
    canvas.alpha_composite(panel, (x0, y0))
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 14)
    except OSError:
        font = ImageFont.load_default()
    draw.text((10, 6), title, fill=(35, 55, 40, 255), font=font)
    return canvas


def build_landing_mosaic(
    project_id: int,
    tenant_id: int,
    *,
    variant: str,
) -> bytes:
    """
    Mosaico 2×2 para la landing:
    1.1 DEM (solo valores válidos) | 1.2 DEM paleta de alturas + barra
    2.1 CV                        | 2.2 Clusters Agrogeofísica
    """
    vk = variant.strip().lower()
    if vk not in ("fast", "matlab"):
        raise ValueError("variant debe ser fast o matlab")
    jp = _tenant_storage(tenant_id, project_id, "dem") / f"soilplus_saved_{vk}.json"
    if not jp.is_file():
        raise LookupError(f"No hay Soil+ guardado ({vk})")
    try:
        meta = json.loads(jp.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"JSON ilegible: {exc}") from exc

    dem_path, arr, mask, _transform = _load_soilplus_dem_band1(project_id, tenant_id)
    _ = dem_path
    window_size = int(meta.get("window_size") or 3)
    n_clusters = int(meta.get("n_clusters") or 4)
    cv_engine = "matlab" if vk == "matlab" else "fast"
    roi_polygon = meta.get("roi_polygon") if meta.get("roi_polygon_applied") else None
    verts = _soilplus_parse_roi_polygon(roi_polygon if isinstance(roi_polygon, str) else None)
    eff = _soilplus_effective_roi_mask(arr, mask, verts)
    if int(np.count_nonzero(eff)) <= 0:
        raise ValueError("ROI vacía para mosaico Soil+.")

    stats_mask = eff if verts is not None else None
    cv_w, _, _wu, _cv_meta = _soilplus_compute_cv_dispatch(
        arr, mask, window_size, stats_mask=stats_mask, cv_engine=cv_engine
    )
    lab_map = _soilplus_fcm_labels_from_cv_norm(cv_w, eff, int(n_clusters), m=2.0)

    dem_gray = upscale_image(png_dem_valid_only(arr, mask), 420, nearest=True)
    dem_elev = png_dem_elevation_colorbar(arr, mask, max_dim=420)
    cv_img = upscale_image(
        Image.open(io.BytesIO(_soilplus_png_cv_colormap(cv_w, eff, "jet"))).convert("RGBA"),
        420,
    )
    cluster_img = upscale_image(
        Image.open(io.BytesIO(_soilplus_cluster_png(lab_map, eff, int(n_clusters)))).convert("RGBA"),
        420,
        nearest=True,
    )
    shape = meta.get("raster_shape") or {}
    grid_h = int(shape.get("height") or lab_map.shape[0])
    grid_w = int(shape.get("width") or lab_map.shape[1])
    cluster_img = overlay_sample_triangles(
        cluster_img,
        meta.get("sample_points"),
        grid_h=grid_h,
        grid_w=grid_w,
    )

    cell_w, cell_h = 520, 460
    gap = 12
    panels = [
        label_panel(dem_gray, "1.1 DEM (valores válidos)", cell_w, cell_h),
        label_panel(dem_elev, "1.2 DEM (altura)", cell_w, cell_h),
        label_panel(cv_img, "2.1 CV", cell_w, cell_h),
        label_panel(cluster_img, "2.2 Clusters (puntos de muestreo)", cell_w, cell_h),
    ]
    mosaic = Image.new("RGB", (cell_w * 2 + gap * 3, cell_h * 2 + gap * 3), (250, 251, 248))
    positions = [(gap, gap), (gap * 2 + cell_w, gap), (gap, gap * 2 + cell_h), (gap * 2 + cell_w, gap * 2 + cell_h)]
    for panel, (x, y) in zip(panels, positions):
        mosaic.paste(panel.convert("RGB"), (x, y))
    buf = io.BytesIO()
    mosaic.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def dem_input_stats(
    *,
    project_id: int,
    tenant_id: int,
    window_size: int = 13,
    cv_engine: str = "fast",
    roi_polygon: str | None = None,
) -> dict:
    try:
        dem_path, arr, mask, transform = _load_soilplus_dem_band1(project_id, tenant_id)
        verts = _soilplus_parse_roi_polygon(roi_polygon)
        eff = _soilplus_effective_roi_mask(arr, mask, verts)
        n_valid = int(np.count_nonzero(mask))
        n_roi = int(np.count_nonzero(eff))
        vals = arr[mask]
        vals_roi = arr[eff] if n_roi else np.array([], dtype=np.float64)
        stats_mask = eff if verts is not None else None
        _cv_map, cv_for_stats, _ws_use, cv_run_meta = _soilplus_compute_cv_dispatch(
            arr, mask, window_size, stats_mask=stats_mask, cv_engine=cv_engine
        )
        area_m2 = _soilplus_roi_planar_area_m2(verts, mask, transform)
        area_ha = area_m2 / 10000.0
        suggested_snc = max(1, int(round(area_ha))) if area_ha > 0 else 60
        return {
            "project_id": int(project_id),
            "input_image_path": str(dem_path),
            "window_size": int(window_size),
            "cv_run": cv_run_meta,
            "width": int(arr.shape[1]),
            "height": int(arr.shape[0]),
            "valid_pixel_count": n_valid,
            "roi_pixel_count": n_roi,
            "roi_polygon_applied": bool(verts is not None),
            "polygon_area_m2": float(area_m2),
            "polygon_area_ha": float(area_ha),
            "suggested_sample_count": int(suggested_snc),
            "dem_mean": float(np.mean(vals)),
            "dem_std": float(np.std(vals)),
            "dem_min": float(np.min(vals)),
            "dem_max": float(np.max(vals)),
            "dem_roi_mean": float(np.mean(vals_roi)) if vals_roi.size else 0.0,
            "dem_roi_std": float(np.std(vals_roi)) if vals_roi.size else 0.0,
            "cv_mean": float(np.mean(cv_for_stats)) if cv_for_stats.size else 0.0,
            "cv_var": float(np.var(cv_for_stats)) if cv_for_stats.size else 0.0,
            "method": "band1_dem_values_cleaned_negatives_to_zero_mask_gt_zero",
        }
    except (LookupError, ValueError):
        raise
    except Exception as exc:
        raise ValueError(f"No se pudo leer DEM de entrada: {exc}") from exc


def f123_terrain(*, project_id: int, tenant_id: int, roi_polygon: str | None = None) -> dict:
    _path, arr, mask, transform = _load_soilplus_dem_band1(project_id, tenant_id)
    verts = _soilplus_parse_roi_polygon(roi_polygon)
    eff = _soilplus_effective_roi_mask(arr, mask, verts)
    if int(np.count_nonzero(eff)) <= 0:
        raise ValueError(
            "ROI vacía: define un polígono válido sobre el DEM o omite roi_polygon para usar toda la máscara."
        )
    stats = _soilplus_f123_from_roi_dem(arr, mask, eff, transform)
    return {
        "project_id": int(project_id),
        "roi_polygon_applied": bool(verts is not None),
        "roi_pixel_count": int(np.count_nonzero(eff)),
        **stats,
        "method": "dem_roi_f1_aspect_f2_slope_f3_minmax_mean",
    }


def sampling_plan(
    *,
    project_id: int,
    tenant_id: int,
    window_size: int = 13,
    cv_engine: str = "fast",
    n_clusters: int = 4,
    fishnet_step: int = 5,
    roi_polygon: str | None = None,
    total_samples: int | None = None,
) -> dict:
    _, arr, mask, transform = _load_soilplus_dem_band1(project_id, tenant_id)
    verts = _soilplus_parse_roi_polygon(roi_polygon)
    eff = _soilplus_effective_roi_mask(arr, mask, verts)
    if int(np.count_nonzero(eff)) <= 0:
        raise ValueError(
            "ROI vacía: define un polígono o omite roi_polygon para usar toda la máscara DEM."
        )
    area_m2 = _soilplus_roi_planar_area_m2(verts, mask, transform)
    area_ha = area_m2 / 10000.0
    inferred = total_samples is None
    if total_samples is not None:
        snc = int(total_samples)
    else:
        snc = max(1, int(round(area_ha))) if area_ha > 0 else 60
    stats_mask = eff if verts is not None else None
    cv_w, _, _wu, cv_run_meta = _soilplus_compute_cv_dispatch(
        arr, mask, window_size, stats_mask=stats_mask, cv_engine=cv_engine
    )
    lab_map = _soilplus_fcm_labels_from_cv_norm(cv_w, eff, int(n_clusters), m=2.0)
    alloc, snh, pix_c = _soilplus_allocate_samples_per_cluster_dem(
        arr, lab_map, eff, int(n_clusters), snc
    )
    aspect_deg, _slope_unused = _soilplus_aspect_slope_deg(arr, mask, transform)
    sample_points = _soilplus_sample_points_hoya_rs(
        arr, aspect_deg, lab_map, eff, alloc, int(fishnet_step), m=2.0, seed=42
    )
    nk = int(n_clusters)
    actual = np.zeros(nk, dtype=np.int64)
    for pt in sample_points:
        cid = int(pt.get("cluster", -1))
        if 0 <= cid < nk:
            actual[cid] += 1
    placed = int(actual.sum())
    return {
        "project_id": int(project_id),
        "window_size": int(window_size),
        "cv_run": cv_run_meta,
        "n_clusters": int(n_clusters),
        "fishnet_step": int(fishnet_step),
        "roi_polygon_applied": bool(verts is not None),
        "roi_pixel_count": int(np.count_nonzero(eff)),
        "polygon_area_m2": float(area_m2),
        "polygon_area_ha": float(area_ha),
        "total_samples": int(snc),
        "total_samples_placed": placed,
        "total_samples_inferred": inferred,
        "samples_requested_per_cluster": [int(x) for x in alloc],
        "samples_per_cluster": [int(x) for x in actual],
        "pixels_per_cluster": pix_c,
        "dem_weight_per_cluster": [float(x) for x in snh],
        "raster_shape": {"height": int(arr.shape[0]), "width": int(arr.shape[1])},
        "sample_points": sample_points,
    }


def saved_summary(*, project_id: int, tenant_id: int) -> dict:
    root = _tenant_storage(tenant_id, project_id, "dem")
    out: dict[str, dict[str, object] | None] = {}
    for slug in ("fast", "matlab"):
        jp = root / f"soilplus_saved_{slug}.json"
        if not jp.is_file():
            out[slug] = None
            continue
        try:
            data = json.loads(jp.read_text(encoding="utf-8"))
        except Exception:
            out[slug] = {"error": "bad_json"}
            continue
        out[slug] = {
            "saved_at": data.get("saved_at"),
            "cv_run": data.get("cv_run"),
            "window_size": data.get("window_size"),
            "n_clusters": data.get("n_clusters"),
            "total_samples": data.get("total_samples"),
            "total_samples_placed": data.get("total_samples_placed"),
            "fishnet_step": data.get("fishnet_step"),
        }
    return {"project_id": int(project_id), "variants": out}


def saved_json(*, project_id: int, tenant_id: int, variant: str = "fast") -> dict:
    vk = variant.strip().lower()
    if vk not in ("fast", "matlab"):
        raise ValueError("variant debe ser fast o matlab")
    jp = _tenant_storage(tenant_id, project_id, "dem") / f"soilplus_saved_{vk}.json"
    if not jp.is_file():
        raise LookupError("No hay Soil+ guardado para esta variante")
    try:
        return json.loads(jp.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"JSON ilegible: {exc}") from exc


def saved_img_path(*, project_id: int, tenant_id: int, variant: str = "fast", kind: str = "dem") -> Path:
    vk = variant.strip().lower()
    if vk not in ("fast", "matlab"):
        raise ValueError("variant debe ser fast o matlab")
    kd = kind.strip().lower()
    if kd not in ("dem", "cv", "fcm", "aspect", "slope"):
        raise ValueError("kind no soportado")
    path_png = _tenant_storage(tenant_id, project_id, "dem") / f"soilplus_saved_{vk}_{kd}.png"
    if not path_png.is_file():
        raise LookupError("Imagen guardada no encontrada")
    return path_png


def dem_preview_png(*, project_id: int, tenant_id: int) -> bytes:
    dem_path, arr, mask, _ = _load_soilplus_dem_band1(project_id, tenant_id)
    _ = dem_path
    return _soilplus_png_from_array(arr, mask)


def cv_preview_png(
    *,
    project_id: int,
    tenant_id: int,
    window_size: int = 13,
    cv_engine: str = "fast",
    roi_polygon: str | None = None,
    cmap: str = "jet",
) -> bytes:
    _, arr, mask, _ = _load_soilplus_dem_band1(project_id, tenant_id)
    verts = _soilplus_parse_roi_polygon(roi_polygon)
    eff = _soilplus_effective_roi_mask(arr, mask, verts)
    if int(np.count_nonzero(eff)) <= 0:
        raise ValueError(
            "ROI vacia: dibuja un polígono dentro del DEM valido o deja roi_polygon vacio."
        )
    cmap_id = _soilplus_resolve_cv_colormap(cmap)
    stats_mask = eff if verts is not None else None
    cv_w, _, _ws_ignore, _meta = _soilplus_compute_cv_dispatch(
        arr, mask, window_size, stats_mask=stats_mask, cv_engine=cv_engine
    )
    return _soilplus_png_cv_colormap(cv_w, eff, cmap_id)


def aspect_preview_png(*, project_id: int, tenant_id: int, roi_polygon: str | None = None) -> bytes:
    _, arr, mask, transform = _load_soilplus_dem_band1(project_id, tenant_id)
    verts = _soilplus_parse_roi_polygon(roi_polygon)
    eff = _soilplus_effective_roi_mask(arr, mask, verts)
    if int(np.count_nonzero(eff)) <= 0:
        raise ValueError(
            "ROI vacía: define un polígono o omite roi_polygon para usar toda la máscara DEM."
        )
    aspect_deg, _slope = _soilplus_aspect_slope_deg(arr, mask, transform)
    return _soilplus_png_aspect_masked(aspect_deg, eff)


def slope_preview_png(*, project_id: int, tenant_id: int, roi_polygon: str | None = None) -> bytes:
    _, arr, mask, transform = _load_soilplus_dem_band1(project_id, tenant_id)
    verts = _soilplus_parse_roi_polygon(roi_polygon)
    eff = _soilplus_effective_roi_mask(arr, mask, verts)
    if int(np.count_nonzero(eff)) <= 0:
        raise ValueError(
            "ROI vacía: define un polígono o omite roi_polygon para usar toda la máscara DEM."
        )
    _aspect, slope_deg = _soilplus_aspect_slope_deg(arr, mask, transform)
    return _soilplus_png_slope_masked(slope_deg, eff)


def q_curve(
    *,
    project_id: int,
    tenant_id: int,
    window_size: int = 13,
    cv_engine: str = "fast",
    k_min: int = 2,
    k_max: int = 11,
    roi_polygon: str | None = None,
    m: float = 2.0,
) -> dict:
    if k_max < k_min:
        raise ValueError("k_max debe ser >= k_min")
    _, arr, mask, _ = _load_soilplus_dem_band1(project_id, tenant_id)
    verts = _soilplus_parse_roi_polygon(roi_polygon)
    eff = _soilplus_effective_roi_mask(arr, mask, verts)
    if int(np.count_nonzero(eff)) <= 0:
        raise ValueError(
            "ROI vacía: define un polígono o omite roi_polygon para usar toda la máscara DEM."
        )
    stats_mask = eff if verts is not None else None
    cv_w, _, _wu, cv_run_meta = _soilplus_compute_cv_dispatch(
        arr, mask, window_size, stats_mask=stats_mask, cv_engine=cv_engine
    )
    rc_cm = _soilplus_eff_pixel_rc_column_major(eff)
    cv_flat = cv_w[rc_cm[:, 0], rc_cm[:, 1]].astype(np.float64)
    if not np.all(np.isfinite(cv_flat)):
        cv_flat = np.nan_to_num(cv_flat, nan=0.0, posinf=0.0, neginf=0.0)
    vmax = float(np.max(cv_flat))
    if vmax > 1e-12:
        cv_flat = cv_flat / vmax
    ks: list[int] = []
    q_list: list[float | None] = []
    for k in range(int(k_min), int(k_max) + 1):
        ks.append(int(k))
        qv = _soilplus_qcomp_from_cv_flat(cv_flat, k, m=float(m), seed=42)
        q_list.append(None if not np.isfinite(qv) else float(qv))
    return {
        "project_id": int(project_id),
        "window_size": int(window_size),
        "cv_run": cv_run_meta,
        "m": float(m),
        "k_values": ks,
        "q_values": q_list,
    }


def fcm_cv_preview_png(
    *,
    project_id: int,
    tenant_id: int,
    window_size: int = 13,
    cv_engine: str = "fast",
    n_clusters: int = 4,
    roi_polygon: str | None = None,
    m: float = 2.0,
) -> bytes:
    _, arr, mask, _ = _load_soilplus_dem_band1(project_id, tenant_id)
    verts = _soilplus_parse_roi_polygon(roi_polygon)
    eff = _soilplus_effective_roi_mask(arr, mask, verts)
    if int(np.count_nonzero(eff)) <= 0:
        raise ValueError(
            "ROI vacía: define un polígono en el DEM o deja roi_polygon vacío para usar toda la máscara."
        )
    stats_mask = eff if verts is not None else None
    cv_w, _, _wu, _meta = _soilplus_compute_cv_dispatch(
        arr, mask, window_size, stats_mask=stats_mask, cv_engine=cv_engine
    )
    lab_map = _soilplus_fcm_labels_from_cv_norm(cv_w, eff, int(n_clusters), m=m)
    return _soilplus_cluster_png(lab_map, eff, int(n_clusters))


def elbow_curve(
    *,
    project_id: int,
    tenant_id: int,
    k_min: int = 2,
    k_max: int = 10,
    sample_max: int = 20000,
) -> dict:
    if k_max < k_min:
        raise ValueError("k_max debe ser >= k_min")
    _, arr, mask, _ = _load_soilplus_dem_band1(project_id, tenant_id)
    x = arr[mask].reshape(-1, 1).astype(np.float64)
    n = x.shape[0]
    if n > sample_max:
        rng = np.random.default_rng(42)
        idx = rng.choice(n, size=int(sample_max), replace=False)
        x = x[idx]
    ks: list[int] = []
    wcss: list[float] = []
    for k in range(int(k_min), int(k_max) + 1):
        km = KMeans(n_clusters=k, random_state=42, n_init=10)
        km.fit(x)
        ks.append(k)
        wcss.append(float(km.inertia_))
    elbow_k = ks[0]
    if len(ks) >= 3:
        x0, y0 = ks[0], wcss[0]
        x1, y1 = ks[-1], wcss[-1]
        den = ((y1 - y0) ** 2 + (x1 - x0) ** 2) ** 0.5
        if den > 0:
            dmax = -1.0
            for k, y in zip(ks[1:-1], wcss[1:-1]):
                d = abs((y1 - y0) * k - (x1 - x0) * y + x1 * y0 - y1 * x0) / den
                if d > dmax:
                    dmax = d
                    elbow_k = k
    return {
        "project_id": int(project_id),
        "source": "dem/(band_1.img|band_1.tif|DEM_*.tif)",
        "ks": ks,
        "wcss": wcss,
        "elbow_k": elbow_k,
        "sample_size": int(x.shape[0]),
    }


def kmeans_cluster_preview_png(
    *,
    project_id: int,
    tenant_id: int,
    n_clusters: int = 4,
    sample_max: int = 20000,
) -> bytes:
    _, arr, mask, _ = _load_soilplus_dem_band1(project_id, tenant_id)
    x = arr[mask].reshape(-1, 1).astype(np.float64)
    n = x.shape[0]
    if n > sample_max:
        rng = np.random.default_rng(42)
        idx = rng.choice(n, size=int(sample_max), replace=False)
        x_fit = x[idx]
    else:
        x_fit = x
    km = KMeans(n_clusters=int(n_clusters), random_state=42, n_init=10)
    km.fit(x_fit)
    all_labels = km.predict(x).astype(np.int16)
    lab_map = np.full(arr.shape, -1, dtype=np.int16)
    lab_map[mask] = all_labels
    return _soilplus_cluster_png(lab_map, mask, int(n_clusters))
