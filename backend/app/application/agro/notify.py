"""Notificaciones vía MailPort (H3)."""

from __future__ import annotations

from app.domain.shared.ports import MailPort
from app.infrastructure.composition import default_mail


class NotifyStudyOrderOrProject:
    """Envía el resumen operativo (ORDER_NOTIFY_EMAIL) vía ``MailPort``."""

    def __init__(self, mail: MailPort | None = None) -> None:
        self._mail = mail or default_mail()

    def execute(self, *, order_id: int, user_email: str, lines: list[str]) -> None:
        self._mail.send_study_order_notification(
            order_id=order_id, user_email=user_email, lines=lines
        )
