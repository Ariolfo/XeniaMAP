from fastapi import APIRouter

from app.api.v1.ai import router as ai_router
from app.api.v1.auth import router as auth_router
from app.api.v1.cluster_analysis import router as cluster_analysis_router
from app.api.v1.fire_orders import router as fire_orders_router
from app.api.v1.landing_texts import router as landing_texts_router
from app.api.v1.layers import router as layers_router
from app.api.v1.preprocess import router as preprocess_router
from app.api.v1.projects import router as projects_router
from app.api.v1.rasters import router as rasters_router
from app.api.v1.rasters_admin import router as rasters_admin_router
from app.api.v1.soilplus import router as soilplus_router
from app.api.v1.study_orders import router as study_orders_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(projects_router)
router.include_router(landing_texts_router)
router.include_router(layers_router)
# Admin browse/inventory antes que ``/raster/{project_id}`` del mapa.
router.include_router(rasters_admin_router)
router.include_router(rasters_router)
router.include_router(ai_router)
router.include_router(preprocess_router)
router.include_router(soilplus_router)
router.include_router(cluster_analysis_router)
router.include_router(study_orders_router)
router.include_router(fire_orders_router)
