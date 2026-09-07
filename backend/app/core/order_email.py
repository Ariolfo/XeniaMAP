"""Facade: notificaciones de solicitud de estudio (SMTP vía mail.py)."""

from app.core.mail import send_study_order_notification

__all__ = ["send_study_order_notification"]
