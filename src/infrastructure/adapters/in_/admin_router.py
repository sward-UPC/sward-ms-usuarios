from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from src.infrastructure.adapters.in_.middleware import require_admin
from src.infrastructure.adapters.out_.redis_adapter import RedisAdapter
from src.infrastructure.adapters.out_.usuario_postgres_adapter import (
    UsuarioPostgresAdapter,
)
from src.infrastructure.db.database import get_session

router = APIRouter(prefix="/admin", tags=["Administración"])


class UpdateStatusRequest(BaseModel):
    estado: str


@router.get("/users")
async def list_users(
    offset: int = 0,
    limit: int = 20,
    _: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    usuarios, total = await UsuarioPostgresAdapter(session).find_all(
        offset=offset, limit=limit
    )
    return {
        "items": [
            {"id": str(u.id), "correo": u.correo_institucional, "estado": u.estado}
            for u in usuarios
        ],
        "total": total,
    }


@router.patch("/users/{user_id}/status")
async def update_status(
    user_id: UUID,
    body: UpdateStatusRequest,
    _: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    if body.estado not in {"activo", "inactivo", "bloqueado"}:
        raise HTTPException(status_code=422, detail="Estado inválido.")
    repo = UsuarioPostgresAdapter(session)
    if not await repo.find_by_id(user_id):
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    await repo.update_estado(user_id, body.estado)
    await RedisAdapter().invalidar_permisos(user_id)
    return {"id": str(user_id), "estado": body.estado}
