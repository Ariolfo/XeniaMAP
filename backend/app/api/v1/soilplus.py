"""SoilPlus + dashboard IA Planet — thin HTTP sobre ``application.agro.soilplus``."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_project_dashboard_access, tenant_from_jwt
from app.application.agro import soilplus as sp
from app.db.session import get_db
from app.models.models import User

router = APIRouter()
logger = logging.getLogger(__name__)


def _map_app_exc(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, RuntimeError):
        return HTTPException(status_code=500, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


def _call(fn, **kwargs):
    try:
        return fn(**kwargs)
    except (LookupError, ValueError, RuntimeError) as exc:
        raise _map_app_exc(exc) from exc


@router.get("/preprocess/dashboard-ia-planet-integral/{project_id}")
def dashboard_ia_planet_integral(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
    max_scenes: int = Query(36, ge=4, le=60),
):
    require_project_dashboard_access(db, user, tenant_id, project_id)
    return sp.build_dashboard_ia_planet_integral(
        project_id=project_id, tenant_id=tenant_id, max_scenes=max_scenes
    )


@router.get("/preprocess/ps-soilplus-f1/{project_id}")
def get_ps_soilplus_f1_exact(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    require_project_dashboard_access(db, user, tenant_id, project_id)
    return _call(sp.compute_ps_soilplus_f1_exact, project_id=project_id, tenant_id=tenant_id)


@router.get("/preprocess/soilplus-dem-input/{project_id}")
def get_soilplus_dem_input_stats(
    project_id: int,
    window_size: int = Query(13, ge=1, le=101),
    cv_engine: str = Query("fast"),
    roi_polygon: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    require_project_dashboard_access(db, user, tenant_id, project_id)
    return _call(
        sp.dem_input_stats,
        project_id=project_id,
        tenant_id=tenant_id,
        window_size=window_size,
        cv_engine=cv_engine,
        roi_polygon=roi_polygon,
    )


@router.get("/preprocess/soilplus-f123-terrain/{project_id}")
def get_soilplus_f123_terrain(
    project_id: int,
    roi_polygon: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    require_project_dashboard_access(db, user, tenant_id, project_id)
    return _call(
        sp.f123_terrain, project_id=project_id, tenant_id=tenant_id, roi_polygon=roi_polygon
    )


@router.get("/preprocess/soilplus-sampling-plan/{project_id}")
def get_soilplus_sampling_plan(
    project_id: int,
    window_size: int = Query(13, ge=1, le=101),
    cv_engine: str = Query("fast"),
    n_clusters: int = Query(4, ge=2, le=30),
    fishnet_step: int = Query(5, ge=1, le=80),
    roi_polygon: str | None = Query(None),
    total_samples: int | None = Query(None, ge=1, le=500000),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    require_project_dashboard_access(db, user, tenant_id, project_id)
    return _call(
        sp.sampling_plan,
        project_id=project_id,
        tenant_id=tenant_id,
        window_size=window_size,
        cv_engine=cv_engine,
        n_clusters=n_clusters,
        fishnet_step=fishnet_step,
        roi_polygon=roi_polygon,
        total_samples=total_samples,
    )


@router.post("/preprocess/soilplus-execute-save/{project_id}")
def post_soilplus_execute_save(
    project_id: int,
    window_size: int = Query(13, ge=1, le=101),
    cv_engine: str = Query("fast"),
    n_clusters: int = Query(4, ge=2, le=30),
    fishnet_step: int = Query(5, ge=1, le=80),
    roi_polygon: str | None = Query(None),
    total_samples: int | None = Query(None, ge=1, le=500000),
    cmap: str = Query("jet"),
    m: float = Query(2.0, ge=1.05, le=10.0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    require_project_dashboard_access(db, user, tenant_id, project_id)
    try:
        return sp.execute_save_bundle(
            project_id,
            tenant_id,
            window_size=window_size,
            cv_engine=cv_engine,
            n_clusters=n_clusters,
            fishnet_step=fishnet_step,
            roi_polygon=roi_polygon,
            total_samples=total_samples,
            cmap=cmap,
            m=m,
        )
    except (LookupError, ValueError, RuntimeError) as exc:
        raise _map_app_exc(exc) from exc
    except Exception as exc:
        logger.exception("soilplus execute-save")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/preprocess/soilplus-saved-summary/{project_id}")
def get_soilplus_saved_summary(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    require_project_dashboard_access(db, user, tenant_id, project_id)
    return sp.saved_summary(project_id=project_id, tenant_id=tenant_id)


@router.get("/preprocess/soilplus-saved-json/{project_id}")
def get_soilplus_saved_json(
    project_id: int,
    variant: str = Query("fast"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    require_project_dashboard_access(db, user, tenant_id, project_id)
    return _call(sp.saved_json, project_id=project_id, tenant_id=tenant_id, variant=variant)


@router.get("/preprocess/soilplus-saved-img/{project_id}")
def get_soilplus_saved_img(
    project_id: int,
    variant: str = Query("fast"),
    kind: str = Query("dem"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    require_project_dashboard_access(db, user, tenant_id, project_id)
    path = _call(
        sp.saved_img_path,
        project_id=project_id,
        tenant_id=tenant_id,
        variant=variant,
        kind=kind,
    )
    return FileResponse(path, media_type="image/png")


@router.get("/preprocess/soilplus-landing-mosaic/{project_id}")
def get_soilplus_landing_mosaic(
    project_id: int,
    variant: str = Query("matlab"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    require_project_dashboard_access(db, user, tenant_id, project_id)
    try:
        png = sp.build_landing_mosaic(project_id, tenant_id, variant=variant)
    except (LookupError, ValueError, RuntimeError) as exc:
        raise _map_app_exc(exc) from exc
    except Exception as exc:
        logger.exception("soilplus landing mosaic failed")
        raise HTTPException(status_code=500, detail=f"No se pudo generar el mosaico: {exc}") from exc
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


@router.get("/preprocess/soilplus-dem-preview/{project_id}")
def get_soilplus_dem_preview(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    require_project_dashboard_access(db, user, tenant_id, project_id)
    png = _call(sp.dem_preview_png, project_id=project_id, tenant_id=tenant_id)
    return Response(content=png, media_type="image/png")


@router.get("/preprocess/soilplus-cv-preview/{project_id}")
def get_soilplus_cv_preview(
    project_id: int,
    window_size: int = Query(13, ge=1, le=101),
    cv_engine: str = Query("fast"),
    roi_polygon: str | None = Query(None),
    cmap: str = Query("jet"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    require_project_dashboard_access(db, user, tenant_id, project_id)
    png = _call(
        sp.cv_preview_png,
        project_id=project_id,
        tenant_id=tenant_id,
        window_size=window_size,
        cv_engine=cv_engine,
        roi_polygon=roi_polygon,
        cmap=cmap,
    )
    return Response(content=png, media_type="image/png")


@router.get("/preprocess/soilplus-aspect-preview/{project_id}")
def get_soilplus_aspect_preview(
    project_id: int,
    roi_polygon: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    require_project_dashboard_access(db, user, tenant_id, project_id)
    png = _call(
        sp.aspect_preview_png,
        project_id=project_id,
        tenant_id=tenant_id,
        roi_polygon=roi_polygon,
    )
    return Response(content=png, media_type="image/png")


@router.get("/preprocess/soilplus-slope-preview/{project_id}")
def get_soilplus_slope_preview(
    project_id: int,
    roi_polygon: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    require_project_dashboard_access(db, user, tenant_id, project_id)
    png = _call(
        sp.slope_preview_png,
        project_id=project_id,
        tenant_id=tenant_id,
        roi_polygon=roi_polygon,
    )
    return Response(content=png, media_type="image/png")


@router.get("/preprocess/soilplus-q-curve/{project_id}")
def get_soilplus_q_curve(
    project_id: int,
    window_size: int = Query(13, ge=1, le=101),
    cv_engine: str = Query("fast"),
    k_min: int = Query(2, ge=2, le=30),
    k_max: int = Query(11, ge=2, le=30),
    roi_polygon: str | None = Query(None),
    m: float = Query(2.0, ge=1.05, le=10.0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    require_project_dashboard_access(db, user, tenant_id, project_id)
    return _call(
        sp.q_curve,
        project_id=project_id,
        tenant_id=tenant_id,
        window_size=window_size,
        cv_engine=cv_engine,
        k_min=k_min,
        k_max=k_max,
        roi_polygon=roi_polygon,
        m=m,
    )


@router.get("/preprocess/soilplus-fcm-cv-preview/{project_id}")
def get_soilplus_fcm_cv_preview(
    project_id: int,
    window_size: int = Query(13, ge=1, le=101),
    cv_engine: str = Query("fast"),
    n_clusters: int = Query(4, ge=2, le=30),
    roi_polygon: str | None = Query(None),
    m: float = Query(2.0, ge=1.05, le=10.0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    require_project_dashboard_access(db, user, tenant_id, project_id)
    png = _call(
        sp.fcm_cv_preview_png,
        project_id=project_id,
        tenant_id=tenant_id,
        window_size=window_size,
        cv_engine=cv_engine,
        n_clusters=n_clusters,
        roi_polygon=roi_polygon,
        m=m,
    )
    return Response(content=png, media_type="image/png")


@router.get("/preprocess/soilplus-elbow/{project_id}")
def get_soilplus_elbow(
    project_id: int,
    k_min: int = Query(2, ge=2, le=20),
    k_max: int = Query(10, ge=2, le=30),
    sample_max: int = Query(20000, ge=2000, le=120000),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    require_project_dashboard_access(db, user, tenant_id, project_id)
    return _call(
        sp.elbow_curve,
        project_id=project_id,
        tenant_id=tenant_id,
        k_min=k_min,
        k_max=k_max,
        sample_max=sample_max,
    )


@router.get("/preprocess/soilplus-cluster-preview/{project_id}")
def get_soilplus_cluster_preview(
    project_id: int,
    n_clusters: int = Query(4, ge=2, le=30),
    sample_max: int = Query(20000, ge=2000, le=120000),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(tenant_from_jwt),
):
    require_project_dashboard_access(db, user, tenant_id, project_id)
    png = _call(
        sp.kmeans_cluster_preview_png,
        project_id=project_id,
        tenant_id=tenant_id,
        n_clusters=n_clusters,
        sample_max=sample_max,
    )
    return Response(content=png, media_type="image/png")
