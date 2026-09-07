import logging
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, issue_tokens, require_admin
from app.core.config import settings
from app.core.mail import send_otp_email, smtp_configured
from app.core.otp_store import peek_otp_for_dev, set_otp, verify_and_consume_otp
from app.core.security import decode_token, hash_password, verify_password
from app.db.session import get_db
from app.models.models import Tenant, User, UserAuditLog
from app.schemas.schemas import (
    AdminCreateUserRequest,
    AdminCreateUserResponse,
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


@router.post("/auth/register", response_model=TokenResponse)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    tenant = db.query(Tenant).filter(Tenant.name == payload.tenant_name).first()
    if tenant is None:
        tenant = Tenant(name=payload.tenant_name)
        db.add(tenant)
        db.flush()
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already exists")
    role = "admin" if settings.is_bootstrap_admin(payload.email) else "cliente"
    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        tenant_id=tenant.id,
        role=role,
        full_name="",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return issue_tokens(user)


@router.post("/auth/refresh", response_model=TokenResponse)
def refresh_session(payload: RefreshRequest, db: Session = Depends(get_db)):
    """Emite nuevos access/refresh tokens a partir de un refresh token válido."""
    claims = decode_token(payload.refresh_token)
    if claims.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")
    user = db.query(User).filter(User.id == int(claims["sub"])).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid user")
    if not getattr(user, "is_active", True):
        _user_inactive_response()
    return issue_tokens(user)


@router.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not getattr(user, "is_active", True):
        _user_inactive_response()
    return issue_tokens(user)


@router.post("/auth/check-email", response_model=CheckEmailResponse)
def check_email(payload: CheckEmailRequest, db: Session = Depends(get_db)):
    email = str(payload.email).strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return {"exists": False, "role": None, "is_admin": False}
    role = str(getattr(user, "role", "") or "").strip().lower() or None
    return {"exists": True, "role": role, "is_admin": role == "admin"}


@router.post("/auth/request-otp", response_model=RequestOtpResponse)
def request_registration_otp(payload: RequestOtpRequest, db: Session = Depends(get_db)):
    email = str(payload.email).strip().lower()
    existing = db.query(User).filter(User.email == email).first()
    if existing and str(existing.role).strip().lower() == "admin":
        raise HTTPException(
            status_code=400,
            detail="Este correo es administrador. Debe iniciar sesión con contraseña.",
        )

    simulate = bool(settings.otp_simulate)
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
        logger.warning(
            "OTP_SIMULATE activo — código emitido para dominio=%s",
            email.split("@")[-1],
        )
        dbg = peek_otp_for_dev(email) or code
        return {
            "message": (
                "Modo desarrollo (OTP_SIMULATE): use el código mostrado. "
                "No usar en producción."
            ),
            "debug_otp": dbg,
        }

    sent = send_otp_email(email, code)
    if not sent:
        raise HTTPException(
            status_code=503,
            detail="No se pudo enviar el correo de verificación. Intente más tarde.",
        )
    return {
        "message": "Se envió un código de verificación a su correo. Revise la bandeja de entrada.",
        "debug_otp": None,
    }


@router.post("/auth/verify-otp", response_model=TokenResponse)
def verify_otp_and_register(payload: VerifyOtpRegisterRequest, db: Session = Depends(get_db)):
    email = str(payload.email).strip().lower()
    if not verify_and_consume_otp(email, payload.code):
        raise HTTPException(status_code=400, detail="Código incorrecto o expirado.")
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        if str(existing.role).strip().lower() == "admin":
            raise HTTPException(status_code=400, detail="Usuario admin requiere contraseña.")
        if not getattr(existing, "is_active", True):
            _user_inactive_response()
        return issue_tokens(existing)
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
    return issue_tokens(user, {"temporary_password": auto_pw})


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


@router.get("/auth/users/audit-log", response_model=list[UserAuditLogEntry])
def list_user_audit_log(db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    rows = (
        db.query(UserAuditLog)
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
def list_users(db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    users = db.query(User).order_by(User.id.asc()).all()
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
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
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
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
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
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
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
