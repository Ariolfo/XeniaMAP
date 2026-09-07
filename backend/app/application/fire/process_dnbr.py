"""Caso de uso: pipeline dNBR / severidad / candidatos (script 02 Fire)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class ProcessDnbrPipeline:
    """
    Orquesta el procesamiento dNBR sin acoplar Celery/HTTP.

    La implementación pesada permanece en ``modules.fire.process_dnbr``
    (script portado); este use case es el punto de entrada hexagonal.
    """

    def execute(
        self,
        *,
        aoi_path: str | Path,
        s2_root: str | Path,
        output_dir: str | Path,
        output_prefix: str = "Fire",
        municipality_field: str = "MpNombre",
        department_field: str = "Depto",
    ) -> dict[str, Any]:
        from app.modules.fire.process_dnbr import run_dnbr_pipeline

        return run_dnbr_pipeline(
            aoi_path=aoi_path,
            s2_root=s2_root,
            output_dir=output_dir,
            output_prefix=output_prefix,
            municipality_field=municipality_field,
            department_field=department_field,
        )
