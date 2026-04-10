"""
Email Sender — envía reportes por email via SMTP.

Responsabilidades:
- Conectarse al servidor SMTP con credenciales del entorno
- Construir un email con cuerpo HTML y adjunto PDF
- Retornar (bool, mensaje) indicando éxito o descripción del error

Funciones principales:
    send_report(to_email, subject, html_body, pdf_bytes)  -> tuple[bool, str]
"""

import os
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from dotenv import load_dotenv

load_dotenv()

_PLACEHOLDER_PATTERNS = ("your-email", "your-app-password")


def _is_placeholder(value: str) -> bool:
    return any(p in value.lower() for p in _PLACEHOLDER_PATTERNS)


def send_report(
    to_email: str,
    subject: str,
    html_body: str,
    pdf_bytes: bytes,
) -> tuple[bool, str]:
    """
    Envía un reporte PDF por email via SMTP con TLS.

    Lee SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS del environment.
    Retorna (True, "Email enviado exitosamente") o (False, "descripción del error").
    """
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")

    # Validate credentials
    if not all([smtp_host, smtp_user, smtp_pass]):
        return (
            False,
            "Credenciales SMTP no configuradas. Configura las variables SMTP_* en el archivo .env",
        )
    if _is_placeholder(smtp_user) or _is_placeholder(smtp_pass):
        return (
            False,
            "Credenciales SMTP no configuradas. Configura las variables SMTP_* en el archivo .env",
        )

    try:
        msg = MIMEMultipart("mixed")
        msg["From"] = smtp_user
        msg["To"] = to_email
        msg["Subject"] = subject

        # HTML body
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        # PDF attachment
        pdf_part = MIMEApplication(pdf_bytes, _subtype="pdf")
        pdf_part.add_header(
            "Content-Disposition",
            "attachment",
            filename="rappi_insights_report.pdf",
        )
        msg.attach(pdf_part)

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, to_email, msg.as_string())

        return (True, "Email enviado exitosamente")

    except Exception as exc:
        return (False, f"Error al enviar email: {str(exc)}")
