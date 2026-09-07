"""Caso de uso: validación FIRMS VIIRS (script 03 Fire)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class ValidateFirmsPipeline:
    """
    Orquesta validación FIRMS sin acoplar Celery/HTTP.

    La implementación pesada permanece en ``modules.fire.validate_firms``.
    """

    def execute(
        self,
        *,
        aoi_path: str | Path,
        results_dir: str | Path,
        fire_start: str,
        fire_end: str | None = None,
        output_prefix: str = "Fire",
        municipality_field: str = "MpNombre",
        department_field: str = "Depto",
        map_key: str | None = None,
    ) -> dict[str, Any]:
        from app.modules.fire.validate_firms import run_firms_pipeline

        return run_firms_pipeline(
            aoi_path=aoi_path,
            results_dir=results_dir,
            fire_start=fire_start,
            fire_end=fire_end,
            output_prefix=output_prefix,
            municipality_field=municipality_field,
            department_field=department_field,
            map_key=map_key,
        )
