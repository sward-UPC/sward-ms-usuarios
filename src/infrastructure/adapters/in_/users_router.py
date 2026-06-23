from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, status

from src.application.use_cases.gestionar_usuarios import (
    GestionarUsuariosUseCase,
    UsuarioNoEncontradoError,
)
from src.infrastructure.adapters.in_.middleware import get_current_user
from src.infrastructure.adapters.in_.schemas import (
    ActualizarPerfilRequest,
    DeleteCuentaResponse,
    PerfilResponse,
    PreferenciasRequest,
)
from src.infrastructure.dependencies import get_gestionar_usuarios_uc

router = APIRouter(prefix="/users", tags=["Usuarios"])


def _user_response(u, current_user: dict) -> PerfilResponse:
    return PerfilResponse(
        id=str(u.id),
        correo=u.correo_institucional,
        estado=u.estado if isinstance(u.estado, str) else u.estado.value,
        nombre=u.nombre,
        apellido=u.apellido,
        moodle_user_id=u.moodle_user_id,
        avatar_color=u.avatar_color,
        avatar_url=u.avatar_url,
        notif_logros=getattr(u, "notif_logros", True),
        rol=current_user.get("rol"),
        permisos=current_user.get("permisos", []),
    )


@router.get("/me", response_model=PerfilResponse, summary="Perfil del usuario autenticado")
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


# Límite del data URL del avatar (~1.6 MB para imágenes ~1.2 MB ya comprimidas).
_MAX_AVATAR_URL_LEN = 1_600_000


@router.put("/me", response_model=PerfilResponse, summary="Actualiza el perfil del usuario autenticado")
async def update_me(
    body: ActualizarPerfilRequest = Body(...),
    current_user: dict = Depends(get_current_user),
    uc: GestionarUsuariosUseCase = Depends(get_gestionar_usuarios_uc),
):
    """Actualiza los campos personalizables del perfil (color e imagen de avatar).

    Nombre, correo, institución y rol provienen de Moodle y NO se modifican aquí.

    **Auth:** JWT requerido
    """
    if body.avatar_url is not None and len(body.avatar_url) > _MAX_AVATAR_URL_LEN:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="La imagen es demasiado grande. Usa una foto más pequeña.",
        )
    try:
        u = await uc.actualizar_perfil(
            UUID(current_user["sub"]),
            avatar_color=body.avatar_color,
            avatar_url=body.avatar_url,
        )
    except UsuarioNoEncontradoError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return _user_response(u, current_user)


@router.put("/me/preferences", response_model=PerfilResponse, summary="Actualiza preferencias de notificación")
async def update_preferences(
    body: PreferenciasRequest = Body(...),
    current_user: dict = Depends(get_current_user),
    uc: GestionarUsuariosUseCase = Depends(get_gestionar_usuarios_uc),
):
    """Actualiza las preferencias de notificación del usuario autenticado.

    **Auth:** JWT requerido
    """
    try:
        u = await uc.actualizar_preferencias(UUID(current_user["sub"]), body.notif_logros)
    except UsuarioNoEncontradoError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return _user_response(u, current_user)


@router.delete("/me", response_model=DeleteCuentaResponse, summary="Elimina la cuenta del usuario autenticado")
async def delete_me(
    current_user: dict = Depends(get_current_user),
    uc: GestionarUsuariosUseCase = Depends(get_gestionar_usuarios_uc),
):
    """Elimina (desactiva) la cuenta del usuario autenticado y revoca sus sesiones.

    **Auth:** JWT requerido
    """
    try:
        await uc.eliminar_cuenta(UUID(current_user["sub"]))
    except UsuarioNoEncontradoError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return DeleteCuentaResponse(ok=True)


@router.get("/{user_id}", response_model=PerfilResponse, summary="Perfil de un usuario por UUID")
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
