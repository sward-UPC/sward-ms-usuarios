from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.application.use_cases.gestionar_usuarios import GestionarUsuariosUseCase
from src.infrastructure.adapters.in_.middleware import require_service_key
from src.infrastructure.dependencies import get_gestionar_usuarios_uc

# Endpoints internos service-to-service (s2s). Autenticados por X-Service-Key,
# no por JWT de usuario. Consumidos por otros microservicios (ms-trazabilidad).
router = APIRouter(
    prefix="/internal",
    tags=["Internal (s2s)"],
    dependencies=[Depends(require_service_key)],
)


class UsersByIdsRequest(BaseModel):
    ids: list[UUID] = Field(..., description="Lista de UUIDs de usuarios a consultar")


@router.post("/users/by-ids", summary="Perfiles de usuarios por lista de UUID (s2s)")
async def users_by_ids(
    req: UsersByIdsRequest,
    uc: GestionarUsuariosUseCase = Depends(get_gestionar_usuarios_uc),
) -> list[dict]:
    """Retorna los perfiles (nombre, apellido, correo) de los UUIDs solicitados.

    Pensado para que otros microservicios enriquezcan sus respuestas con datos
    de usuario sin exponer el endpoint a clientes finales. Los IDs inexistentes
    simplemente se omiten del resultado.

    **Auth:** X-Service-Key (s2s)
    """
    usuarios = await uc.consultar_varios(req.ids)
    return [
        {
            "id": str(u.id),
            "correo": u.correo_institucional,
            "nombre": u.nombre,
            "apellido": u.apellido,
            "moodle_user_id": u.moodle_user_id,
        }
        for u in usuarios
    ]
