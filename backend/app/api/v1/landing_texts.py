"""API: textos narrativos de la landing (draft / published) por subsección."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin, require_project_dashboard_access, tenant_from_jwt
from app.api.v1.helpers import _tenant_storage
from app.core.image_upload import InvalidImageUpload, mime_for_image_path, validate_raster_image_bytes
from app.db.session import get_db
from app.models.models import ProjectLandingText, User
from app.schemas.schemas import (
    LandingTextsResponse,
    LandingTextsUpsertRequest,
    LandingTextItem,
)

router = APIRouter()

# Subsecciones canónicas (mismo criterio que frontend landingNavConfig SUBSECTION_DEFS).
LANDING_SECTION_SUFFIXES = (
    "interactive",
    "rgb",
    "rgb-vv",
    "rgb-vh",
    "indices",
    "clusters",
    "smart-clusters",
    "agrogeofisica",
    "ia",
)
LANDING_SENSOR_KEYS = ("ps", "s1", "s2")
LANDING_INDEX_KEYS = (
    "NDVI",
    "EVI",
    "KNDVI",
    "MSAVI2",
    "MTVI2",
    "CIre",
    "MCARI",
    "NDRE",
    "TGI",
    "NDWI",
    "VARI",
    "GIYI",
    "RSTRUCTURE",
    "RVI",
    "RFDI",
    "VV_VH",
    "VH_VV",
    "NRPB",
)
_INDEX_KEY_RE = re.compile(r"^landing-(ps|s1|s2)-index-([A-Za-z0-9_]+)$")
_MEDIA_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_ALLOWED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
_INDEX_KEYS_UPPER = {x.upper() for x in LANDING_INDEX_KEYS}


def canonical_section_keys() -> list[str]:
    # Índices ópticos reales por sensor (CIre solo S2; PS usa catálogo Planet).
    optical_by_sensor = {
        "ps": {
            "NDVI",
            "EVI",
            "NDWI",
            "MSAVI2",
            "MTVI2",
            "VARI",
            "TGI",
            "KNDVI",
            "GIYI",
            "MCARI",
            "NDRE",
            "RSTRUCTURE",
        },
        "s2": {"NDVI", "EVI", "NDWI", "CIre", "MCARI"},
        "s1": {"RVI", "RFDI", "VV_VH", "VH_VV", "NRPB"},
    }
    keys: list[str] = []
    for sensor in LANDING_SENSOR_KEYS:
        for suffix in LANDING_SECTION_SUFFIXES:
            if suffix == "ia" and sensor != "ps":
                continue
            if suffix in ("rgb-vv", "rgb-vh") and sensor != "s1":
                continue
            if suffix == "rgb" and sensor == "s1":
                continue
            keys.append(f"landing-{sensor}-{suffix}")
        allow = optical_by_sensor.get(sensor) or set()
        for ik in LANDING_INDEX_KEYS:
            if ik in allow or ik.upper() in {x.upper() for x in allow}:
                keys.append(f"landing-{sensor}-index-{ik}")
    return keys


def _is_valid_section_key(key: str) -> bool:
    k = str(key or "").strip()
    if not k.startswith("landing-"):
        return False
    m = _INDEX_KEY_RE.match(k)
    if m:
        return m.group(2).upper() in _INDEX_KEYS_UPPER
    parts = k.split("-", 2)
    if len(parts) < 3:
        return False
    sensor = parts[1]
    suffix = parts[2]
    if sensor not in LANDING_SENSOR_KEYS:
        return False
    if suffix == "ia" and sensor != "ps":
        return False
    if suffix in ("rgb-vv", "rgb-vh") and sensor != "s1":
        return False
    if suffix == "rgb" and sensor == "s1":
        # Se permite por compatibilidad con textos antiguos; la UI usa rgb-vv / rgb-vh.
        return True
    return suffix in LANDING_SECTION_SUFFIXES


def _landing_media_dir(tenant_id: int, project_id: int) -> Path:
    return _tenant_storage(tenant_id, project_id, "landing_media")


def _row_to_item(row: ProjectLandingText) -> LandingTextItem:
    return LandingTextItem(
        section_key=row.section_key,
        draft_body=row.draft_body or "",
        published_body=row.published_body or "",
        updated_at=row.updated_at.isoformat() + "Z" if row.updated_at else None,
        published_at=row.published_at.isoformat() + "Z" if row.published_at else None,
    )


def _has_unpublished(rows: list[ProjectLandingText]) -> bool:
    for r in rows:
        d = (r.draft_body or "").strip()
        p = (r.published_body or "").strip()
        if d != p:
            return True
    return False


@router.get("/projects/{project_id}/landing-texts", response_model=LandingTextsResponse)
def get_landing_texts(
    project_id: int,
    view: str = Query(
        "auto",
        description="auto | draft | published. Cliente siempre recibe published. Admin: draft por defecto en auto.",
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    require_project_dashboard_access(db, user, tenant_id, project_id)
    role = str(user.role or "").strip().lower()
    is_admin = role == "admin"
    view_norm = (view or "auto").strip().lower()
    if view_norm not in {"auto", "draft", "published"}:
        raise HTTPException(status_code=400, detail="view debe ser auto, draft o published")

    rows = (
        db.query(ProjectLandingText)
        .filter(
            ProjectLandingText.project_id == project_id,
            ProjectLandingText.tenant_id == tenant_id,
        )
        .order_by(ProjectLandingText.section_key.asc())
        .all()
    )

    # Cliente (u auto no-admin): solo cuerpos publicados; no filtrar filas vacías aquí
    # (el front decide no renderizar si body vacío). En draft se incluyen draft_body.
    if not is_admin or view_norm == "published" or (view_norm == "auto" and not is_admin):
        # Forzar published_body visible; draft_body vacío en respuesta al cliente
        items = [
            LandingTextItem(
                section_key=r.section_key,
                draft_body="",
                published_body=r.published_body or "",
                updated_at=r.updated_at.isoformat() + "Z" if r.updated_at else None,
                published_at=r.published_at.isoformat() + "Z" if r.published_at else None,
            )
            for r in rows
        ]
        return LandingTextsResponse(
            project_id=project_id,
            texts=items,
            has_unpublished_drafts=False,
        )

    items = [_row_to_item(r) for r in rows]
    return LandingTextsResponse(
        project_id=project_id,
        texts=items,
        has_unpublished_drafts=_has_unpublished(rows),
    )


@router.put("/projects/{project_id}/landing-texts", response_model=LandingTextsResponse)
def upsert_landing_texts(
    project_id: int,
    payload: LandingTextsUpsertRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
    tenant_id: int = Depends(tenant_from_jwt),
):
    require_project_dashboard_access(db, admin, tenant_id, project_id)
    now = datetime.utcnow()
    for item in payload.texts or []:
        key = str(item.section_key or "").strip()
        if not _is_valid_section_key(key):
            raise HTTPException(status_code=400, detail=f"section_key inválida: {key}")
        row = (
            db.query(ProjectLandingText)
            .filter(
                ProjectLandingText.project_id == project_id,
                ProjectLandingText.section_key == key,
            )
            .first()
        )
        body = item.draft_body if item.draft_body is not None else ""
        if row is None:
            row = ProjectLandingText(
                project_id=project_id,
                tenant_id=tenant_id,
                section_key=key,
                draft_body=body,
                published_body="",
                updated_by_user_id=admin.id,
                updated_at=now,
                created_at=now,
            )
            db.add(row)
        else:
            row.draft_body = body
            row.updated_by_user_id = admin.id
            row.updated_at = now
            row.tenant_id = tenant_id
    db.commit()

    rows = (
        db.query(ProjectLandingText)
        .filter(
            ProjectLandingText.project_id == project_id,
            ProjectLandingText.tenant_id == tenant_id,
        )
        .order_by(ProjectLandingText.section_key.asc())
        .all()
    )
    return LandingTextsResponse(
        project_id=project_id,
        texts=[_row_to_item(r) for r in rows],
        has_unpublished_drafts=_has_unpublished(rows),
    )


@router.post("/projects/{project_id}/landing-texts/publish", response_model=LandingTextsResponse)
def publish_landing_texts(
    project_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
    tenant_id: int = Depends(tenant_from_jwt),
):
    """Copia draft_body → published_body en todas las filas del proyecto."""
    require_project_dashboard_access(db, admin, tenant_id, project_id)
    now = datetime.utcnow()
    rows = (
        db.query(ProjectLandingText)
        .filter(
            ProjectLandingText.project_id == project_id,
            ProjectLandingText.tenant_id == tenant_id,
        )
        .all()
    )
    if not rows:
        raise HTTPException(
            status_code=400,
            detail="No hay textos de landing guardados. Guarda borradores antes de publicar.",
        )
    for row in rows:
        row.published_body = row.draft_body or ""
        row.published_at = now
        row.updated_by_user_id = admin.id
        row.updated_at = now
    db.commit()

    rows = (
        db.query(ProjectLandingText)
        .filter(
            ProjectLandingText.project_id == project_id,
            ProjectLandingText.tenant_id == tenant_id,
        )
        .order_by(ProjectLandingText.section_key.asc())
        .all()
    )
    return LandingTextsResponse(
        project_id=project_id,
        texts=[_row_to_item(r) for r in rows],
        has_unpublished_drafts=False,
    )


@router.post("/projects/{project_id}/landing-media")
async def upload_landing_media(
    project_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
    tenant_id: int = Depends(tenant_from_jwt),
):
    """Sube una imagen para incrustar en la narrativa (Informe inteligente / Markdown)."""
    require_project_dashboard_access(db, admin, tenant_id, project_id)
    original = Path(str(file.filename or "image.png")).name
    claimed_ext = Path(original).suffix.lower()
    if claimed_ext not in _ALLOWED_IMAGE_EXT:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Formato no soportado ({claimed_ext or 'sin extensión'}). "
                f"Use: {', '.join(sorted(_ALLOWED_IMAGE_EXT))}"
            ),
        )
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Archivo vacío")
    if len(content) > 12 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="La imagen supera 12 MB")

    try:
        # F10: magic bytes / decode (Pillow); extensión canónica según contenido real.
        ext, _media_type = validate_raster_image_bytes(content, claimed_ext=claimed_ext)
    except InvalidImageUpload as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    media_dir = _landing_media_dir(tenant_id, project_id)
    media_dir.mkdir(parents=True, exist_ok=True)
    safe_stem = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(original).stem).strip("_")[:60] or "img"
    filename = f"{safe_stem}_{uuid.uuid4().hex[:10]}{ext}"
    dest = media_dir / filename
    dest.write_bytes(content)

    url = f"/api/v1/projects/{project_id}/landing-media/{filename}"
    alt = safe_stem.replace("_", " ")
    return {
        "filename": filename,
        "url": url,
        "markdown": f"![{alt}]({url})",
        "bytes": len(content),
    }


@router.get("/projects/{project_id}/landing-media/{filename}")
def get_landing_media(
    project_id: int,
    filename: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    """Sirve una imagen subida para la narrativa del landing."""
    require_project_dashboard_access(db, user, tenant_id, project_id)
    name = Path(str(filename or "")).name
    if not _MEDIA_NAME_RE.match(name):
        raise HTTPException(status_code=400, detail="Nombre de archivo inválido")
    path = (_landing_media_dir(tenant_id, project_id) / name).resolve()
    root = _landing_media_dir(tenant_id, project_id).resolve()
    if not path.is_file() or not path.is_relative_to(root):
        raise HTTPException(status_code=404, detail="Imagen no encontrada")
    media = mime_for_image_path(path.suffix)
    return FileResponse(
        path,
        media_type=media,
        headers={
            "Content-Disposition": f'inline; filename="{name}"',
            "X-Content-Type-Options": "nosniff",
        },
    )
