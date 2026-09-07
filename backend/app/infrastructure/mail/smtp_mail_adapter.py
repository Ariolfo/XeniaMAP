"""Adapter: MailPort → SMTP / helpers existentes."""

from __future__ import annotations

from app.core import mail as _mail


class SmtpMailAdapter:
    def send_email(self, *, to: str, subject: str, body: str) -> bool:
        return _mail.send_email(to=to, subject=subject, body=body)

    def send_study_order_notification(
        self, *, order_id: int, user_email: str, lines: list[str]
    ) -> None:
        _mail.send_study_order_notification(
            order_id=order_id, user_email=user_email, lines=lines
        )
