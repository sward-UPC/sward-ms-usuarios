from uuid import UUID

from src.application.ports.out_.notificacion_repository_port import NotificacionRepositoryPort
from src.domain.entities.notificacion import Notificacion


class GestionarNotificacionesUseCase:
    """Operaciones del usuario sobre SUS notificaciones (siempre acotadas al
    destinatario autenticado, para que nadie lea/edite las de otro)."""

    def __init__(self, repo: NotificacionRepositoryPort):
        self._repo = repo

    async def listar(
        self, destinatario_id: UUID, *, solo_no_leidas: bool = False, limit: int = 50
    ) -> tuple[list[Notificacion], int]:
        """Devuelve las notificaciones del usuario y el conteo de no leídas."""
        items = await self._repo.find_by_destinatario(destinatario_id, solo_no_leidas=solo_no_leidas, limit=limit)
        no_leidas = await self._repo.count_no_leidas(destinatario_id)
        return items, no_leidas

    async def marcar_leida(self, id: UUID, destinatario_id: UUID) -> bool:
        return await self._repo.marcar_leida(id, destinatario_id)

    async def marcar_todas_leidas(self, destinatario_id: UUID) -> int:
        return await self._repo.marcar_todas_leidas(destinatario_id)

    async def eliminar(self, id: UUID, destinatario_id: UUID) -> bool:
        return await self._repo.eliminar(id, destinatario_id)
