from pathlib import Path

from app.core.config import settings


def _tenant_storage(tenant_id: int, project_id: int, kind: str) -> Path:
    base = Path(settings.storage_path) / f"tenant_{tenant_id}" / f"project_{project_id}" / kind
    base.mkdir(parents=True, exist_ok=True)
    return base


# Nombre correcto en disco. Historico: typo ``s1prepoceso`` (sin la r de proceso).
S1_PREPROCESO_DIR_NAME = "s1preproceso"
S1_PREPROCESO_DIR_NAME_LEGACY = "s1prepoceso"


def project_s1_preproceso_dir(tenant_id: int, project_id: int, *, create: bool = False) -> Path:
    """
    Carpeta de sigma0 ENVI/SNAP del proyecto: ``s1preproceso/``.

    Preferencia: ``s1preproceso`` si existe; si no, legacy ``s1prepoceso``.
    Con ``create=True`` y ninguna existe, crea ``s1preproceso``.
    """
    root = Path(settings.storage_path) / f"tenant_{tenant_id}" / f"project_{project_id}"
    preferred = root / S1_PREPROCESO_DIR_NAME
    legacy = root / S1_PREPROCESO_DIR_NAME_LEGACY
    if preferred.is_dir():
        return preferred
    if legacy.is_dir():
        return legacy
    if create:
        preferred.mkdir(parents=True, exist_ok=True)
    return preferred


def project_downloads_slug(project_name: str) -> str:
    """Subcarpeta bajo downloads/ por proyecto; debe coincidir en todo el backend."""
    return project_name.replace(" ", "_").lower()


def project_downloads_dir(tenant_id: int, project_id: int, project_name: str) -> Path:
    """Raíz de descargas del proyecto: ``downloads/<slug>/`` (contiene Sentinel1/, Sentinel2/, …)."""
    slug = project_downloads_slug(project_name)
    return _tenant_storage(tenant_id, project_id, "downloads") / slug


def project_sentinel2_dir(tenant_id: int, project_id: int, project_name: str) -> Path:
    """Carpeta de productos Sentinel-2: ``downloads/<slug>/Sentinel2/``."""
    return project_downloads_dir(tenant_id, project_id, project_name) / "Sentinel2"


def project_sentinel1_dir(tenant_id: int, project_id: int, project_name: str) -> Path:
    """Carpeta de productos Sentinel-1: ``downloads/<slug>/Sentinel1/``."""
    return project_downloads_dir(tenant_id, project_id, project_name) / "Sentinel1"


def project_root_path(tenant_id: int, project_id: int) -> Path:
    """Raíz del proyecto en almacenamiento: ``storage/tenant_*/project_*/``."""
    return (Path(settings.storage_path) / f"tenant_{tenant_id}" / f"project_{project_id}").resolve()


def resolve_project_subpath(tenant_id: int, project_id: int, source_subpath: str | None) -> Path | None:
    """
    Resuelve una ruta relativa bajo la raíz del proyecto.
    ``None`` → no resuelve (el llamador usa el default del sensor).
    Cadena vacía → raíz del proyecto.
    Devuelve ``None`` si la ruta es inválida (``..`` o fuera del proyecto).
    """
    if source_subpath is None:
        return None
    pr = project_root_path(tenant_id, project_id)
    rel = str(source_subpath).strip().replace("\\", "/")
    parts = [x for x in rel.split("/") if x and x != "."]
    cur = pr
    for part in parts:
        if part == "..":
            return None
        cur = (cur / part).resolve()
    try:
        cur.relative_to(pr)
    except ValueError:
        return None
    return cur


EXTERNAL_SOURCE_PREFIX = "ext:"


def external_data_root_path() -> Path | None:
    """Raíz configurada de datos externos (``EXTERNAL_DATA_ROOT``), o ``None`` si no aplica."""
    raw = (settings.external_data_root or "").strip()
    if not raw:
        return None
    p = Path(raw).expanduser().resolve()
    if not p.is_dir():
        return None
    return p


def is_external_source_subpath(source_subpath: str | None) -> bool:
    if source_subpath is None:
        return False
    return str(source_subpath).strip().startswith(EXTERNAL_SOURCE_PREFIX)


def encode_external_subpath(rel_posix: str | None) -> str:
    """Codifica ruta relativa bajo el disco externo como ``ext:`` / ``ext:carpeta/…``."""
    rel = str(rel_posix or "").strip().replace("\\", "/").lstrip("/")
    parts = [p for p in rel.split("/") if p and p != "."]
    if any(p == ".." for p in parts):
        return EXTERNAL_SOURCE_PREFIX
    return EXTERNAL_SOURCE_PREFIX + "/".join(parts)


