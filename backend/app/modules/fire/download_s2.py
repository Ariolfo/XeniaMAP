"""
Partial Sentinel-2 L2A download for Fire burn-severity workflow.

Port of Tolima script ``01_download_s2_tolima_RGB_MNDWI_v6.py``:
catalogue OData search + partial SAFE (B02/B03/B04/B8A/B11/B12/SCL + MTD).

Download backends (first available wins):
1. CDSE S3 credentials (``CDSE_S3_ACCESS_KEY`` / ``CDSE_S3_SECRET_KEY``)
2. OAuth + STAC HTTPS assets (``COPERNICUS_USER`` / ``COPERNICUS_PASSWORD``)
"""

from __future__ import annotations

import csv
import logging
import os
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import requests

from app.services.cdse_client import (
    CATALOGUE_URL,
    STAC_SEARCH_URL,
    get_copernicus_token,
    odata_attribute,
)

logger = logging.getLogger(__name__)

PRODUCT_TYPE = "S2MSI2A"

REQUIRED_10M = ("B02_10m", "B03_10m", "B04_10m")
REQUIRED_20M = ("B8A_20m", "B11_20m", "B12_20m", "SCL_20m")
REQUIRED_BAND_KEYS = REQUIRED_10M + REQUIRED_20M

REQUIRED_10M_SUFFIXES = tuple(f"_{k}.jp2" for k in REQUIRED_10M)
REQUIRED_20M_SUFFIXES = tuple(f"_{k}.jp2" for k in REQUIRED_20M)
REQUIRED_SUFFIXES = REQUIRED_10M_SUFFIXES + REQUIRED_20M_SUFFIXES

ProgressCb = Optional[Callable[[int, int, str], None]]


def _inclusive_end_to_exclusive(value: str) -> str:
    return (datetime.strptime(value, "%Y-%m-%d").date() + timedelta(days=1)).isoformat()


def mgrs_tile_from_name(product_name: str) -> str:
    match = re.search(r"_T(\d{2}[A-Z]{3})_", product_name)
    return match.group(1) if match else "UNKNOWN"


def sensing_datetime_from_product(product: Dict) -> str:
    content_date = product.get("ContentDate") or {}
    return str(content_date.get("Start") or "")


def extract_attribute(product: Dict, name: str, default=None):
    return odata_attribute(product, name, default)


def product_cloud_cover(product: Dict) -> Optional[float]:
    value = extract_attribute(product, "cloudCover")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def envelope_to_wkt(bounds) -> str:
    minx, miny, maxx, maxy = bounds
    return (
        "POLYGON(("
        f"{minx:.8f} {miny:.8f},"
        f"{maxx:.8f} {miny:.8f},"
        f"{maxx:.8f} {maxy:.8f},"
        f"{minx:.8f} {maxy:.8f},"
        f"{minx:.8f} {miny:.8f}"
        "))"
    )


def geometry_to_search_wkt(geometry: dict) -> str:
    """Build an OData search envelope WKT (EPSG:4326) from GeoJSON geometry/FC."""
    import geopandas as gpd

    t = geometry.get("type")
    if t == "FeatureCollection":
        gdf = gpd.GeoDataFrame.from_features(geometry.get("features") or [], crs="EPSG:4326")
    elif t == "Feature":
        gdf = gpd.GeoDataFrame.from_features([geometry], crs="EPSG:4326")
    elif t in ("Polygon", "MultiPolygon"):
        gdf = gpd.GeoDataFrame.from_features(
            [{"type": "Feature", "properties": {}, "geometry": geometry}],
            crs="EPSG:4326",
        )
    else:
        raise ValueError(f"Unsupported geometry type: {t}")
    if gdf.empty:
        raise ValueError("Empty geometry")
    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
    else:
        gdf = gdf.to_crs(4326)
    return envelope_to_wkt(gdf.total_bounds)


