"""Catálogo de capas de salida Fire publicables en el mapa."""

from __future__ import annotations

from pathlib import Path

# Orden de visualización en el panel / mapa.
FIRE_RESULT_CATALOG: list[dict] = [
    {
        "filename": "Fire_dNBR.tif",
        "label": "dNBR",
        "kind": "raster",
        "default_on": False,
        "preview_meta": {"preview_rgb_bands": [1, 1, 1], "index_preview_cmap": "RdYlBu_r"},
        "index_palette": True,
        # Clases 1–7 (desde Fire_burn_severity.tif) se anidan bajo dNBR en el panel.
        "severity_class_group": True,
    },
    {
        "filename": "Fire_burn_severity.tif",
        "label": "Severidad",
        "kind": "raster",
        "default_on": False,
        "preview_meta": {"preview_rgb_bands": [1, 1, 1]},
        "index_palette": False,
        "discrete_severity": True,
        # No listar como capa top-level: se expone vía clases bajo dNBR.
        "ui_nested_only": True,
    },
    {
        "filename": "Fire_RGB_PRE_10m_COG.tif",
        "label": "RGB PRE",
        "kind": "raster",
        "default_on": False,
        "preview_meta": {"preview_rgb_bands": [1, 2, 3]},
        "index_palette": False,
        "display_ready_uint8": True,
    },
    {
        "filename": "Fire_RGB_POST_10m_COG.tif",
        "label": "RGB POST",
        "kind": "raster",
        "default_on": False,
        "preview_meta": {"preview_rgb_bands": [1, 2, 3]},
        "index_palette": False,
        "display_ready_uint8": True,
    },
    {
        "filename": "Fire_burn_candidates.gpkg",
        "label": "Candidatos quemados",
        "kind": "vector",
        "default_on": False,
        "stats": True,
    },
    {
        "filename": "Fire_burn_candidates_validated.gpkg",
        "label": "Candidatos validados",
        "kind": "vector",
        "default_on": False,
        "stats": True,
    },
    {
        "filename": "Fire_burned_area_recommended.gpkg",
        "label": "Área quemada recomendada",
        "kind": "vector",
        "default_on": True,
        "stats": True,
    },
    {
        "filename": "Fire_FIRMS_VIIRS_hotspots.gpkg",
        "label": "Hotspots FIRMS VIIRS",
        "kind": "vector",
        "default_on": True,
        "stats": True,
        "stats_kind": "points",
        "map_symbol": "star",
    },
]


def catalog_entry(filename: str) -> dict | None:
    name = Path(str(filename or "")).name
    return next((c for c in FIRE_RESULT_CATALOG if c["filename"] == name), None)


def allowed_result_filenames() -> set[str]:
    return {c["filename"] for c in FIRE_RESULT_CATALOG}
