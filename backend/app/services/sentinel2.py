"""
Sentinel-2 download service using Copernicus Data Space.
Searches and downloads S2 L2A (MSIL2A) products month by month for a given WKT polygon.

Criteria before download:
- footprint covers >= 75% of the AOI;
- cloudiness over the AOI (from SCL_20m) is < 25%.
"""
from __future__ import annotations

import logging
import os
import tempfile
from collections.abc import Callable
from datetime import date
from pathlib import Path

import numpy as np
import requests
from dateutil.relativedelta import relativedelta
from shapely import from_wkt
from shapely.geometry import mapping

from app.domain.shared.ports import CdseAuthPort
from app.infrastructure.cdse.client import (
    CATALOGUE_URL,
    STAC_SEARCH_URL,
    CdseAuthAdapter,
    odata_cloud_cover_pct as _odata_cloud_cover_pct_shared,
)

logger = logging.getLogger(__name__)

DATA_COLLECTION = "SENTINEL-2"
MIN_COVERAGE = 0.75
MAX_AOI_CLOUD = 0.25
# Sen2Cor SCL: medium cloud, high cloud, thin cirrus (nubosidad).
CLOUDY_SCL_CLASSES = frozenset({8, 9, 10})


def _count_month_slots(start: date, end: date) -> int:
    n = 0
    cur = start
    while cur < end:
        n += 1
        cur = cur + relativedelta(months=1)
    return max(n, 1)


def get_copernicus_credentials(auth: CdseAuthPort | None = None) -> tuple[str, str]:
    """
    Usuario y contraseña CDSE desde settings vía ``CdseAuthPort``.
    """
    from app.core.config import settings

    return (auth or CdseAuthAdapter()).credentials_from_settings(settings)


def get_copernicus_token(
    username: str,
    password: str,
    auth: CdseAuthPort | None = None,
) -> str:
    """Token Bearer CDSE vía ``CdseAuthPort`` (default ``CdseAuthAdapter``)."""
    return (auth or CdseAuthAdapter()).access_token(username, password)


def _product_covers_area(product: dict, aoi_geom) -> bool:
    """Check if product footprint covers >= 75% of the area of interest."""
    try:
        footprint_wkt = product.get("Footprint", "")
        if not footprint_wkt:
            # If no footprint, accept based on catalogue intersection
            return True
        # Extract WKT from "geography'SRID=4326;POLYGON(...)'" format
        if "SRID=" in footprint_wkt:
            footprint_wkt = footprint_wkt.split(";", 1)[1].rstrip("'")
        product_geom = from_wkt(footprint_wkt)
        if not product_geom.is_valid:
            product_geom = product_geom.buffer(0)
        intersection = aoi_geom.intersection(product_geom)
        coverage = intersection.area / aoi_geom.area if aoi_geom.area > 0 else 0
        logger.info("Product coverage: %.1f%%", coverage * 100)
        return coverage >= MIN_COVERAGE
    except Exception:
        logger.warning("Could not compute coverage, accepting product")
        return True


def _product_identifier(product: dict) -> str:
    return str(product.get("Name") or "").split(".")[0]


def _odata_cloud_cover_pct(product: dict) -> float | None:
    """Cloud cover de la escena completa (Attributes OData), 0–100. No es del polígono."""
    return _odata_cloud_cover_pct_shared(product)


