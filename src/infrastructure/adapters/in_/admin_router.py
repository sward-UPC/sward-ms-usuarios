from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.rol import TipoRol
from src.infrastructure.adapters.in_.middleware import require_admin
from src.infrastructure.adapters.out_.redis_adapter import RedisAdapter
from src.infrastructure.adapters.out_.rol_postgres_adapter import RolPostgresAdapter
from src.infrastructure.adapters.out_.usuario_postgres_adapter import UsuarioPostgresAdapter
from src.infrastructure.db.database import get_session
from src.infrastructure.dependencies import get_redis_adapter

router = APIRouter(prefix="/admin", tags=["Administración"])


class UpdateStatusRequest(BaseModel):
    estado: str


class AssignRoleRequest(BaseModel):
    rol: TipoRol


@router.get("/users")
async def list_users(
    offset: int = 0,
    limit: int = 20,
    _: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    usuarios, total = await UsuarioPostgresAdapter(session).find_all(offset=offset, limit=limit)
    return {
        "items": [{"id": str(u.id), "correo": u.correo_institucional, "estado": u.estado} for u in usuarios],
        "total": total,
    }


@router.patch("/users/{user_id}/status")
async def update_user_status(
    user_id: UUID,
    body: UpdateStatusRequest,
    _: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    cache: RedisAdapter = Depends(get_redis_adapter),
):
    if body.estado not in {"activo", "inactivo", "bloqueado"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Estado inválido.")
    repo = UsuarioPostgresAdapter(session)
    if not await repo.find_by_id(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")
    await repo.update_estado(user_id, body.estado)
    await cache.invalidar_permisos(user_id)
    return {"id": str(user_id), "estado": body.estado}


@router.post("/users/{user_id}/roles", status_code=status.HTTP_200_OK)
async def assign_user_role(
    user_id: UUID,
    body: AssignRoleRequest,
    _: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    cache: RedisAdapter = Depends(get_redis_adapter),
):
    """Asigna un rol a un usuario. Exclusivo de administradores.

    Es el único punto del sistema autorizado para conceder roles
    docente/administrador; el registro público nunca puede hacerlo.
    """
    usuario_repo = UsuarioPostgresAdapter(session)
    if not await usuario_repo.find_by_id(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")

    rol_repo = RolPostgresAdapter(session)
    rol = await rol_repo.find_by_nombre(body.rol)
    if not rol:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rol no encontrado.")

    await rol_repo.assign_rol(user_id, rol.id)
    await cache.invalidar_permisos(user_id)
    return {"id": str(user_id), "rol": str(body.rol)}
