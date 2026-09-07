import logging
import os
import re

import redis as redis_lib
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.v1.routes import router as v1_router
from app.core.auth_cookies import ACCESS_COOKIE
from app.core.config import get_max_upload_mb, settings
from app.core.rate_limit import is_auth_rate_limited_path
from app.core.security import decode_token

logging.basicConfig(level=logging.INFO)
audit_logger = logging.getLogger("audit")
logger = logging.getLogger(__name__)

# Schema managed by Alembic migrations (run: alembic upgrade head)

app = FastAPI(title=settings.app_name)
_cors_regex = settings.cors_origin_regex.strip() or None
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_origin_regex=_cors_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Fire-Bounds", "X-Fire-Filename"],
)
app.include_router(v1_router, prefix=settings.api_v1_prefix)
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# Cliente: solo list + preview (no browse/inventory admin bajo /raster/*).
_CLIENTE_RASTER_GET_RE = re.compile(
    rf"^{re.escape(settings.api_v1_prefix)}/raster/\d+(?:/\d+/preview)?/?$"
)


@app.on_event("startup")
def _log_upload_limit() -> None:
    logger.info(
        "Subidas: límite efectivo %s MB (env MAX_UPLOAD_MB=%r)",
        get_max_upload_mb(),
        os.environ.get("MAX_UPLOAD_MB"),
    )
    logger.info("Almacenamiento: STORAGE_PATH=%r", settings.storage_path)

_redis_client = None


def _bearer_token_from_request(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "").strip()
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        if token:
            return token
    cookie = request.cookies.get(ACCESS_COOKIE)
    return cookie or None


def _is_cliente_allowed_request(request: Request) -> bool:
    path = request.url.path
    method = request.method.upper()
    if not path.startswith(settings.api_v1_prefix):
        return True
    if path.startswith(f"{settings.api_v1_prefix}/study-orders") and method == "POST":
        return True
    if path.startswith(f"{settings.api_v1_prefix}/auth"):
        return True
    if method == "GET" and _CLIENTE_RASTER_GET_RE.match(path):
        return True
    if method == "GET" and (
        path.startswith(f"{settings.api_v1_prefix}/projects")
        or path.startswith(f"{settings.api_v1_prefix}/layers")
        or path.startswith(f"{settings.api_v1_prefix}/preprocess/")
        or path.startswith(f"{settings.api_v1_prefix}/cluster-analysis/")
        or path.startswith(f"{settings.api_v1_prefix}/fire-orders")
    ):
        return True
    if method == "DELETE":
        projects_prefix = f"{settings.api_v1_prefix}/projects/"
        if path.startswith(projects_prefix):
            project_id_part = path[len(projects_prefix) :].strip("/")
            if project_id_part.isdigit():
                return True
    if method == "POST" and path in (
        f"{settings.api_v1_prefix}/preprocess/vegetation-time-series",
        f"{settings.api_v1_prefix}/preprocess/s1-sar-time-series",
    ):
        return True
    return False


def _get_redis():
    global _redis_client
    if _redis_client is None:
        try:
            client = redis_lib.from_url(settings.redis_url, decode_responses=True)
            client.ping()
            _redis_client = client
        except Exception:
            _redis_client = None
    return _redis_client


def _invalidate_redis() -> None:
    global _redis_client
    _redis_client = None


def _rate_limit_response(*, window: int, limit: int) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Rate limit exceeded",
            "retry_after_seconds": window,
            "limit_per_window": limit,
        },
    )


def _incr_rate_limit(r, key: str, window: int) -> int:
    count = r.incr(key)
    if count == 1:
        r.expire(key, window)
    return int(count)


@app.middleware("http")
async def audit_and_rate_limit(request: Request, call_next):
    ip = request.client.host if request.client else "unknown"
    path = request.url.path
    auth_path = is_auth_rate_limited_path(path, api_prefix=settings.api_v1_prefix)
    r = _get_redis()

    if auth_path:
        # F6: fail-closed — sin Redis no se permiten intentos de login/OTP.
        if r is None:
            return JSONResponse(
                status_code=503,
                content={"detail": "Rate limiter unavailable"},
            )
        window = max(1, int(settings.auth_rate_limit_window_seconds))
        limit = max(1, int(settings.auth_rate_limit_max_requests))
        try:
            count = _incr_rate_limit(r, f"ratelimit:auth:{ip}", window)
            if count > limit:
                return _rate_limit_response(window=window, limit=limit)
        except Exception:
            _invalidate_redis()
            return JSONResponse(
                status_code=503,
                content={"detail": "Rate limiter unavailable"},
            )
    elif r is not None:
        # API general: fail-open si Redis falla (galerías / tiles).
        window = max(1, int(settings.rate_limit_window_seconds))
        limit = max(1, int(settings.rate_limit_max_requests))
        try:
            count = _incr_rate_limit(r, f"ratelimit:{ip}", window)
            if count > limit:
                return _rate_limit_response(window=window, limit=limit)
        except Exception:
            _invalidate_redis()

    token = _bearer_token_from_request(request)
    if token:
        try:
            claims = decode_token(token)
            role = str(claims.get("role", "")).strip().lower()
            if role == "cliente" and not _is_cliente_allowed_request(request):
                return JSONResponse(status_code=403, content={"detail": "Forbidden for cliente role"})
        except Exception:
            # La autenticación formal sigue en los endpoints/dependencies.
            pass
    response = await call_next(request)
    audit_logger.info(
        "audit",
        extra={"path": request.url.path, "method": request.method, "status": response.status_code, "ip": ip},
    )
    return response


@app.get("/health")
def health():
    return {"status": "ok"}
