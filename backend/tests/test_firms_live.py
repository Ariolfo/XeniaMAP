"""Unit tests for FIRMS live age bucketing (no network)."""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from app.modules.fire.firms_live import _hotspots_to_feature_collections
import geopandas as gpd
from shapely.geometry import box


def test_hotspots_split_24h_and_48h_buckets():
    as_of = datetime(2026, 9, 5, 15, 0, tzinfo=timezone.utc)
    # AOI around a point in Colombia-ish
    aoi = gpd.GeoDataFrame(geometry=[box(-75.1, 4.0, -74.9, 4.2)], crs="EPSG:4326").to_crs(32618)

    df = pd.DataFrame(
        [
            # 12h ago → 24h bucket
            {
                "latitude": 4.1,
                "longitude": -75.0,
                "acq_date": "2026-09-05",
                "acq_time": 300,
                "frp": 1.0,
                "confidence": "n",
            },
            # 36h ago → 48h bucket
            {
                "latitude": 4.11,
                "longitude": -75.01,
                "acq_date": "2026-09-04",
                "acq_time": 300,
                "frp": 2.0,
                "confidence": "n",
            },
            # 60h ago → discarded when hours=48
            {
                "latitude": 4.12,
                "longitude": -75.02,
                "acq_date": "2026-09-03",
                "acq_time": 300,
                "frp": 3.0,
                "confidence": "n",
            },
        ]
    )

    fc24, fc48, n24, n48 = _hotspots_to_feature_collections(
        df, aoi, as_of=as_of, hours=48
    )
    assert n24 == 1
    assert n48 == 1
    assert len(fc24["features"]) == 1
    assert len(fc48["features"]) == 1
    assert fc24["features"][0]["properties"]["age_bucket"] == "24h"
    assert fc48["features"][0]["properties"]["age_bucket"] == "48h"
