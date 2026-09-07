"""Puertos compartidos — sin frameworks (FastAPI / SQLAlchemy / Celery)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class CdseAuthPort(Protocol):
    """Puerto: autenticación OAuth CDSE (Copernicus Data Space)."""

    def credentials_from_settings(self, settings: Any) -> tuple[str, str]:
        """Usuario/contraseña desde settings; lanza RuntimeError si faltan."""
        ...

    def access_token(self, username: str, password: str) -> str:
        """Token Bearer CDSE."""
        ...


class ProjectRepository(Protocol):
    """Persistencia mínima de proyectos (H3)."""

    def get_by_id(self, project_id: int, *, tenant_id: int | None = None) -> Any | None:
        """Devuelve el proyecto ORM/DTO o None."""
        ...

    def get_name(self, project_id: int) -> str | None:
        ...

    def save(self, project: Any) -> Any:
        """Persiste cambios (add/commit/refresh) y retorna el mismo objeto."""
        ...


class RasterStoragePort(Protocol):
    """Paths de almacenamiento por tenant/proyecto (disco)."""

    def tenant_kind_dir(self, tenant_id: int, project_id: int, kind: str) -> Path:
        """``storage/tenant_*/project_*/{kind}/`` (crea si falta)."""
        ...

    def project_root(self, tenant_id: int, project_id: int) -> Path:
        ...


class JobQueuePort(Protocol):
    """Encola trabajo asíncrono y registra task_id→tenant."""

    def enqueue(
        self,
        task: Any,
        *args: Any,
        tenant_id: int,
        project_id: int | None = None,
        task_name: str | None = None,
        **kwargs: Any,
    ) -> str:
        """
        Encola ``task.delay(*args, **kwargs)``, registra ownership y retorna ``task_id``.
        Lanza ``RuntimeError`` si el broker no está disponible.
        """
        ...


class MailPort(Protocol):
    """Salida de correo (SMTP u otro adaptador)."""

    def send_email(self, *, to: str, subject: str, body: str) -> bool:
        ...

    def send_study_order_notification(
        self, *, order_id: int, user_email: str, lines: list[str]
    ) -> None:
        ...


class TileRenderPort(Protocol):
    """Render de previews / XYZ / MVT (salida bytes)."""

    def render_raster_preview_png(
        self,
        path: Path,
        *,
        max_dim: int = 2048,
        layer_metadata: dict | None = None,
        index_palette_request: bool = False,
        rgb_bands_1based: tuple[int, int, int] | None = None,
    ) -> bytes:
        ...

    def render_fire_xyz_tile_png(
        self,
        path: Path,
        z: int,
        x: int,
        y: int,
        *,
        mode: str = "rgb",
        severity_class: int | None = None,
        index_cmap: str = "RdYlBu_r",
    ) -> bytes:
        ...

    def render_layer_mvt_tile(
        self,
        db: Any,
        *,
        layer_id: int,
        tenant_id: int,
        project_id: int,
        z: int,
        x: int,
        y: int,
        source_layer: str = "published",
        extent: int = 4096,
        buffer: int = 64,
    ) -> bytes:
        """``db`` es un handle opaco de persistencia (adaptador ejecuta el SQL)."""
        ...