def query_s2_l2a_products(
    aoi_wkt: str,
    start_date: str,
    end_date_inclusive: str,
    max_cloud_cover: float,
) -> List[Dict]:
    end_exclusive = _inclusive_end_to_exclusive(end_date_inclusive)
    filter_query = (
        "Collection/Name eq 'SENTINEL-2' "
        "and Attributes/OData.CSC.StringAttribute/any(att:"
        "att/Name eq 'productType' and "
        f"att/OData.CSC.StringAttribute/Value eq '{PRODUCT_TYPE}') "
        f"and OData.CSC.Intersects(area=geography'SRID=4326;{aoi_wkt}') "
        f"and ContentDate/Start ge {start_date}T00:00:00.000Z "
        f"and ContentDate/Start lt {end_exclusive}T00:00:00.000Z "
        "and Attributes/OData.CSC.DoubleAttribute/any(att:"
        "att/Name eq 'cloudCover' and "
        f"att/OData.CSC.DoubleAttribute/Value le {max_cloud_cover:.2f})"
    )
    params = {
        "$filter": filter_query,
        "$expand": "Attributes",
        "$orderby": "ContentDate/Start asc",
        "$top": "1000",
    }
    products: List[Dict] = []
    next_url: Optional[str] = CATALOGUE_URL
    next_params: Optional[Dict] = params
    while next_url:
        response = requests.get(next_url, params=next_params, timeout=120)
        response.raise_for_status()
        payload = response.json()
        products.extend(payload.get("value", []))
        next_url = payload.get("@odata.nextLink")
        next_params = None
    products = [p for p in products if "_MSIL2A_" in str(p.get("Name", ""))]
    return products


def _get_oauth_token(username: str, password: str) -> str:
    return get_copernicus_token(username, password)


def _stac_required_assets(product_name: str, session: requests.Session) -> Dict[str, str]:
    identifier = str(product_name or "").split(".")[0]
    body = {"collections": ["sentinel-2-l2a"], "ids": [identifier], "limit": 1}
    r = session.post(STAC_SEARCH_URL, json=body, timeout=60)
    r.raise_for_status()
    feats = r.json().get("features") or []
    if not feats:
        raise FileNotFoundError(f"STAC item not found for {identifier}")
    assets = feats[0].get("assets") or {}
    out: Dict[str, str] = {}
    for key in REQUIRED_BAND_KEYS:
        asset = assets.get(key) or {}
        alt = (asset.get("alternate") or {}).get("https") or {}
        href = alt.get("href") or asset.get("href")
        if href and str(href).startswith("http"):
            out[key] = str(href)
    missing = [k for k in REQUIRED_BAND_KEYS if k not in out]
    if missing:
        raise FileNotFoundError(f"Missing STAC assets for {identifier}: {missing}")
    return out


def _download_url(session: requests.Session, url: str, dest: Path, overwrite: bool = False) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0 and not overwrite:
        return
    with session.get(url, stream=True, timeout=300, allow_redirects=True) as r:
        r.raise_for_status()
        tmp = dest.with_suffix(dest.suffix + ".part")
        with tmp.open("wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                if chunk:
                    f.write(chunk)
        tmp.replace(dest)


def _download_partial_via_stac(
    product: Dict,
    period_dir: Path,
    session: requests.Session,
    overwrite: bool = False,
) -> Path:
    name = product["Name"]
    safe_path = period_dir / name
    safe_path.mkdir(parents=True, exist_ok=True)
    assets = _stac_required_assets(name, session)
    for key, url in assets.items():
        # Keep a SAFE-like layout for script 02 compatibility.
        res = "R10m" if key.endswith("10m") else "R20m"
        rel = Path("IMG_DATA") / res / f"{name.split('.')[0]}_{key}.jp2"
        _download_url(session, url, safe_path / rel, overwrite=overwrite)
    # Metadata via OData product value is heavy; write a minimal stub marker if MTD missing.
    mtd = safe_path / "MTD_MSIL2A.xml"
    if not mtd.exists():
        mtd.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            "<n1:Level-2A_User_Product "
            'xmlns:n1="https://psd-14.sentinel2.eo.esa.int/PSD/User_Product_Level-2A.xsd">\n'
            "  <n1:General_Info>\n"
            "    <Product_Info><PRODUCT_URI>STAC_PARTIAL</PRODUCT_URI></Product_Info>\n"
            "    <Product_Image_Characteristics>\n"
            "      <QUANTIFICATION_VALUES_LIST>\n"
            "        <BOA_QUANTIFICATION_VALUE unit=\"none\">10000</BOA_QUANTIFICATION_VALUE>\n"
            "      </QUANTIFICATION_VALUES_LIST>\n"
            "    </Product_Image_Characteristics>\n"
            "  </n1:General_Info>\n"
            "</n1:Level-2A_User_Product>\n",
            encoding="utf-8",
        )
    return safe_path


