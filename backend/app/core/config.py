import logging
import os
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


def _default_storage_path() -> str:
    """
    Sin STORAGE_PATH en el entorno: misma carpeta que en compose (``./data:/data`` → ``/data/storage``)
    o, en desarrollo local, ``<repo>/data/storage`` (p. ej. recortes en tenant_X/project_Y/recortes).

    En contenedor suele existir ``/data/storage``; en el repo local suele existir ``…/XeniaMAP/backend``.
    """
    core_dir = Path(__file__).resolve().parent
    railway_mount = Path(os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "").strip()) if os.getenv("RAILWAY_VOLUME_MOUNT_PATH") else None
    docker_root = Path("/data/storage")
    if railway_mount and str(railway_mount).strip():
        return str((railway_mount / "storage").resolve())
    if len(core_dir.parents) > 2:
        repo = core_dir.parents[2]
        if (repo / "backend").is_dir():
            return str((repo / "data" / "storage").resolve())
        if (docker_root).is_dir():
            return str(docker_root.resolve())
    if docker_root.is_dir():
        return str(docker_root.resolve())
    if len(core_dir.parents) > 2:
        return str((core_dir.parents[2] / "data" / "storage").resolve())
    return "/data/storage"


def _env_files_for_settings() -> tuple[str, ...]:
    """Carga .env de backend/ y, si existe, de la raíz del repo. En Docker (/app/app/core) no hay parents[3]."""
    core = Path(__file__).resolve().parent
    candidates: list[Path] = []
    if len(core.parents) > 2:
        candidates.append(core.parents[2] / ".env")  # …/backend/.env
    if len(core.parents) > 3:
        candidates.append(core.parents[3] / ".env")  # …/repo/.env (solo en árbol profundo)
    return tuple(str(p) for p in candidates if p.is_file())


def _settings_model_config() -> SettingsConfigDict:
    kw: dict = {"env_file_encoding": "utf-8", "extra": "ignore"}
    ef = _env_files_for_settings()
    if ef:
        kw["env_file"] = ef
    return SettingsConfigDict(**kw)


class Settings(BaseSettings):
    app_name: str = "XeniaMAP API"
    api_v1_prefix: str = "/api/v1"
    secret_key: str = ""
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_minutes: int = 60 * 24 * 7
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/xeniamap"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000"
    cors_origin_regex: str = ""
    redis_url: str = "redis://localhost:6379/0"
    # Límite por IP (middleware en ``main.py``); galerías RGB lanzan muchas peticiones en paralelo.
    rate_limit_window_seconds: int = 60
    rate_limit_max_requests: int = 600
    ai_service_url: str = Field(
        default="http://localhost:8001",
        description="Stub IA opcional (perfil compose ``ai``). No requerido para Agro/Fire.",
    )
    storage_path: str = Field(default_factory=_default_storage_path)
    # Disco local de datos grandes (recorte S1/S2/PS). En Docker: montar host → /data_xeniamap.
    # Vacío = deshabilitado. Ejemplo host: /mnt/disco3tb/Data_XeniaMap
    external_data_root: str = Field(
        default="",
        description="Raíz Data_XeniaMap (datos externos). Subpaths vía prefijo ext:.",
    )
    max_upload_mb: int = 4096  # Sentinel-2 ZIP; variable de entorno MAX_UPLOAD_MB tiene prioridad
    copernicus_user: str = Field(
        default="",
        description="CDSE (Copernicus Data Space); misma cuenta para descarga Sentinel-2 y Sentinel-1.",
    )
    copernicus_password: str = Field(default="", description="Contraseña CDSE (Sentinel-2 / Sentinel-1).")
    order_notify_email: str = Field(
        default="",
        description="Destino de notificaciones de nuevas solicitudes de estudio AgroGeoFísico.",
    )
    admin_emails: str = Field(
        default="",
        description="Correos bootstrap admin (coma-separados). Vacío = nadie por lista; usar rol en DB.",
    )
    otp_simulate: bool = Field(
        default=False,
        description="Si true, OTP fijo/depurable sin SMTP (solo desarrollo). En prod: false + SMTP.",
    )
    otp_ttl_sec: int = Field(default=600, ge=60, le=3600, description="TTL del OTP en segundos.")
    firms_map_key: str = Field(
        default="",
        description="NASA FIRMS MAP_KEY para validación VIIRS del módulo Fire.",
    )
    firms_live_cache_ttl_sec: int = Field(
        default=300,
        ge=0,
        description="TTL (s) de cache Redis/memoria para GET firms-live. 0 = sin cache.",
    )
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True
    snap_gpt_path: str = Field(
        default="",
        description=(
            "Ruta al ``gpt`` de **ESA SNAP** (p. ej. /opt/snap/bin/gpt). Vacío: autodetección priorizando "
            "/opt/snap y rutas ESA frente a un ``gpt`` genérico en PATH (evita confusión con la tienda "
            "Snap de Linux). Sin SNAP, recorte S1 con rasterio."
        ),
    )
    model_config = _settings_model_config()

    def bootstrap_admin_emails(self) -> set[str]:
        return {
            e.strip().lower()
            for e in (self.admin_emails or "").split(",")
            if e.strip()
        }

    def is_bootstrap_admin(self, email: str) -> bool:
        return str(email or "").strip().lower() in self.bootstrap_admin_emails()

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if not v or v.strip() in {"change-me-in-production", "super-secret-dev-key"}:
            raise ValueError("SECRET_KEY must be provided via environment and cannot use insecure defaults")
        return v.strip()

    @field_validator("access_token_expire_minutes")
    @classmethod
    def validate_access_expiry(cls, v: int) -> int:
        # Security baseline: access JWT must not exceed 15 minutes.
        if int(v) > 15:
            raise ValueError("ACCESS_TOKEN_EXPIRE_MINUTES must be <= 15")
        if int(v) < 1:
            raise ValueError("ACCESS_TOKEN_EXPIRE_MINUTES must be >= 1")
        return int(v)


settings = Settings()


def get_max_upload_mb() -> int:
    """Prioridad: variable de entorno MAX_UPLOAD_MB (Docker/compose), luego Settings."""
    raw = os.environ.get("MAX_UPLOAD_MB", "").strip()
    if raw:
        try:
            v = int(raw)
            return max(1, v)
        except ValueError:
            pass
    return max(1, int(settings.max_upload_mb))

