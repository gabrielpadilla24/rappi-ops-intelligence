"""
Email Sender — envía reportes por email via SMTP.

Responsabilidades:
- Conectarse al servidor SMTP con credenciales del entorno
- Construir un email con cuerpo HTML y adjunto PDF
- Retornar True si el envío fue exitoso, False en caso contrario

Funciones principales:
    send_report(to_email, subject, html_body, pdf_bytes)  -> bool
"""


def send_report(to_email: str, subject: str, html_body: str, pdf_bytes: bytes) -> bool:
    pass
