from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.out_.notificacion_repository_port import NotificacionRepositoryPort
from src.domain.entities.notificacion import Notificacion
from src.infrastructure.db.models.notification_model import NotificationModel


class NotificacionPostgresAdapter(NotificacionRepositoryPort):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def find_by_destinatario(
        self, destinatario_id: UUID, *, solo_no_leidas: bool = False, limit: int = 50
    ) -> list[Notificacion]:
        stmt = select(NotificationModel).where(NotificationModel.destinatario_id == destinatario_id)
        if solo_no_leidas:
            stmt = stmt.where(NotificationModel.leida.is_(False))
        stmt = stmt.order_by(NotificationModel.created_at.desc()).limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_to_entity(m) for m in rows]

    async def count_no_leidas(self, destinatario_id: UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(NotificationModel)
            .where(NotificationModel.destinatario_id == destinatario_id)
            .where(NotificationModel.leida.is_(False))
        )
        return (await self._session.execute(stmt)).scalar_one()

    async def marcar_leida(self, id: UUID, destinatario_id: UUID) -> bool:
        stmt = (
            update(NotificationModel)
            .where(NotificationModel.id == id)
            .where(NotificationModel.destinatario_id == destinatario_id)
            .values(leida=True)
        )
        result = await self._session.execute(stmt)
        return (result.rowcount or 0) > 0

    async def marcar_todas_leidas(self, destinatario_id: UUID) -> int:
        stmt = (
            update(NotificationModel)
            .where(NotificationModel.destinatario_id == destinatario_id)
            .where(NotificationModel.leida.is_(False))
            .values(leida=True)
        )
        result = await self._session.execute(stmt)
        return result.rowcount or 0

    async def eliminar(self, id: UUID, destinatario_id: UUID) -> bool:
        stmt = (
            delete(NotificationModel)
            .where(NotificationModel.id == id)
            .where(NotificationModel.destinatario_id == destinatario_id)
        )
        result = await self._session.execute(stmt)
        return (result.rowcount or 0) > 0

    async def save(self, notificacion: Notificacion) -> Notificacion:
        m = NotificationModel(
            id=notificacion.id,
            destinatario_id=notificacion.destinatario_id,
            tipo=notificacion.tipo,
            titulo=notificacion.titulo,
            mensaje=notificacion.mensaje,
            payload=notificacion.payload,
            leida=notificacion.leida,
            created_at=notificacion.created_at,
        )
        self._session.add(m)
        await self._session.flush()
        return _to_entity(m)


def _to_entity(m: NotificationModel) -> Notificacion:
    return Notificacion(
        id=m.id,
        destinatario_id=m.destinatario_id,
        tipo=m.tipo,
        titulo=m.titulo,
        mensaje=m.mensaje,
        payload=m.payload,
        leida=m.leida,
        created_at=m.created_at,
    )
