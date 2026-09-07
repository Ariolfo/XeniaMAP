import logging
import os
import secrets
from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, issue_tokens, require_admin
from app.core.auth_cookies import REFRESH_COOKIE, clear_auth_cookies, set_auth_cookies
from app.core.config import settings
from app.core.mail import send_otp_email, smtp_configured
from app.core.otp_store import set_otp, verify_and_consume_otp
from app.core.security import decode_token, hash_password, verify_password
from app.core.password_policy import PasswordRejected, assert_new_password
from app.db.session import get_db
from app.models.models import Tenant, User, UserAuditLog
from app.schemas.schemas import (
    AdminCreateUserRequest,
    AdminCreateUserResponse,
    ChangePasswordRequest,
    CheckEmailRequest,
    CheckEmailResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    RequestOtpRequest,
    RequestOtpResponse,
    TokenResponse,
    UpdateUserActiveRequest,
    UpdateUserRoleRequest,
    UserAuditLogEntry,
    UserMeResponse,
    UserSummaryResponse,
    VerifyOtpRegisterRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Respuesta uniforme de request-otp (F8: no filtrar admin vs resto).
_OTP_REQUEST_OK_MESSAGE = (
    "Si el correo admite verificación, recibirá un código en breve. "
    "Revise la bandeja de entrada."
)


def _append_audit(
    db: Session,
    *,
    actor_id: int,
    action: str,
    target_user_id: int | None,
    details: dict | None = None,
) -> None:
    row = UserAuditLog(
        actor_user_id=actor_id,
        action=action,
        target_user_id=target_user_id,
        details=details or {},
    )
    db.add(row)


def _user_inactive_response():
    raise HTTPException(status_code=401, detail="Cuenta inactiva")


def _issue_and_set_cookies(response: Response, user: User, extra: dict | None = None) -> dict:
    tokens = issue_tokens(user, extra)
    set_auth_cookies(
        response,
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
    )
    return tokens


@router.post("/auth/register", response_model=TokenResponse, deprecated=True)
def register(payload: RegisterRequest):
    """Deshabilitado (F1): el alta pública debe pasar por OTP.

    Usar ``POST /auth/request-otp`` y luego ``POST /auth/verify-otp``.
    La creación de usuarios por admin sigue en ``POST /auth/users``.
    """
    raise HTTPException(
        status_code=410,
        detail=(
            "Registro directo deshabilitado. "
            "Use /auth/request-otp y /auth/verify-otp para verificar el correo."
        ),
    )


@router.post("/auth/logout")
def logout(response: Response):
    """Limpia cookies HttpOnly de sesión (F5)."""
    clear_auth_cookies(response)
    return {"ok": True}


@router.post("/auth/refresh", response_model=TokenResponse)
def refresh_session(
    request: Request,
    response: Response,
    payload: RefreshRequest = Body(default_factory=RefreshRequest),
    db: Session = Depends(get_db),
):
    """Emite nuevos access/refresh a partir del body o de la cookie HttpOnly."""
    raw = payload.refresh_token or request.cookies.get(REFRESH_COOKIE)
    if not raw:
        raise HTTPException(status_code=401, detail="Missing refresh token")
    claims = decode_token(raw)
    if claims.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")
    user = db.query(User).filter(User.id == int(claims["sub"])).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid user")
    if not getattr(user, "is_active", True):
        _user_inactive_response()
    return _issue_and_set_cookies(response, user)


@router.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not getattr(user, "is_active", True):
        _user_inactive_response()
    return _issue_and_set_cookies(response, user)


@router.post("/auth/change-password")
def change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """F9: cambia la contraseña de la sesión actual (política local + HIBP)."""
    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    try:
        new_pw = assert_new_password(payload.new_password, check_hibp=True)
    except PasswordRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if verify_password(new_pw, user.hashed_password):
        raise HTTPException(
            status_code=400,
            detail="New password must be different from the current password",
        )
    user.hashed_password = hash_password(new_pw)
    _append_audit(
        db,
        actor_id=user.id,
        action="password_changed",
        target_user_id=user.id,
        details={},
    )
    db.commit()
    return {"ok": True}


@router.post("/auth/check-email", response_model=CheckEmailResponse)
def check_email(payload: CheckEmailRequest, db: Session = Depends(get_db)):
    """F8: no enumera cuentas ni roles. Solo indica el siguiente paso del UI."""
    email = str(payload.email).strip().lower()
    user = db.query(User).filter(User.email == email).first()
    role = str(getattr(user, "role", "") or "").strip().lower() if user else ""
    if user and role == "admin":
        return {"next": "password"}
    return {"next": "otp"}


@router.post("/auth/request-otp", response_model=RequestOtpResponse)
def request_registration_otp(payload: RequestOtpRequest, db: Session = Depends(get_db)):
    email = str(payload.email).strip().lower()
    existing = db.query(User).filter(User.email == email).first()
    if existing and str(existing.role).strip().lower() == "admin":
        # F8: misma forma/mensaje que un envío OK (sin filtrar que es admin).
        logger.info("OTP request ignored for admin account (domain=%s)", email.split("@")[-1])
        return {"message": _OTP_REQUEST_OK_MESSAGE, "debug_otp": None}

    simulate = bool(settings.otp_simulate)
    if simulate and settings.is_production():
        raise HTTPException(
            status_code=503,
            detail="OTP_SIMULATE no está permitido en producción. Configure SMTP_*.",
        )
    if not simulate and not smtp_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                "Verificación por correo no configurada. "
                "Defina SMTP_* o OTP_SIMULATE=1 solo en desarrollo."
            ),
        )

    code = f"{secrets.randbelow(10**8):08d}"
    set_otp(email, code, ttl_sec=int(settings.otp_ttl_sec))

    if simulate:
        # F2: nunca devolver el OTP en el body JSON (ni con OTP_SIMULATE).
        logger.warning(
            "OTP_SIMULATE activo — código emitido para dominio=%s (no se incluye en la respuesta)",
            email.split("@")[-1],
        )
        if os.environ.get("LOG_OTP", "").strip().lower() in {"1", "true", "yes"}:
            logger.warning("LOG_OTP=1 — OTP de desarrollo para %s: %s", email, code)
        return {
            "message": (
                "Modo desarrollo (OTP_SIMULATE): código almacenado en el servidor. "
                "No se expone en la API. Con LOG_OTP=1 aparece solo en logs del backend."
            ),
            "debug_otp": None,
        }

    sent = send_otp_email(email, code)
    if not sent:
        raise HTTPException(
            status_code=503,
            detail="No se pudo enviar el correo de verificación. Intente más tarde.",
        )
    return {
        "message": _OTP_REQUEST_OK_MESSAGE,
        "debug_otp": None,
    }


