from src.application.ports.out_.email_port import EmailPort, EnvioCorreoError


class SinCorreoAdapter(EmailPort):
    """Correo sin configurar fuera de desarrollo.

    Existe para que la falta de SMTP no tumbe el servicio: el login y el registro
    siguen funcionando, y solo la recuperación de contraseña responde que no está
    disponible.
    """

    disponible = False

    async def enviar(self, destinatario: str, asunto: str, cuerpo: str) -> None:
        raise EnvioCorreoError("El correo saliente no está configurado (EMAIL_BACKEND).")
