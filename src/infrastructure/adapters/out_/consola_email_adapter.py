import logging

from src.application.ports.out_.email_port import EmailPort

logger = logging.getLogger(__name__)


class ConsolaEmailAdapter(EmailPort):
    """Escribe el correo en el log en vez de enviarlo.

    Solo para desarrollo: permite probar la recuperación sin servidor de correo.
    La configuración impide usarlo fuera de development, porque dejaría los
    códigos de recuperación a la vista de cualquiera que lea los logs.
    """

    async def enviar(self, destinatario: str, asunto: str, cuerpo: str) -> None:
        logger.warning("[CORREO NO ENVIADO — desarrollo] Para: %s | %s\n%s", destinatario, asunto, cuerpo)
