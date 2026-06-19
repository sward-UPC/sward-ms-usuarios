from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.rol import Permiso, Rol, TipoRol
from src.domain.ports.out_.rol_repository_port import RolRepositoryPort
from src.infrastructure.db.models.role_model import RoleModel, user_roles


class RolPostgresAdapter(RolRepositoryPort):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def find_by_nombre(self, nombre: TipoRol) -> Rol | None:
        r = await self._session.execute(select(RoleModel).where(RoleModel.nombre == str(nombre)))
        m = r.scalar_one_or_none()
        return _to_entity(m) if m else None

    async def find_by_usuario_id(self, usuario_id: UUID) -> list[Rol]:
        r = await self._session.execute(
            select(RoleModel)
            .join(user_roles, RoleModel.id == user_roles.c.role_id)
            .where(user_roles.c.user_id == usuario_id)
        )
        return [_to_entity(m) for m in r.scalars().all()]

    async def assign_rol(self, usuario_id: UUID, rol_id: UUID) -> None:
        await self._session.execute(
            insert(user_roles).values(user_id=usuario_id, role_id=rol_id).on_conflict_do_nothing()
        )

    async def revoke_rol(self, usuario_id: UUID, rol_id: UUID) -> None:
        await self._session.execute(
            delete(user_roles).where(user_roles.c.user_id == usuario_id, user_roles.c.role_id == rol_id)
        )

    async def find_all(self) -> list[Rol]:
        r = await self._session.execute(select(RoleModel))
        return [_to_entity(m) for m in r.scalars().all()]


def _to_entity(m: RoleModel) -> Rol:
    return Rol(
        id=m.id,
        nombre=TipoRol(m.nombre),
        descripcion=m.descripcion,
        permisos=[Permiso(id=p.id, codigo=p.codigo) for p in m.permisos],
    )
