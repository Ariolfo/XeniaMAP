"""Create client-visible Project + polygon Layer for each FireOrder."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.storage_paths import _tenant_storage
from app.core.config import settings
from app.models.models import FireOrder, Layer, Project, User


def ensure_fire_order_project(db: Session, order: FireOrder, owner: User) -> Project:
    """
    Ensure the Fire order has a Project owned by ``owner`` (module=fire)
    and a vector layer with the request polygon.
    """
    if order.project_id:
        existing = db.query(Project).filter(Project.id == order.project_id).first()
        if existing:
            # Keep ownership aligned with applicant.
            if existing.owner_user_id != owner.id:
                existing.owner_user_id = owner.id
                existing.tenant_id = owner.tenant_id
            if getattr(existing, "module", None) != "fire":
                existing.module = "fire"
            return existing

    project_name = f"Fire — {order.request_name}"
    # Reuse same-named Fire project for this owner if already present.
    project = (
        db.query(Project)
        .filter(
            Project.owner_user_id == owner.id,
            Project.name == project_name,
            Project.module == "fire",
        )
        .first()
    )
    if not project:
        # Legacy: same name without module tag
        project = (
            db.query(Project)
            .filter(Project.owner_user_id == owner.id, Project.name == project_name)
            .first()
        )
        if project and getattr(project, "module", None) != "fire":
            project.module = "fire"
    if not project:
        project = Project(
            name=project_name,
            owner_user_id=owner.id,
            tenant_id=owner.tenant_id,
            status="enproceso",
            module="fire",
        )
        db.add(project)
        db.flush()
    else:
        if getattr(project, "module", None) != "fire":
            project.module = "fire"

    order.project_id = project.id
    # Keep order tenant aligned with the client who will see the project.
    order.tenant_id = owner.tenant_id

    # Persist polygon as project vector layer (same pattern as study-orders).
    out_dir = _tenant_storage(owner.tenant_id, project.id, "vectors")
    geojson_path = out_dir / "fire_poligono_solicitud.geojson"
    geom = order.geometry_geojson or {}
    geojson_path.write_text(json.dumps(geom, ensure_ascii=False), encoding="utf-8")

    layer = (
        db.query(Layer)
        .filter(
            Layer.project_id == project.id,
            Layer.name == "Polígono Fire",
        )
        .first()
    )
    if not layer:
        db.add(
            Layer(
                project_id=project.id,
                tenant_id=owner.tenant_id,
                name="Polígono Fire",
                file_path=str(geojson_path),
                geom_type="Vector",
                layer_metadata={
                    "source_name": "fire_poligono_solicitud.geojson",
                    "auto_created": True,
                    "module": "fire",
                    "fire_order_id": order.id,
                    "municipality": order.request_name,
                    "department": order.department,
                },
            )
        )
    else:
        layer.file_path = str(geojson_path)
        meta = dict(layer.layer_metadata or {})
        meta.update(
            {
                "module": "fire",
                "fire_order_id": order.id,
                "municipality": order.request_name,
                "department": order.department,
            }
        )
        layer.layer_metadata = meta

    return project


def materialize_fire_projects_for_applicant(
    db: Session,
    *,
    applicant_email: str,
) -> dict:
    """Create/link Project+Layer for all Fire orders of an applicant email."""
    email = str(applicant_email or "").strip().lower()
    owner = db.query(User).filter(User.email == email).first()
    if not owner:
        raise ValueError(f"Usuario no encontrado: {applicant_email}")

    orders = (
        db.query(FireOrder)
        .filter(FireOrder.applicant_email == email)
        .order_by(FireOrder.id.asc())
        .all()
    )
    # Also include orders created_by this user without email match.
    if not orders:
        orders = (
            db.query(FireOrder)
            .filter(FireOrder.created_by_user_id == owner.id)
            .order_by(FireOrder.id.asc())
            .all()
        )

    created = []
    linked = []
    for order in orders:
        had_project = bool(order.project_id)
        project = ensure_fire_order_project(db, order, owner)
        item = {
            "fire_order_id": order.id,
            "request_name": order.request_name,
            "project_id": project.id,
            "project_name": project.name,
        }
        if had_project:
            linked.append(item)
        else:
            created.append(item)

    db.commit()
    return {
        "applicant_email": email,
        "owner_user_id": owner.id,
        "created_projects": created,
        "linked_projects": linked,
        "total": len(created) + len(linked),
        "storage_hint": str(Path(settings.storage_path) / f"tenant_{owner.tenant_id}"),
    }
