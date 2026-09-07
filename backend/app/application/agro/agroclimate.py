"""Agroclima: Open-Meteo archive → medias mensuales alineadas a fechas de escena."""

from __future__ import annotations

import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

import numpy as np


def norm_iso_date(raw: str) -> str:
    return str(raw or "").strip()[:10]


def fetch_open_meteo_daily(lat: float, lon: float, start_date: str, end_date: str) -> list[dict]:
    """Serie diaria (Open-Meteo archive) en unidades nativas. Lanza RuntimeError si falla la red."""
    params = {
        "latitude": f"{lat:.8f}",
        "longitude": f"{lon:.8f}",
        "start_date": start_date,
        "end_date": end_date,
        "timezone": "auto",
        "daily": "temperature_2m_mean,relative_humidity_2m_mean,precipitation_sum,shortwave_radiation_sum",
    }
    url = f"https://archive-api.open-meteo.com/v1/archive?{urlencode(params)}"
    try:
        with urlopen(url, timeout=25) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(f"No se pudo consultar Open-Meteo: {exc!s}") from exc

    daily = payload.get("daily") or {}
    times = daily.get("time") or []
    t2m = daily.get("temperature_2m_mean") or []
    rh = daily.get("relative_humidity_2m_mean") or []
    pr = daily.get("precipitation_sum") or []
    sw = daily.get("shortwave_radiation_sum") or []
    n = min(len(times), len(t2m), len(rh), len(pr), len(sw))
    out: list[dict] = []
    for i in range(n):
        d = norm_iso_date(times[i])
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", d):
            continue
        out.append(
            {
                "date": d,
                "temp": float(t2m[i]) if t2m[i] is not None else None,
                "humidity": float(rh[i]) if rh[i] is not None else None,
                "precip": float(pr[i]) if pr[i] is not None else None,
                "radiation": float(sw[i]) if sw[i] is not None else None,
            }
        )
    return out


def monthly_means_from_daily(rows: list[dict]) -> dict[str, dict]:
    buckets: dict[str, dict[str, list[float]]] = {}
    for r in rows:
        m = str(r.get("date") or "")[:7]
        if not re.match(r"^\d{4}-\d{2}$", m):
            continue
        b = buckets.setdefault(m, {"precip": [], "temp": [], "humidity": [], "radiation": []})
        for k in ("precip", "temp", "humidity", "radiation"):
            v = r.get(k)
            if v is None or not np.isfinite(v):
                continue
            b[k].append(float(v))
    out: dict[str, dict] = {}
    for m, b in buckets.items():
        out[m] = {
            "precip": float(np.mean(b["precip"])) if b["precip"] else None,
            "temp": float(np.mean(b["temp"])) if b["temp"] else None,
            "humidity": float(np.mean(b["humidity"])) if b["humidity"] else None,
            "radiation": float(np.mean(b["radiation"])) if b["radiation"] else None,
        }
    return out


def series_from_scene_dates(scene_dates: list[str], monthly_means: dict[str, dict]) -> list[dict]:
    out: list[dict] = []
    for d in scene_dates:
        nd = norm_iso_date(d)
        month = nd[:7]
        row = monthly_means.get(month) or {}
        out.append(
            {
                "date": nd,
                "month": month,
                "precip": row.get("precip"),
                "temp": row.get("temp"),
                "humidity": row.get("humidity"),
                "radiation": row.get("radiation"),
            }
        )
    return out
