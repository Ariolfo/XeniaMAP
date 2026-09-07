"""Tests agroclimate helpers extracted from preprocess."""

from app.application.agro.agroclimate import (
    monthly_means_from_daily,
    norm_iso_date,
    series_from_scene_dates,
)


def test_norm_iso_date() -> None:
    assert norm_iso_date("2024-03-15T12:00:00") == "2024-03-15"


def test_monthly_means_and_series() -> None:
    rows = [
        {"date": "2024-01-15", "temp": 20.0, "humidity": 50.0, "precip": 1.0, "radiation": 10.0},
        {"date": "2024-01-16", "temp": 22.0, "humidity": 52.0, "precip": 3.0, "radiation": 12.0},
    ]
    mm = monthly_means_from_daily(rows)
    assert abs(mm["2024-01"]["temp"] - 21.0) < 1e-9
    assert abs(mm["2024-01"]["precip"] - 2.0) < 1e-9
    series = series_from_scene_dates(["2024-01-10"], mm)
    assert series[0]["month"] == "2024-01"
    assert series[0]["temp"] == 21.0