def resolve_external_subpath(source_subpath: str) -> Path | None:
    """
    Resuelve ``ext:`` / ``ext:rel/path`` bajo ``EXTERNAL_DATA_ROOT``.
    Rechaza ``..`` y rutas fuera de la raíz.
    """
    root = external_data_root_path()
    if root is None:
        return None
    raw = str(source_subpath or "").strip().replace("\\", "/")
    if not raw.startswith(EXTERNAL_SOURCE_PREFIX):
        return None
    rel = raw[len(EXTERNAL_SOURCE_PREFIX) :].lstrip("/")
    parts = [p for p in rel.split("/") if p and p != "."]
    if any(p == ".." for p in parts):
        return None
    cur = root
    for part in parts:
        cur = (cur / part).resolve()
    try:
        cur.relative_to(root)
    except ValueError:
        return None
    return cur


def resolve_source_subpath(tenant_id: int, project_id: int, source_subpath: str | None) -> Path | None:
    """
    Resuelve origen de recorte: proyecto (relativo) o disco externo (``ext:…``).
    ``None`` → el llamador usa el default del sensor.
    """
    if source_subpath is None:
        return None
    if is_external_source_subpath(source_subpath):
        return resolve_external_subpath(source_subpath)
    return resolve_project_subpath(tenant_id, project_id, source_subpath)


def encode_source_subpath_for_path(
    tenant_id: int, project_id: int, absolute: Path, requested: str | None
) -> str | None:
    """Devuelve el ``source_subpath`` a persistir (``ext:…`` o relativo al proyecto)."""
    if requested is None:
        return None
    if is_external_source_subpath(requested):
        root = external_data_root_path()
        if root is None:
            return requested
        try:
            return encode_external_subpath(absolute.resolve().relative_to(root).as_posix())
        except ValueError:
            return requested
    return project_relative_posix(tenant_id, project_id, absolute)


def ensure_external_sensor_download_dirs(download_subpath: str, sensor: str) -> tuple[Path, Path, str]:
    """
    Resuelve carpeta destino en el disco externo para descarga S1/S2.

    ``download_subpath``: ``ext:`` o ``ext:carpeta/…`` (carpeta elegida por el usuario).
    Crea ``Sentinel1/`` o ``Sentinel2/`` dentro si no existen.
    Si la carpeta elegida ya se llama Sentinel1/Sentinel2, se usa directamente.

    Returns:
        (sensor_dir, parent_for_s1_job, encoded_ext_subpath_of_sensor_dir)
        ``parent_for_s1_job`` es el padre que espera ``search_filter_and_download``
        (crea Sentinel1 dentro).
    """
    sensor_key = str(sensor or "").strip().lower()
    folder_name = {"s1": "Sentinel1", "s2": "Sentinel2", "sentinel-1": "Sentinel1", "sentinel-2": "Sentinel2"}.get(
        sensor_key
    )
    if not folder_name:
        raise ValueError("sensor debe ser s1/s2 (o sentinel-1/sentinel-2)")
    root = external_data_root_path()
    if root is None:
        raise ValueError("Disco externo no configurado o no montado (EXTERNAL_DATA_ROOT)")
    if not is_external_source_subpath(download_subpath):
        raise ValueError("download_subpath debe ser una ruta ext: bajo el disco externo")
    parent = resolve_external_subpath(download_subpath)
    if parent is None:
        raise ValueError("Ruta de descarga inválida o fuera del disco externo")
    if not parent.exists():
        parent.mkdir(parents=True, exist_ok=True)
    if not parent.is_dir():
        raise ValueError("La ruta de descarga no es una carpeta")

    if parent.name == folder_name:
        sensor_dir = parent
        s1_parent = parent.parent
    else:
        sensor_dir = parent / folder_name
        s1_parent = parent
    sensor_dir.mkdir(parents=True, exist_ok=True)
    try:
        rel = sensor_dir.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError("Destino fuera del disco externo") from exc
    return sensor_dir, s1_parent, encode_external_subpath(rel)


def project_relative_posix(tenant_id: int, project_id: int, absolute: Path) -> str:
    """Ruta posix relativa a la raíz del proyecto, o ``""`` si es la raíz."""
    pr = project_root_path(tenant_id, project_id)
    try:
        return absolute.resolve().relative_to(pr).as_posix()
    except ValueError:
        return ""
