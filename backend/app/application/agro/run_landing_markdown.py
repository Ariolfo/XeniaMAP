"""Caso de uso Agro: generación Markdown landing (worker H4)."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class RunLandingMarkdownJob:
    """Ejecuta ``scripts/generate_landing_markdown.py`` para un proyecto."""

    def execute(self, *, project_id: int) -> dict[str, Any]:
        from app.core.config import settings

        script = Path("/repo/scripts/generate_landing_markdown.py")
        if not script.is_file():
            return {
                "ok": False,
                "error": "script_missing",
                "message": f"No se encontró {script}. Monta ./scripts en el worker (docker-compose).",
                "pipeline": "landing_markdown",
            }
        db_url = settings.database_url.replace("+psycopg2", "")
        storage_root = os.environ.get("STORAGE_PATH", "/data/storage")
        env = dict(os.environ)
        env["PYTHONPATH"] = "/app"
        cmd = [
            sys.executable,
            str(script),
            "--project-id",
            str(project_id),
            "--storage",
            storage_root,
            "--database-url",
            db_url,
        ]
        logger.info("landing markdown: %s", " ".join(cmd))
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=1800)
        tail = "\n".join((proc.stdout or "").strip().splitlines()[-25:])
        if proc.returncode != 0:
            err_tail = "\n".join((proc.stderr or "").strip().splitlines()[-15:])
            logger.error("landing markdown falló (rc=%s): %s", proc.returncode, err_tail)
            return {
                "ok": False,
                "error": "generation_failed",
                "message": err_tail or f"El generador terminó con código {proc.returncode}",
                "log": tail,
                "pipeline": "landing_markdown",
            }
        return {"ok": True, "log": tail, "pipeline": "landing_markdown"}