def _get_s3_client():
    import boto3
    from botocore.config import Config

    endpoint_url = os.environ.get(
        "CDSE_S3_ENDPOINT_URL",
        "https://eodata.dataspace.copernicus.eu",
    )
    access_key = os.environ.get("CDSE_S3_ACCESS_KEY") or os.environ.get("CDSE_ACCESS_KEY")
    secret_key = os.environ.get("CDSE_S3_SECRET_KEY") or os.environ.get("CDSE_SECRET_KEY")
    region_name = os.environ.get("CDSE_S3_REGION", "default")
    if not access_key or not secret_key:
        return None
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url.rstrip("/"),
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region_name,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            retries={"max_attempts": 10, "mode": "standard"},
        ),
    )


def _parse_cdse_s3_path(s3_path: str) -> Tuple[str, str]:
    clean = s3_path.strip()
    if clean.startswith("s3://"):
        clean = clean[5:]
    clean = clean.strip("/")
    parts = clean.split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"Unexpected S3Path format: {s3_path}")
    bucket_name, prefix = parts
    if not prefix.endswith("/"):
        prefix += "/"
    return bucket_name, prefix


def _object_is_required(key: str, prefix: str) -> bool:
    relative = key[len(prefix) :] if key.startswith(prefix) else key
    if relative == "MTD_MSIL2A.xml":
        return True
    rel = f"/{relative}"
    if "/IMG_DATA/R10m/" in rel and relative.endswith(REQUIRED_10M_SUFFIXES):
        return True
    if "/IMG_DATA/R20m/" in rel and relative.endswith(REQUIRED_20M_SUFFIXES):
        return True
    return False


def _download_partial_via_s3(s3_client, product: Dict, period_dir: Path, overwrite: bool = False) -> Path:
    from boto3.s3.transfer import TransferConfig

    product_name = product["Name"]
    bucket, prefix = _parse_cdse_s3_path(product["S3Path"])
    safe_path = period_dir / product_name
    safe_path.mkdir(parents=True, exist_ok=True)

    paginator = s3_client.get_paginator("list_objects_v2")
    objects = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj.get("Key", "")
            if key and not key.endswith("/") and _object_is_required(key, prefix):
                objects.append(obj)
    if not objects:
        raise FileNotFoundError(f"No required objects under s3://{bucket}/{prefix}")

    transfer_config = TransferConfig(
        multipart_threshold=64 * 1024 * 1024,
        multipart_chunksize=64 * 1024 * 1024,
        max_concurrency=8,
        use_threads=True,
    )
    for obj in objects:
        key = obj["Key"]
        size = int(obj.get("Size", 0))
        relative_path = key[len(prefix) :]
        local_path = safe_path / relative_path
        local_path.parent.mkdir(parents=True, exist_ok=True)
        if local_path.exists() and local_path.stat().st_size == size and not overwrite:
            continue
        s3_client.download_file(
            Bucket=bucket,
            Key=key,
            Filename=str(local_path),
            Config=transfer_config,
        )
    return safe_path


def write_manifest(period: str, products: Iterable[Dict], output_root: Path) -> Path:
    manifest_path = output_root / f"catalog_{period}.csv"
    fieldnames = [
        "period",
        "sensing_datetime",
        "mgrs_tile",
        "cloud_cover_catalog_pct",
        "product_name",
        "product_id",
        "s3_path",
        "local_safe",
    ]
    with manifest_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for product in products:
            name = product.get("Name", "")
            writer.writerow(
                {
                    "period": period,
                    "sensing_datetime": sensing_datetime_from_product(product),
                    "mgrs_tile": mgrs_tile_from_name(name),
                    "cloud_cover_catalog_pct": product_cloud_cover(product),
                    "product_name": name,
                    "product_id": product.get("Id", ""),
                    "s3_path": product.get("S3Path", ""),
                    "local_safe": str(output_root / period / name),
                }
            )
    return manifest_path


