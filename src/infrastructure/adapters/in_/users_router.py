from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from src.application.use_cases.gestionar_usuarios import (
    GestionarUsuariosUseCase,
    UsuarioNoEncontradoError,
)
from src.infrastructure.adapters.in_.middleware import get_current_user
from src.infrastructure.dependencies import get_gestionar_usuarios_uc

router = APIRouter(prefix="/users", tags=["Usuarios"])


@router.get("/{user_id}")
async def get_user(
    user_id: UUID,
    current_user: dict = Depends(get_current_user),
    uc: GestionarUsuariosUseCase = Depends(get_gestionar_usuarios_uc),
):
    if str(user_id) != current_user["sub"] and current_user.get("rol") != "administrador":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso denegado.")
    try:
        u = await uc.consultar(user_id)
    except UsuarioNoEncontradoError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return {"id": str(u.id), "correo": u.correo_institucional, "estado": u.estado}
