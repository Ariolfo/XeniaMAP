"""Estados y transiciones de Project (Agro)."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.errors import InvalidStatusError

PROJECT_STATUS_PENDIENTE = "pendiente"
PROJECT_STATUS_EN_PROCESO = "en proceso"
PROJECT_STATUS_PROCESADO = "procesado"
PROJECT_STATUS_PUBLICADO = "publicado"

PROJECT_STATUSES: frozenset[str] = frozenset(
    {
        PROJECT_STATUS_PENDIENTE,
        PROJECT_STATUS_EN_PROCESO,
        PROJECT_STATUS_PROCESADO,
        PROJECT_STATUS_PUBLICADO,
    }
)

# Admin puede fijar cualquier estado canónico desde cualquier otro (comportamiento actual).
PROJECT_TRANSITIONS: dict[str, frozenset[str]] = {
    s: frozenset(PROJECT_STATUSES - {s}) | frozenset({s}) for s in PROJECT_STATUSES
}


def normalize_project_status(raw: str) -> str:
    s = str(raw or "").strip().lower().replace("_", " ")
    if s.replace(" ", "") == "enproceso":
        s = PROJECT_STATUS_EN_PROCESO
    if s not in PROJECT_STATUSES:
        raise InvalidStatusError("Estado de proyecto inválido")
    return s


def assert_project_transition(current: str | None, new: str) -> str:
    """Valida destino (y origen si es conocido). Devuelve status canónico destino."""
    target = normalize_project_status(new)
    if current is None or str(current).strip() == "":
        return target
    try:
        src = normalize_project_status(current)
    except InvalidStatusError:
        # Legado sucio (p.ej. "enproceso" sin espacio ya normalizado arriba; otros): permitir target válido.
        return target
    allowed = PROJECT_TRANSITIONS.get(src, PROJECT_STATUSES)
    if target not in allowed:
        raise InvalidStatusError(f"Transición de proyecto no permitida: {src} → {target}")
    return target


@dataclass(frozen=True)
class ProjectStatusEffects:
    status: str
    set_processing_started: bool = False
    set_processing_completed: bool = False
    set_published: bool = False
    notify_owner: bool = False


def plan_project_status_change(new_status: str) -> ProjectStatusEffects:
    s = normalize_project_status(new_status)
    if s == PROJECT_STATUS_EN_PROCESO:
        return ProjectStatusEffects(status=s, set_processing_started=True)
    if s == PROJECT_STATUS_PROCESADO:
        return ProjectStatusEffects(status=s, set_processing_completed=True)
    if s == PROJECT_STATUS_PUBLICADO:
        return ProjectStatusEffects(
            status=s,
            set_published=True,
            notify_owner=True,
        )
    return ProjectStatusEffects(status=s)