def download_period(
    *,
    period: str,
    aoi_wkt: str,
    start_date: str,
    end_date: str,
    max_cloud_cover: float,
    output_root: Path,
    progress: ProgressCb = None,
) -> Dict:
    products = query_s2_l2a_products(aoi_wkt, start_date, end_date, max_cloud_cover)
    products = sorted(products, key=sensing_datetime_from_product)
    period_dir = output_root / period
    period_dir.mkdir(parents=True, exist_ok=True)

    if not products:
        write_manifest(period, [], output_root)
        return {
            "period": period,
            "product_count": 0,
            "products": [],
            "manifest": str(output_root / f"catalog_{period}.csv"),
        }

    s3_client = _get_s3_client()
    oauth_session: Optional[requests.Session] = None
    if s3_client is None:
        from app.services.cdse_client import get_copernicus_credentials
        from app.core.config import settings

        user, password = get_copernicus_credentials(settings)
        token = _get_oauth_token(user, password)
        oauth_session = requests.Session()
        oauth_session.headers.update({"Authorization": f"Bearer {token}"})

    downloaded = []
    total = len(products)
    for idx, product in enumerate(products, start=1):
        name = product.get("Name", "")
        if progress:
            progress(idx - 1, total, f"{period.upper()}: descargando {name}")
        if s3_client is not None and product.get("S3Path"):
            path = _download_partial_via_s3(s3_client, product, period_dir)
        else:
            assert oauth_session is not None
            path = _download_partial_via_stac(product, period_dir, oauth_session)
        downloaded.append(
            {
                "name": name,
                "id": product.get("Id"),
                "cloud_cover": product_cloud_cover(product),
                "mgrs_tile": mgrs_tile_from_name(name),
                "local_safe": str(path),
            }
        )
    if progress:
        progress(total, total, f"{period.upper()}: {len(downloaded)} productos")
    manifest = write_manifest(period, products, output_root)
    return {
        "period": period,
        "product_count": len(downloaded),
        "products": downloaded,
        "manifest": str(manifest),
    }


def run_fire_s2_download(
    *,
    geometry: dict,
    pre_start: str,
    pre_end: str,
    post_start: str,
    post_end: str,
    max_cloud_cover: float,
    output_root: str | Path,
    progress: ProgressCb = None,
) -> Dict:
    t0 = time.perf_counter()
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    aoi_wkt = geometry_to_search_wkt(geometry)

    def _wrap(done: int, total: int, msg: str, offset: int = 0, span: int = 50) -> None:
        if not progress:
            return
        pct = offset + int((done / max(total, 1)) * span)
        progress(min(pct, 99), 100, msg)

    pre = download_period(
        period="pre",
        aoi_wkt=aoi_wkt,
        start_date=pre_start,
        end_date=pre_end,
        max_cloud_cover=max_cloud_cover,
        output_root=root,
        progress=lambda d, t, m: _wrap(d, t, m, 0, 45),
    )
    post = download_period(
        period="post",
        aoi_wkt=aoi_wkt,
        start_date=post_start,
        end_date=post_end,
        max_cloud_cover=max_cloud_cover,
        output_root=root,
        progress=lambda d, t, m: _wrap(d, t, m, 45, 50),
    )
    if progress:
        progress(100, 100, "Descarga Fire S2 finalizada")
    return {
        "ok": True,
        "aoi_wkt": aoi_wkt,
        "max_cloud_cover": max_cloud_cover,
        "pre": pre,
        "post": post,
        "output_root": str(root),
        "elapsed_sec": round(time.perf_counter() - t0, 1),
        "backend": "s3" if _get_s3_client() is not None else "stac_oauth",
    }
