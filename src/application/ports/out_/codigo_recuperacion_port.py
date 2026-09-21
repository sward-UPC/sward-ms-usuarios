from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class CodigoGuardado:
    """Código de recuperación vigente de un usuario.

    Nunca se guarda el código en claro: solo su huella, de modo que quien lea el
    almacenamiento no pueda usarlo.
    """

    huella: str
    intentos_fallidos: int


class CodigoRecuperacionPort(ABC):
    """Puerto de salida para los códigos de recuperación de contraseña.

    Todos los datos son efímeros: vencen solos, y el núcleo no necesita saber
    si viven en Redis o en otro almacenamiento con expiración.
    """

    @abstractmethod
    async def guardar(self, usuario_id: UUID, huella: str, ttl_segundos: int) -> None:
        """Guarda un código nuevo, reemplazando el anterior y sus intentos."""

    @abstractmethod
    async def obtener(self, usuario_id: UUID) -> CodigoGuardado | None: ...

    @abstractmethod
    async def registrar_intento_fallido(self, usuario_id: UUID) -> int:
        """Suma un intento fallido y devuelve el total."""

    @abstractmethod
    async def eliminar(self, usuario_id: UUID) -> None: ...

    @abstractmethod
    async def en_espera(self, usuario_id: UUID) -> bool:
        """True si se envió un código hace muy poco y aún no toca reenviar."""

    @abstractmethod
    async def iniciar_espera(self, usuario_id: UUID, segundos: int) -> None: ...

    @abstractmethod
    async def contar_envio(self, usuario_id: UUID, ventana_segundos: int) -> int:
        """Suma un envío a la ventana actual y devuelve cuántos van."""
