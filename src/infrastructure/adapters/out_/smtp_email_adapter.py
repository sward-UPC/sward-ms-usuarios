import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from src.application.ports.out_.email_port import EmailPort, EnvioCorreoError


class SmtpEmailAdapter(EmailPort):
    """Envía correos por SMTP con la biblioteca estándar.

    Sirve igual para un servidor de pruebas local (Mailpit), una cuenta de Gmail
    con contraseña de aplicación o Amazon SES por SMTP: solo cambia la
    configuración. `smtplib` es síncrona, así que el envío corre en un hilo para
    no bloquear el bucle de eventos.
    """

    def __init__(
        self,
        host: str,
        port: int,
        usuario: str,
        contrasena: str,
        remitente: str,
        starttls: bool,
        usar_ssl: bool,
        timeout: int = 15,
    ):
        self._host = host
        self._port = port
        self._usuario = usuario
        self._contrasena = contrasena
        self._remitente = remitente
        self._starttls = starttls
        self._usar_ssl = usar_ssl
        self._timeout = timeout

    async def enviar(self, destinatario: str, asunto: str, cuerpo: str) -> None:
        mensaje = EmailMessage()
        mensaje["From"] = self._remitente
        mensaje["To"] = destinatario
        mensaje["Subject"] = asunto
        mensaje["Date"] = formatdate(localtime=True)
        mensaje["Message-ID"] = make_msgid(domain="sward")
        mensaje.set_content(cuerpo)
        try:
            await asyncio.to_thread(self._enviar, mensaje)
        except (smtplib.SMTPException, OSError) as e:
            raise EnvioCorreoError(str(e)) from e

    def _enviar(self, mensaje: EmailMessage) -> None:
        contexto = ssl.create_default_context()
        if self._usar_ssl:
            servidor = smtplib.SMTP_SSL(self._host, self._port, timeout=self._timeout, context=contexto)
        else:
            servidor = smtplib.SMTP(self._host, self._port, timeout=self._timeout)
        with servidor:
            if self._starttls and not self._usar_ssl:
                servidor.starttls(context=contexto)
            if self._usuario:
                servidor.login(self._usuario, self._contrasena)
            servidor.send_message(mensaje)
