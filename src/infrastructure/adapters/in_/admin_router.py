from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from src.application.use_cases.gestionar_usuarios import (
    EstadoInvalidoError,
    GestionarUsuariosUseCase,
    RolNoEncontradoError,
    UsuarioNoEncontradoError,
)
from src.domain.entities.rol import TipoRol
from src.infrastructure.adapters.in_.middleware import require_admin
from src.infrastructure.dependencies import get_gestionar_usuarios_uc

router = APIRouter(prefix="/admin", tags=["Administración"])


class UpdateStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estado: str = Field(max_length=32)


class AssignRoleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rol: TipoRol


@router.get("/users")
async def list_users(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    _: dict = Depends(require_admin),
    uc: GestionarUsuariosUseCase = Depends(get_gestionar_usuarios_uc),
):
    usuarios, total = await uc.listar(offset=offset, limit=limit)
    return {
        "items": [{"id": str(u.id), "correo": u.correo_institucional, "estado": u.estado} for u in usuarios],
        "total": total,
    }


@router.patch("/users/{user_id}/status")
async def update_user_status(
    user_id: UUID,
    body: UpdateStatusRequest,
    _: dict = Depends(require_admin),
    uc: GestionarUsuariosUseCase = Depends(get_gestionar_usuarios_uc),
):
    try:
        usuario = await uc.cambiar_estado(user_id, body.estado)
    except EstadoInvalidoError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except UsuarioNoEncontradoError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return {"id": str(user_id), "estado": usuario.estado}


@router.post("/users/{user_id}/roles", status_code=status.HTTP_200_OK)
async def assign_user_role(
    user_id: UUID,
    body: AssignRoleRequest,
    _: dict = Depends(require_admin),
    uc: GestionarUsuariosUseCase = Depends(get_gestionar_usuarios_uc),
):
    """Asigna un rol a un usuario. Exclusivo de administradores.

    Es el único punto del sistema autorizado para conceder roles
    docente/administrador; el registro público nunca puede hacerlo.
    """
    try:
        await uc.asignar_rol(user_id, body.rol)
    except (UsuarioNoEncontradoError, RolNoEncontradoError) as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return {"id": str(user_id), "rol": str(body.rol)}
