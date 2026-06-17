from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from src.application.use_cases.gestionar_usuarios import (
    GestionarUsuariosUseCase,
    UsuarioNoEncontradoError,
)
from src.infrastructure.adapters.in_.middleware import get_current_user
from src.infrastructure.dependencies import get_gestionar_usuarios_uc

router = APIRouter(prefix="/users", tags=["Usuarios"])


def _user_response(u, current_user: dict) -> dict:
    return {
        "id": str(u.id),
        "correo": u.correo_institucional,
        "estado": u.estado if isinstance(u.estado, str) else u.estado.value,
        "nombre": u.nombre,
        "apellido": u.apellido,
        "moodle_user_id": u.moodle_user_id,
        "rol": current_user.get("rol"),
        "permisos": current_user.get("permisos", []),
    }


@router.get("/me", summary="Perfil del usuario autenticado")
async def get_me(
    current_user: dict = Depends(get_current_user),
    uc: GestionarUsuariosUseCase = Depends(get_gestionar_usuarios_uc),
):
    """Retorna el perfil completo del usuario autenticado.

    Extrae el UUID del claim `sub` del JWT y consulta la base de datos.

    **Auth:** JWT requerido
    """
    try:
        u = await uc.consultar(UUID(current_user["sub"]))
    except UsuarioNoEncontradoError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return _user_response(u, current_user)


@router.get("/{user_id}", summary="Perfil de un usuario por UUID")
async def get_user(
    user_id: UUID,
    current_user: dict = Depends(get_current_user),
    uc: GestionarUsuariosUseCase = Depends(get_gestionar_usuarios_uc),
):
    """Retorna el perfil de un usuario por UUID.

    Solo el propio usuario o un administrador pueden consultar este endpoint.

    **Auth:** JWT requerido
    """
    if str(user_id) != current_user["sub"] and current_user.get("rol") != "administrador":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso denegado.")
    try:
        u = await uc.consultar(user_id)
    except UsuarioNoEncontradoError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return _user_response(u, current_user)
