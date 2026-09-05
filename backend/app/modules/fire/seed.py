"""Seed Tolima municipality fire requests from bundled AOI."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.models import FireOrder, User
from app.modules.fire.project_link import ensure_fire_order_project

AOI_DIR = Path(__file__).resolve().parent / "aoi"
SEED_JSON = AOI_DIR / "tolima_seed.json"

DEFAULT_PRE_START = date(2026, 7, 1)
DEFAULT_PRE_END = date(2026, 7, 31)
DEFAULT_POST_START = date(2026, 8, 8)
DEFAULT_MAX_CLOUD = 95.0


def load_seed_features() -> list[dict]:
    if not SEED_JSON.exists():
        raise FileNotFoundError(f"Seed file missing: {SEED_JSON}")
    data = json.loads(SEED_JSON.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise RuntimeError("Seed file is empty or invalid")
    return data


def seed_tolima_fire_orders(
    db: Session,
    admin: User,
    *,
    applicant: User | None = None,
    applicant_email: str | None = None,
) -> dict:
    """
    Create one FireOrder per municipality (MpNombre) if missing.
    Idempotent via source_key ``tolima:<MpNombre>``.

    If ``applicant`` / ``applicant_email`` is provided, requests are attributed
    to that user (solicitante). Otherwise they stay as generic Tolima preload.
    """
    features = load_seed_features()
    created = []
    skipped = []
    post_end = date.today()

    target = applicant
    if target is None and applicant_email:
        email = str(applicant_email).strip().lower()
        target = db.query(User).filter(User.email == email).first()
        if not target:
            raise ValueError(f"Usuario solicitante no encontrado: {applicant_email}")

    if target is not None:
        sol_name = (target.full_name or "").strip() or target.email
        sol_email = target.email
        sol_phone = "N/A"
        company = "Solicitud Fire — usuario XeniaMAP"
        notes = (
            f"Solicitud precargada desde Incendios_Tolima.shp para {target.email} "
            "(un municipio = una solicitud)."
        )
        owner_id = target.id
        tenant_id = target.tenant_id
    else:
        sol_name = "Gobernación del Tolima / precarga Tolima"
        sol_email = "tolima.incendios@xeniamap.local"
        sol_phone = "N/A"
        company = "Tolima — precarga AOI Incendios"
        notes = "Solicitud precargada desde Incendios_Tolima.shp (un municipio = una solicitud)."
        owner_id = admin.id
        tenant_id = admin.tenant_id

    for feat in features:
        name = str(feat.get("MpNombre") or "").strip()
        dept = str(feat.get("Depto") or "").strip()
        geom = feat.get("geometry")
        if not name or not geom:
            continue
        source_key = f"tolima:{name}"
        existing = db.query(FireOrder).filter(FireOrder.source_key == source_key).first()
        if existing:
            # Reassign solicitante if targeting a specific user.
            if target is not None:
                existing.applicant_name = sol_name
                existing.applicant_email = sol_email
                existing.applicant_phone = sol_phone
                existing.company = company
                existing.created_by_user_id = owner_id
                existing.tenant_id = tenant_id
                existing.extra_notes = notes
                ensure_fire_order_project(db, existing, target)
                skipped.append(
                    {
                        "id": existing.id,
                        "request_name": existing.request_name,
                        "reassigned_to": sol_email,
                        "project_id": existing.project_id,
                    }
                )
            else:
                skipped.append({"id": existing.id, "request_name": existing.request_name})
            continue

        order = FireOrder(
            tenant_id=tenant_id,
            created_by_user_id=owner_id,
            request_name=name,
            department=dept or None,
            applicant_name=sol_name,
            applicant_email=sol_email,
            applicant_phone=sol_phone,
            company=company,
            geometry_geojson={
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"MpNombre": name, "Depto": dept},
                        "geometry": geom,
                    }
                ],
            },
            pre_start=DEFAULT_PRE_START,
            pre_end=DEFAULT_PRE_END,
            post_start=DEFAULT_POST_START,
            post_end=post_end,
            max_cloud_cover=int(DEFAULT_MAX_CLOUD),
            status="pendiente",
            source_key=source_key,
            extra_notes=notes,
        )
        db.add(order)
        db.flush()
        ensure_fire_order_project(db, order, target if target is not None else admin)
        created.append(
            {
                "id": order.id,
                "request_name": order.request_name,
                "applicant_email": sol_email,
                "project_id": order.project_id,
            }
        )

    db.commit()
    return {
        "created_count": len(created),
        "skipped_count": len(skipped),
        "created": created,
        "skipped": skipped,
        "applicant_email": sol_email,
        "defaults": {
            "pre_start": DEFAULT_PRE_START.isoformat(),
            "pre_end": DEFAULT_PRE_END.isoformat(),
            "post_start": DEFAULT_POST_START.isoformat(),
            "post_end": post_end.isoformat(),
            "max_cloud_cover": DEFAULT_MAX_CLOUD,
        },
    }