def _stac_scl_https_url(product_name: str, session: requests.Session) -> str | None:
    """Resuelve URL HTTPS de ``SCL_20m`` vía STAC CDSE."""
    identifier = str(product_name or "").split(".")[0]
    if not identifier:
        return None
    body = {
        "collections": ["sentinel-2-l2a"],
        "ids": [identifier],
        "limit": 1,
    }
    try:
        r = session.post(STAC_SEARCH_URL, json=body, timeout=60)
        r.raise_for_status()
        feats = r.json().get("features") or []
        if not feats:
            # Fallback por filtro de id (algunos ítems no matchean ``ids`` exacto).
            body2 = {
                "collections": ["sentinel-2-l2a"],
                "limit": 1,
                "filter": {
                    "op": "eq",
                    "args": [{"property": "id"}, identifier],
                },
                "filter-lang": "cql2-json",
            }
            r2 = session.post(STAC_SEARCH_URL, json=body2, timeout=60)
            r2.raise_for_status()
            feats = r2.json().get("features") or []
        if not feats:
            return None
        asset = (feats[0].get("assets") or {}).get("SCL_20m") or {}
        alt = (asset.get("alternate") or {}).get("https") or {}
        href = alt.get("href") or asset.get("href")
        if href and str(href).startswith("http"):
            return str(href)
    except Exception:
        logger.exception("STAC SCL lookup failed for %s", identifier)
    return None


def aoi_cloud_fraction_from_scl(scl_path: str | Path, aoi_geom) -> float | None:
    """
    Fracción de nubosidad (0–1) del AOI usando SCL Sen2Cor.
    Nubes = clases 8, 9, 10. Denominador = píxeles del AOI con SCL != 0.
    """
    import rasterio
    from rasterio.mask import mask as rio_mask
    from rasterio.warp import transform_geom

    path = Path(scl_path)
    if not path.is_file():
        return None
    try:
        with rasterio.open(path) as src:
            geom = aoi_geom
            if not geom.is_valid:
                geom = geom.buffer(0)
            # AOI llega en WGS84; SCL suele estar en UTM del tile.
            dst_crs = src.crs
            if dst_crs is None:
                return None
            geom_json = mapping(geom)
            if str(dst_crs).upper() not in {"EPSG:4326", "OGC:CRS84"}:
                geom_json = transform_geom("EPSG:4326", dst_crs, geom_json, precision=6)
            out, _ = rio_mask(src, [geom_json], crop=True, filled=True, nodata=0)
            arr = np.asarray(out[0])
            valid = arr != 0
            n_valid = int(valid.sum())
            if n_valid <= 0:
                return None
            cloudy = np.isin(arr, list(CLOUDY_SCL_CLASSES)) & valid
            return float(cloudy.sum()) / float(n_valid)
    except Exception:
        logger.exception("Failed AOI cloud fraction from SCL %s", path)
        return None


def _product_aoi_cloud_ok(
    product: dict,
    aoi_geom,
    session: requests.Session,
) -> tuple[bool, float | None, str]:
    """
    True si nubosidad del polígono < 25%.
    Descarga solo SCL_20m (~MB) y enmascara al AOI.
    Si no se puede calcular SCL: fallback a cloudCover de escena < 25%.
    """
    identifier = _product_identifier(product)
    href = _stac_scl_https_url(identifier, session)
    if href:
        tmp_path: Path | None = None
        try:
            r = session.get(href, allow_redirects=True, timeout=180)
            r.raise_for_status()
            fd, name = tempfile.mkstemp(suffix="_SCL_20m.jp2")
            os.close(fd)
            tmp_path = Path(name)
            tmp_path.write_bytes(r.content)
            frac = aoi_cloud_fraction_from_scl(tmp_path, aoi_geom)
            if frac is not None:
                logger.info(
                    "AOI cloud cover for %s: %.1f%% (threshold < %.0f%%)",
                    identifier,
                    frac * 100,
                    MAX_AOI_CLOUD * 100,
                )
                return frac < MAX_AOI_CLOUD, frac, "scl_aoi"
        except Exception:
            logger.exception("SCL download/check failed for %s", identifier)
        finally:
            if tmp_path is not None:
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass

    scene_pct = _odata_cloud_cover_pct(product)
    if scene_pct is not None:
        frac = scene_pct / 100.0
        logger.warning(
            "Using scene cloudCover=%.1f%% as fallback for %s (SCL AOI unavailable)",
            scene_pct,
            identifier,
        )
        return frac < MAX_AOI_CLOUD, frac, "scene_cloudcover"

    logger.warning("No cloud metric for %s; skipping download", identifier)
    return False, None, "unavailable"


