from abc import ABC, abstractmethod
from uuid import UUID

from src.domain.entities.notificacion import Notificacion


class NotificacionRepositoryPort(ABC):
    """Puerto de persistencia de notificaciones."""

    @abstractmethod
    async def find_by_destinatario(
        self, destinatario_id: UUID, *, solo_no_leidas: bool = False, limit: int = 50
    ) -> list[Notificacion]: ...

    @abstractmethod
    async def count_no_leidas(self, destinatario_id: UUID) -> int: ...

    @abstractmethod
    async def marcar_leida(self, id: UUID, destinatario_id: UUID) -> bool:
        """Marca una notificación como leída. Devuelve False si no existe o no es del usuario."""
        ...

    @abstractmethod
    async def marcar_todas_leidas(self, destinatario_id: UUID) -> int:
        """Marca todas las del usuario como leídas. Devuelve cuántas cambiaron."""
        ...

    @abstractmethod
    async def eliminar(self, id: UUID, destinatario_id: UUID) -> bool:
        """Elimina una notificación del usuario. Devuelve False si no existe o no es del usuario."""
        ...

    @abstractmethod
    async def save(self, notificacion: Notificacion) -> Notificacion: ...