@router.post("/auth/verify-otp", response_model=TokenResponse)
def verify_otp_and_register(
    payload: VerifyOtpRegisterRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    email = str(payload.email).strip().lower()
    if not verify_and_consume_otp(email, payload.code):
        raise HTTPException(status_code=400, detail="Código incorrecto o expirado.")
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        if str(existing.role).strip().lower() == "admin":
            # F8: no revelar que la cuenta es admin.
            raise HTTPException(status_code=400, detail="Código incorrecto o expirado.")
        if not getattr(existing, "is_active", True):
            _user_inactive_response()
        return _issue_and_set_cookies(response, existing)
    tenant_name = email.split("@")[-1] if "@" in email else "default"
    tenant = db.query(Tenant).filter(Tenant.name == tenant_name).first()
    if tenant is None:
        tenant = Tenant(name=tenant_name)
        db.add(tenant)
        db.flush()
    auto_pw = secrets.token_urlsafe(24)
    role = "admin" if settings.is_bootstrap_admin(email) else "cliente"
    user = User(
        email=email,
        hashed_password=hash_password(auto_pw),
        tenant_id=tenant.id,
        role=role,
        full_name="",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _issue_and_set_cookies(response, user, {"temporary_password": auto_pw})


@router.get("/auth/me", response_model=UserMeResponse)
def auth_me(user: User = Depends(get_current_user)):
    return {"id": user.id, "email": user.email, "tenant_id": user.tenant_id, "role": user.role}


def _user_summary(u: User) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "full_name": getattr(u, "full_name", None) or "",
        "tenant_id": u.tenant_id,
        "role": u.role,
        "is_active": bool(getattr(u, "is_active", True)),
        "created_at": u.created_at.isoformat() if getattr(u, "created_at", None) else None,
    }


def _tenant_user_or_404(db: Session, admin: User, user_id: int) -> User:
    """F3: admins solo gestionan usuarios de su mismo tenant."""
    user = (
        db.query(User)
        .filter(User.id == user_id, User.tenant_id == admin.tenant_id)
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/auth/users/audit-log", response_model=list[UserAuditLogEntry])
def list_user_audit_log(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    tenant_user_ids = db.query(User.id).filter(User.tenant_id == admin.tenant_id)
    rows = (
        db.query(UserAuditLog)
        .filter(
            (UserAuditLog.actor_user_id.in_(tenant_user_ids))
            | (UserAuditLog.target_user_id.in_(tenant_user_ids))
        )
        .order_by(UserAuditLog.created_at.desc())
        .limit(500)
        .all()
    )
    out = []
    for r in rows:
        out.append(
            {
                "id": r.id,
                "created_at": r.created_at.isoformat() if r.created_at else "",
                "actor_user_id": r.actor_user_id,
                "target_user_id": r.target_user_id,
                "action": r.action,
                "details": r.details or {},
            }
        )
    return out


@router.get("/auth/users", response_model=list[UserSummaryResponse])
def list_users(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    users = (
        db.query(User)
        .filter(User.tenant_id == admin.tenant_id)
        .order_by(User.id.asc())
        .all()
    )
    return [_user_summary(u) for u in users]


@router.post("/auth/users", response_model=AdminCreateUserResponse)
def admin_create_user(
    payload: AdminCreateUserRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    email = str(payload.email).strip().lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="El correo ya está registrado")
    temp_password = secrets.token_urlsafe(14)
    user = User(
        email=email,
        hashed_password=hash_password(temp_password),
        full_name=payload.full_name.strip(),
        role=payload.role,
        tenant_id=admin.tenant_id,
        is_active=True,
    )
    db.add(user)
    db.flush()
    _append_audit(
        db,
        actor_id=admin.id,
        action="user_created",
        target_user_id=user.id,
        details={
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
    )
    db.commit()
    db.refresh(user)
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "created_at": user.created_at.isoformat() if user.created_at else "",
        "temporary_password": temp_password,
    }


@router.patch("/auth/users/{user_id}/role")
def update_user_role(
    user_id: int,
    payload: UpdateUserRoleRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = _tenant_user_or_404(db, admin, user_id)
    old_role = user.role
    if old_role != payload.role:
        user.role = payload.role
        db.add(user)
        _append_audit(
            db,
            actor_id=admin.id,
            action="role_changed",
            target_user_id=user.id,
            details={"email": user.email, "from": old_role, "to": payload.role},
        )
        db.commit()
        db.refresh(user)
    return {"id": user.id, "email": user.email, "role": user.role}


@router.patch("/auth/users/{user_id}/active")
def update_user_active(
    user_id: int,
    payload: UpdateUserActiveRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = _tenant_user_or_404(db, admin, user_id)
    if user_id == admin.id and not payload.is_active:
        raise HTTPException(status_code=400, detail="No puede inactivar su propia cuenta")
    prev = bool(getattr(user, "is_active", True))
    if prev == payload.is_active:
        return {"id": user.id, "email": user.email, "is_active": user.is_active}
    user.is_active = payload.is_active
    db.add(user)
    action = "user_reactivated" if payload.is_active else "user_deactivated"
    _append_audit(
        db,
        actor_id=admin.id,
        action=action,
        target_user_id=user.id,
        details={
            "email": user.email,
            "full_name": getattr(user, "full_name", "") or "",
            "is_active": payload.is_active,
        },
    )
    db.commit()
    db.refresh(user)
    return {"id": user.id, "email": user.email, "is_active": user.is_active}


@router.delete("/auth/users/{user_id}")
def admin_delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="No puede eliminar su propia cuenta")
    user = _tenant_user_or_404(db, admin, user_id)
    snap = {
        "email": user.email,
        "full_name": getattr(user, "full_name", "") or "",
        "role": user.role,
        "deleted_at": datetime.utcnow().isoformat(),
    }
    _append_audit(
        db,
        actor_id=admin.id,
        action="user_deleted",
        target_user_id=user.id,
        details=snap,
    )
    db.delete(user)
    db.commit()
    return {"ok": True, "id": user_id}