def download_product(
    product_id: str,
    product_name: str,
    session: requests.Session,
    output_dir: str,
    stream_progress: Callable[[int, int, str], None] | None = None,
) -> str | None:
    url = f"{CATALOGUE_URL}({product_id})/$value"
    r1 = session.get(url, allow_redirects=False, timeout=30)
    download_url = r1.headers.get("Location", url)
    r2 = session.get(
        download_url,
        allow_redirects=True,
        headers={"Authorization": session.headers["Authorization"]},
        stream=True,
        timeout=300,
    )
    r2.raise_for_status()
    zip_path = os.path.join(output_dir, f"{product_name}.zip")
    total_size = 0
    total_hint: int | None = None
    cl = r2.headers.get("Content-Length")
    if cl and str(cl).isdigit():
        total_hint = int(cl)
    # Porcentaje dentro de la fase de descarga del ZIP (la barra no queda congelada varios minutos).
    lo_pct, hi_pct = 88, 99
    throttle = 2 * 1024 * 1024
    last_emit = 0

    def _emit_progress(force: bool = False) -> None:
        nonlocal last_emit
        if not stream_progress:
            return
        if not force and total_size - last_emit < throttle:
            return
        last_emit = total_size
        mb = total_size // (1024 * 1024)
        if total_hint and total_hint > 0:
            frac = min(1.0, total_size / total_hint)
            pct = lo_pct + int(frac * (hi_pct - lo_pct))
        else:
            pct = (lo_pct + hi_pct) // 2
        stream_progress(pct, 100, f"Descargando {product_name}... ({mb} MB)")

    with open(zip_path, "wb") as f:
        for chunk in r2.iter_content(chunk_size=8192 * 16):
            if not chunk:
                continue
            f.write(chunk)
            total_size += len(chunk)
            _emit_progress(force=False)
    _emit_progress(force=True)
    logger.info("Downloaded %s (%d MB)", product_name, total_size // (1024 * 1024))
    return zip_path


def search_and_download_monthly(
    wkt_polygon: str,
    start_date: date,
    end_date: date,
    output_dir: str,
    copernicus_user: str,
    copernicus_password: str,
    progress_callback: Callable[[int, int, str], None] | None = None,
    auth: CdseAuthPort | None = None,
) -> dict:
    """
    Download all S2 L2A (MSIL2A) products per month that:
    - cover >=75% of the WKT area, and
    - have <25% cloudiness over the AOI (SCL).
    """
    os.makedirs(output_dir, exist_ok=True)
    total_downloaded = 0
    total_size_mb = 0
    downloaded_files: list[str] = []
    skipped_low_coverage = 0
    skipped_high_cloud = 0

    aoi_geom = from_wkt(wkt_polygon)
    if not aoi_geom.is_valid:
        aoi_geom = aoi_geom.buffer(0)

    total_months = _count_month_slots(start_date, end_date)
    month_index = 0

    def _report(msg: str, sub: float | None = None) -> None:
        if not progress_callback:
            return
        if sub is not None:
            pct = int(5 + (month_index + sub) / max(total_months, 1) * 90)
        else:
            pct = int(5 + month_index / max(total_months, 1) * 90)
        progress_callback(min(pct, 99), 100, msg)

    _report("Iniciando busqueda Sentinel-2...", 0)

    current = start_date
    while current < end_date:
        next_month = current + relativedelta(months=1)
        if next_month > end_date:
            next_month = end_date
        start_str = current.strftime("%Y-%m-%d")
        end_str = next_month.strftime("%Y-%m-%d")
        logger.info("Searching S2 products: %s -> %s", start_str, end_str)
        _report(f"Buscando imagenes: {start_str} (mes {month_index + 1}/{total_months})", 0.2)

        try:
            token = get_copernicus_token(copernicus_user, copernicus_password, auth=auth)
            session = requests.Session()
            session.verify = False
            session.headers.update({"Authorization": f"Bearer {token}"})

            query_url = (
                f"{CATALOGUE_URL}"
                f"?$filter=Collection/Name eq '{DATA_COLLECTION}'"
                f" and OData.CSC.Intersects(area=geography'SRID=4326;{wkt_polygon}')"
                f" and ContentDate/Start ge {start_str}T00:00:00.000Z"
                f" and ContentDate/Start lt {end_str}T00:00:00.000Z"
                f"&$expand=Attributes"
                f"&$count=True&$top=1000"
            )
            resp = session.get(query_url, timeout=60)
            resp.raise_for_status()
            j = resp.json()

            products = j.get("value", [])
            s2_l2a_products = [
                p
                for p in products
                if p["Name"].startswith("S2A_MSIL2A") or p["Name"].startswith("S2B_MSIL2A")
            ]

            if not s2_l2a_products:
                logger.info("No S2 L2A (MSIL2A) products for %s", start_str)
                month_index += 1
                current = next_month
                continue

            s2_l2a_products.sort(key=lambda p: p["ContentDate"]["Start"])

            downloaded_this_month = 0
            n_products = len(s2_l2a_products)
            for pi, product in enumerate(s2_l2a_products):
                if not _product_covers_area(product, aoi_geom):
                    skipped_low_coverage += 1
                    continue

                identifier = _product_identifier(product)
                _report(f"Verificando nubosidad AOI: {identifier}...", 0.22 + 0.05 * ((pi + 1) / max(n_products, 1)))
                ok_cloud, cloud_frac, cloud_src = _product_aoi_cloud_ok(product, aoi_geom, session)
                if not ok_cloud:
                    skipped_high_cloud += 1
                    logger.info(
                        "Skip %s: AOI cloud %.1f%% (src=%s) >= %.0f%%",
                        identifier,
                        (cloud_frac or 0) * 100,
                        cloud_src,
                        MAX_AOI_CLOUD * 100,
                    )
                    continue

                prod_id = product["Id"]

                expected_file = os.path.join(output_dir, f"{identifier}.zip")
                if os.path.exists(expected_file):
                    logger.info("Already exists: %s", identifier)
                    downloaded_files.append(expected_file)
                    downloaded_this_month += 1
                else:
                    sub = 0.25 + 0.7 * ((pi + 1) / max(n_products, 1))
                    _report(f"Descargando {identifier}...", sub)
                    zip_path = download_product(
                        prod_id,
                        identifier,
                        session,
                        output_dir,
                        stream_progress=progress_callback,
                    )
                    if zip_path and os.path.exists(zip_path):
                        file_size = os.path.getsize(zip_path) // (1024 * 1024)
                        total_downloaded += 1
                        total_size_mb += file_size
                        downloaded_files.append(zip_path)
                        downloaded_this_month += 1

            if downloaded_this_month == 0:
                logger.info(
                    "No product for %s with coverage>=75%% and AOI cloud<%.0f%%",
                    start_str,
                    MAX_AOI_CLOUD * 100,
                )
            else:
                logger.info(
                    "Month %s: %d product(s) kept (coverage>=75%%, AOI cloud<%.0f%%)",
                    start_str,
                    downloaded_this_month,
                    MAX_AOI_CLOUD * 100,
                )

        except Exception:
            logger.exception("Error downloading S2 for %s", start_str)

        month_index += 1
        current = next_month

    _report("Finalizando...", 0.95)

    return {
        "total_downloaded": total_downloaded,
        "total_size_mb": total_size_mb,
        "files": downloaded_files,
        "skipped_low_coverage": skipped_low_coverage,
        "skipped_high_cloud": skipped_high_cloud,
    }
