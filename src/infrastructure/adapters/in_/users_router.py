from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.adapters.in_.middleware import get_current_user
from src.infrastructure.adapters.out_.usuario_postgres_adapter import UsuarioPostgresAdapter
from src.infrastructure.db.database import get_session

router = APIRouter(prefix="/users", tags=["Usuarios"])


@router.get("/{user_id}")
async def get_user(
    user_id: UUID,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if str(user_id) != current_user["sub"] and current_user.get("rol") != "administrador":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso denegado.")
    u = await UsuarioPostgresAdapter(session).find_by_id(user_id)
    if not u:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")
    return {"id": str(u.id), "correo": u.correo_institucional, "estado": u.estado}
