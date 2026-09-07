"""Estados y transiciones de FireOrder."""

from __future__ import annotations

from app.domain.errors import InvalidStatusError

FIRE_STATUS_PENDIENTE = "pendiente"
FIRE_STATUS_EN_DESCARGA = "en_descarga"
FIRE_STATUS_DESCARGADO = "descargado"
FIRE_STATUS_PROCESANDO = "procesando"
FIRE_STATUS_PROCESADO = "procesado"
FIRE_STATUS_VALIDANDO = "validando"
FIRE_STATUS_VALIDADO = "validado"
FIRE_STATUS_ERROR = "error"

FIRE_ORDER_STATUSES: frozenset[str] = frozenset(
    {
        FIRE_STATUS_PENDIENTE,
        FIRE_STATUS_EN_DESCARGA,
        FIRE_STATUS_DESCARGADO,
        FIRE_STATUS_PROCESANDO,
        FIRE_STATUS_PROCESADO,
        FIRE_STATUS_VALIDANDO,
        FIRE_STATUS_VALIDADO,
        FIRE_STATUS_ERROR,
    }
)

# Admin patch: cualquier estado canónico ↔ cualquier otro.
FIRE_ADMIN_TRANSITIONS: dict[str, frozenset[str]] = {
    s: frozenset(FIRE_ORDER_STATUSES) for s in FIRE_ORDER_STATUSES
}

# Pipeline (enqueue / worker): orígenes razonables por destino de paso activo.
FIRE_PIPELINE_ENTRY: dict[str, frozenset[str]] = {
    FIRE_STATUS_EN_DESCARGA: frozenset(
        {
            FIRE_STATUS_PENDIENTE,
            FIRE_STATUS_DESCARGADO,
            FIRE_STATUS_ERROR,
            FIRE_STATUS_EN_DESCARGA,
            FIRE_STATUS_PROCESADO,
            FIRE_STATUS_VALIDADO,
        }
    ),
    FIRE_STATUS_PROCESANDO: frozenset(
        {
            FIRE_STATUS_DESCARGADO,
            FIRE_STATUS_PROCESADO,
            FIRE_STATUS_ERROR,
            FIRE_STATUS_PROCESANDO,
            FIRE_STATUS_PENDIENTE,
            FIRE_STATUS_EN_DESCARGA,
        }
    ),
    FIRE_STATUS_VALIDANDO: frozenset(
        {
            FIRE_STATUS_PROCESADO,
            FIRE_STATUS_VALIDADO,
            FIRE_STATUS_ERROR,
            FIRE_STATUS_VALIDANDO,
        }
    ),
}


def normalize_fire_order_status(raw: str) -> str:
    s = str(raw or "").strip().lower()
    if s not in FIRE_ORDER_STATUSES:
        raise InvalidStatusError(
            f"Estado debe ser uno de: {', '.join(sorted(FIRE_ORDER_STATUSES))}"
        )
    return s


def assert_fire_order_transition(
    current: str | None,
    new: str,
    *,
    mode: str = "admin",
) -> str:
    """
    mode=admin: cualquier ↔ cualquier (patch HTTP).
    mode=pipeline: valida entrada a pasos activos (en_descarga/procesando/validando).
    """
    target = normalize_fire_order_status(new)
    if mode == "admin":
        if current is None or str(current).strip() == "":
            return target
        try:
            src = normalize_fire_order_status(current)
        except InvalidStatusError:
            return target
        if target not in FIRE_ADMIN_TRANSITIONS.get(src, FIRE_ORDER_STATUSES):
            raise InvalidStatusError(f"Transición Fire no permitida: {src} → {target}")
        return target

    # pipeline
    allowed_from = FIRE_PIPELINE_ENTRY.get(target)
    if allowed_from is None:
        # Terminales de worker (descargado/procesado/validado/error) no se filtran aquí.
        return target
    if current is None or str(current).strip() == "":
        return target
    try:
        src = normalize_fire_order_status(current)
    except InvalidStatusError:
        return target
    if src not in allowed_from:
        raise InvalidStatusError(
            f"Pipeline Fire: no se puede pasar de {src} a {target}"
        )
    return target
