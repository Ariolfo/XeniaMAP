"""Envío de correo genérico (SMTP) + helpers OTP / notificaciones."""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger(__name__)


def smtp_configured() -> bool:
    return bool((settings.smtp_host or "").strip())


def send_email(*, to: str, subject: str, body: str) -> bool:
    """Envía correo. Sin SMTP_HOST solo registra y retorna False."""
    to_addr = (to or "").strip()
    if not to_addr:
        logger.warning("send_email: destinatario vacío")
        return False
    host = (settings.smtp_host or "").strip()
    if not host:
        logger.warning("SMTP_HOST vacío: no se envía correo (solo log). Configure SMTP_* para envío real.")
        logger.info("Correo no enviado → %s | %s\n%s", to_addr, subject, body)
        return False
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = (settings.smtp_from or settings.smtp_user or "noreply@localhost").strip()
    msg["To"] = to_addr
    msg.set_content(body)
    try:
        with smtplib.SMTP(host, int(settings.smtp_port)) as s:
            if settings.smtp_use_tls:
                s.starttls()
            user = (settings.smtp_user or "").strip()
            if user:
                s.login(user, settings.smtp_password or "")
            s.send_message(msg)
        logger.info("Correo enviado a %s (%s)", to_addr, subject)
        return True
    except Exception as e:
        logger.exception("Fallo al enviar correo a %s: %s", to_addr, e)
        return False


def send_otp_email(to: str, code: str) -> bool:
    return send_email(
        to=to,
        subject="[XeniaMAP] Código de verificación",
        body=(
            f"Su código de verificación es: {code}\n\n"
            "Caduca en unos minutos. Si no solicitó este código, ignore este mensaje.\n"
        ),
    )


def send_study_order_notification(*, order_id: int, user_email: str, lines: list[str]) -> None:
    to_addr = (settings.order_notify_email or "").strip()
    subject = f"[XeniaMAP] Nueva solicitud AgroGeoFísico #{order_id}"
    body = "\n".join(lines)
    logger.info("Solicitud estudio #%s — resumen (notificación)\n%s", order_id, body)
    if not to_addr:
        logger.warning("ORDER_NOTIFY_EMAIL vacío: no se envía notificación de solicitud #%s", order_id)
        return
    send_email(to=to_addr, subject=subject, body=body)
