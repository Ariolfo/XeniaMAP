import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger(__name__)


def send_study_order_notification(*, order_id: int, user_email: str, lines: list[str]) -> None:
    to_addr = (settings.order_notify_email or "").strip() or "ariolfo.camacho@saber.uis.edu.co"
    subject = f"[XeniaMAP] Nueva solicitud AgroGeoFísico #{order_id}"
    body = "\n".join(lines)
    logger.info("Solicitud estudio #%s — resumen (notificación)\n%s", order_id, body)
    host = (settings.smtp_host or "").strip()
    if not host:
        logger.warning("SMTP_HOST vacío: no se envía correo (solo log). Configure SMTP_* para envío real.")
        return
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
        logger.info("Correo de solicitud #%s enviado a %s", order_id, to_addr)
    except Exception as e:
        logger.exception("Fallo al enviar correo de solicitud #%s: %s", order_id, e)
