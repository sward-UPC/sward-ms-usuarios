from abc import ABC, abstractmethod


class EnvioCorreoError(Exception):
    """El correo no pudo entregarse al servidor de salida."""


class EmailPort(ABC):
    """Puerto de salida para enviar correos transaccionales."""

    # False cuando el servicio corre sin correo configurado. Los casos de uso que
    # dependen del correo lo consultan antes de empezar, en vez de fallar a mitad.
    disponible: bool = True

    @abstractmethod
    async def enviar(self, destinatario: str, asunto: str, cuerpo: str) -> None:
        """Envía un correo de texto plano. Lanza EnvioCorreoError si falla."""
