from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.usuario import Usuario
from src.domain.ports.out_.usuario_repository_port import UsuarioRepositoryPort
from src.domain.value_objects.estado_usuario import EstadoUsuario
from src.infrastructure.db.models.user_model import UserModel


class UsuarioPostgresAdapter(UsuarioRepositoryPort):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def find_by_correo(self, correo: str) -> Usuario | None:
        r = await self._session.execute(select(UserModel).where(UserModel.correo_institucional == correo.lower()))
        m = r.scalar_one_or_none()
        return _to_entity(m) if m else None

    async def find_by_id(self, id: UUID) -> Usuario | None:
        r = await self._session.execute(select(UserModel).where(UserModel.id == id))
        m = r.scalar_one_or_none()
        return _to_entity(m) if m else None

    async def find_by_ids(self, ids: list[UUID]) -> list[Usuario]:
        if not ids:
            return []
        rows = (await self._session.execute(select(UserModel).where(UserModel.id.in_(ids)))).scalars().all()
        return [_to_entity(m) for m in rows]

    async def save(self, usuario: Usuario) -> Usuario:
        r = await self._session.execute(select(UserModel).where(UserModel.id == usuario.id))
        m = r.scalar_one_or_none()
        if m:
            m.correo_institucional = usuario.correo_institucional.lower()
            m.password_hash = usuario.password_hash
            m.estado = usuario.estado.value
            m.nombre = usuario.nombre
            m.apellido = usuario.apellido
            m.moodle_user_id = usuario.moodle_user_id
            m.updated_at = usuario.updated_at
        else:
            m = UserModel(
                id=usuario.id,
                correo_institucional=usuario.correo_institucional.lower(),
                password_hash=usuario.password_hash,
                estado=usuario.estado.value,
                nombre=usuario.nombre,
                apellido=usuario.apellido,
                moodle_user_id=usuario.moodle_user_id,
                created_at=usuario.created_at,
                updated_at=usuario.updated_at,
            )
            self._session.add(m)
        await self._session.flush()
        return _to_entity(m)

    async def exists_by_correo(self, correo: str) -> bool:
        r = await self._session.execute(select(func.count()).where(UserModel.correo_institucional == correo.lower()))
        return r.scalar_one() > 0

    async def find_all(self, offset: int = 0, limit: int = 20) -> tuple[list[Usuario], int]:
        total = (await self._session.execute(select(func.count()).select_from(UserModel))).scalar_one()
        rows = (await self._session.execute(select(UserModel).offset(offset).limit(limit))).scalars().all()
        return [_to_entity(m) for m in rows], total

    async def update_estado(self, id: UUID, estado: str) -> None:
        await self._session.execute(update(UserModel).where(UserModel.id == id).values(estado=estado))


def _to_entity(m: UserModel) -> Usuario:
    return Usuario(
        id=m.id,
        correo_institucional=m.correo_institucional,
        password_hash=m.password_hash,
        estado=EstadoUsuario(m.estado),
        nombre=m.nombre,
        apellido=m.apellido,
        moodle_user_id=m.moodle_user_id,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )
