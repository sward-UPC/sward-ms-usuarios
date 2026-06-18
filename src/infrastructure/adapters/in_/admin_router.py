from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.use_cases.gestionar_usuarios import (
    EstadoInvalidoError,
    GestionarUsuariosUseCase,
    RolNoEncontradoError,
    UsuarioNoEncontradoError,
)
from src.domain.entities.rol import TipoRol
from src.infrastructure.adapters.in_.middleware import require_admin
from src.infrastructure.db.database import get_session
from src.infrastructure.db.models.audit_log_model import AuditLogModel
from src.infrastructure.db.models.role_model import RoleModel, user_roles
from src.infrastructure.db.models.user_model import UserModel
from src.infrastructure.dependencies import get_gestionar_usuarios_uc

router = APIRouter(prefix="/admin", tags=["Administración"])

_EXAMPLE_UUID = "550e8400-e29b-41d4-a716-446655440000"

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class UpdateStatusRequest(BaseModel):
    """Solicitud para cambiar el estado de un usuario."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"example": {"estado": "inactivo"}},
    )

    estado: str = Field(
        ...,
        max_length=32,
        description="Nuevo estado del usuario (activo, inactivo, bloqueado)",
        example="inactivo",
    )


class AssignRoleRequest(BaseModel):
    """Solicitud para asignar un rol a un usuario."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"example": {"rol": "docente"}},
    )

    rol: TipoRol = Field(..., description="Rol a asignar (estudiante, docente, administrador)")


class UsuarioAdminResponse(BaseModel):
    """Perfil de usuario visto desde el panel de administración."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": _EXAMPLE_UUID,
                "correo": "juan.perez@sward.edu",
                "nombre": "Juan",
                "apellido": "Pérez",
                "estado": "activo",
                "rol": "estudiante",
                "moodle_user_id": 7,
            }
        }
    )

    id: str = Field(..., description="UUID del usuario", example=_EXAMPLE_UUID)
    correo: str = Field(..., description="Correo institucional", example="juan.perez@sward.edu")
    nombre: str | None = Field(None, description="Nombre", example="Juan")
    apellido: str | None = Field(None, description="Apellido", example="Pérez")
    estado: str = Field(..., description="Estado actual (activo, inactivo, bloqueado)", example="activo")
    rol: str = Field(..., description="Rol principal del usuario", example="estudiante")
    moodle_user_id: int | None = Field(None, description="ID del usuario en Moodle", example=7)


class UsuarioListResponse(BaseModel):
    """Respuesta paginada de la lista de usuarios."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "items": [
                    {
                        "id": _EXAMPLE_UUID,
                        "correo": "juan.perez@sward.edu",
                        "nombre": "Juan",
                        "apellido": "Pérez",
                        "estado": "activo",
                        "rol": "estudiante",
                        "moodle_user_id": 7,
                    }
                ],
                "total": 42,
            }
        }
    )

    items: list[UsuarioAdminResponse]
    total: int = Field(..., description="Total de usuarios en la base de datos", example=42)


class UpdateStatusResponse(BaseModel):
    """Confirmación de cambio de estado."""

    model_config = ConfigDict(json_schema_extra={"example": {"id": _EXAMPLE_UUID, "estado": "inactivo"}})

    id: str = Field(..., description="UUID del usuario modificado", example=_EXAMPLE_UUID)
    estado: str = Field(..., description="Nuevo estado aplicado", example="inactivo")


class AssignRoleResponse(BaseModel):
    """Confirmación de asignación de rol."""

    model_config = ConfigDict(json_schema_extra={"example": {"id": _EXAMPLE_UUID, "rol": "docente"}})

    id: str = Field(..., description="UUID del usuario modificado", example=_EXAMPLE_UUID)
    rol: str = Field(..., description="Rol asignado", example="docente")


class UsuariosPorRolResponse(BaseModel):
    """Distribución de usuarios por rol."""

    estudiante: int = Field(..., description="Cantidad de estudiantes", example=38)
    docente: int = Field(..., description="Cantidad de docentes", example=3)
    administrador: int = Field(..., description="Cantidad de administradores", example=1)


class MetricsResponse(BaseModel):
    """KPIs del panel de administración."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_usuarios": 42,
                "usuarios_activos": 38,
                "usuarios_inactivos": 4,
                "usuarios_por_rol": {"estudiante": 38, "docente": 3, "administrador": 1},
            }
        }
    )

    total_usuarios: int = Field(..., description="Total de usuarios registrados", example=42)
    usuarios_activos: int = Field(..., description="Usuarios con estado activo", example=38)
    usuarios_inactivos: int = Field(..., description="Usuarios sin estado activo", example=4)
    usuarios_por_rol: UsuariosPorRolResponse


class AuditLogResponse(BaseModel):
    """Entrada del log de auditoría."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": _EXAMPLE_UUID,
                "accion": "cambiar_estado",
                "entidad": "usuario",
                "entidad_id": _EXAMPLE_UUID,
                "detalle": "estado → inactivo",
                "admin_id": _EXAMPLE_UUID,
                "timestamp": "2026-06-18T01:00:00+00:00",
            }
        }
    )

    id: str = Field(..., description="UUID del registro de auditoría")
    accion: str = Field(..., description="Acción realizada", example="cambiar_estado")
    entidad: str = Field(..., description="Tipo de entidad afectada", example="usuario")
    entidad_id: str | None = Field(None, description="UUID de la entidad afectada")
    detalle: str | None = Field(None, description="Descripción detallada del cambio")
    admin_id: str | None = Field(None, description="UUID del administrador que realizó la acción")
    timestamp: str = Field(..., description="Fecha y hora UTC de la acción (ISO 8601)")


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------


async def _write_audit(
    session: AsyncSession,
    admin_id: UUID | None,
    accion: str,
    entidad: str,
    entidad_id: str | None = None,
    detalle: str | None = None,
) -> None:
    session.add(
        AuditLogModel(
            id=uuid4(),
            admin_id=admin_id,
            accion=accion,
            entidad=entidad,
            entidad_id=entidad_id,
            detalle=detalle,
            timestamp=datetime.now(timezone.utc),
        )
    )


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------


@router.get(
    "/users",
    response_model=UsuarioListResponse,
    summary="Listar usuarios (admin)",
    responses={
        200: {"description": "Lista paginada de usuarios con rol"},
        401: {"description": "JWT ausente o inválido"},
        403: {"description": "El usuario no tiene rol administrador"},
    },
)
async def list_users(
    offset: int = Query(default=0, ge=0, description="Número de registros a omitir"),
    limit: int = Query(default=20, ge=1, le=100, description="Máximo de registros a devolver"),
    _: dict = Depends(require_admin),
    uc: GestionarUsuariosUseCase = Depends(get_gestionar_usuarios_uc),
):
    """Retorna lista paginada de usuarios con nombre, apellido, rol y moodle_user_id.

    **Auth:** JWT administrador | **Paginación:** offset + limit (máx 100)
    """
    usuarios_con_rol, total = await uc.listar_con_roles(offset=offset, limit=limit)
    items = [
        UsuarioAdminResponse(
            id=str(u.id),
            correo=u.correo_institucional,
            nombre=u.nombre,
            apellido=u.apellido,
            estado=u.estado if isinstance(u.estado, str) else u.estado.value,
            rol=rol,
            moodle_user_id=u.moodle_user_id,
        )
        for u, rol in usuarios_con_rol
    ]
    return UsuarioListResponse(items=items, total=total)


@router.patch(
    "/users/{user_id}/status",
    response_model=UpdateStatusResponse,
    summary="Cambiar estado de un usuario",
    responses={
        200: {"description": "Estado actualizado correctamente"},
        401: {"description": "JWT ausente o inválido"},
        403: {"description": "El usuario no tiene rol administrador"},
        404: {"description": "Usuario no encontrado"},
        422: {"description": "Estado inválido"},
    },
)
async def update_user_status(
    user_id: UUID = Path(..., description="UUID del usuario a modificar"),
    body: UpdateStatusRequest = ...,
    admin: dict = Depends(require_admin),
    uc: GestionarUsuariosUseCase = Depends(get_gestionar_usuarios_uc),
    session: AsyncSession = Depends(get_session),
):
    """Cambia el estado de un usuario (activo, inactivo, bloqueado).

    Registra la acción en el log de auditoría.

    **SLA:** <100ms | **Auth:** JWT administrador
    """
    try:
        usuario = await uc.cambiar_estado(user_id, body.estado)
    except EstadoInvalidoError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except UsuarioNoEncontradoError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    await _write_audit(
        session,
        admin_id=UUID(admin["sub"]),
        accion="cambiar_estado",
        entidad="usuario",
        entidad_id=str(user_id),
        detalle=f"estado → {body.estado}",
    )
    estado_val = usuario.estado if isinstance(usuario.estado, str) else usuario.estado.value
    return UpdateStatusResponse(id=str(user_id), estado=estado_val)


@router.post(
    "/users/{user_id}/roles",
    response_model=AssignRoleResponse,
    status_code=status.HTTP_200_OK,
    summary="Asignar rol a un usuario",
    responses={
        200: {"description": "Rol asignado correctamente"},
        401: {"description": "JWT ausente o inválido"},
        403: {"description": "El usuario no tiene rol administrador"},
        404: {"description": "Usuario o rol no encontrado"},
    },
)
async def assign_user_role(
    user_id: UUID = Path(..., description="UUID del usuario a modificar"),
    body: AssignRoleRequest = ...,
    admin: dict = Depends(require_admin),
    uc: GestionarUsuariosUseCase = Depends(get_gestionar_usuarios_uc),
    session: AsyncSession = Depends(get_session),
):
    """Asigna un rol a un usuario. Único punto autorizado para conceder docente/administrador.

    El registro público fija siempre rol estudiante; este endpoint es la única
    vía para promover a docente o administrador.

    Registra la acción en el log de auditoría.

    **SLA:** <100ms | **Auth:** JWT administrador
    """
    try:
        await uc.asignar_rol(user_id, body.rol)
    except (UsuarioNoEncontradoError, RolNoEncontradoError) as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    await _write_audit(
        session,
        admin_id=UUID(admin["sub"]),
        accion="asignar_rol",
        entidad="usuario",
        entidad_id=str(user_id),
        detalle=f"rol → {body.rol}",
    )
    return AssignRoleResponse(id=str(user_id), rol=str(body.rol))


# ---------------------------------------------------------------------------
# Métricas
# ---------------------------------------------------------------------------


@router.get(
    "/metrics",
    response_model=MetricsResponse,
    summary="KPIs del panel de administración",
    responses={
        200: {"description": "Métricas calculadas en tiempo real desde la base de datos"},
        401: {"description": "JWT ausente o inválido"},
        403: {"description": "El usuario no tiene rol administrador"},
    },
)
async def get_metrics(
    _: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Retorna totales de usuarios, activos, inactivos y distribución por rol.

    Consulta directa a la base de datos — no usa caché.

    **SLA:** <150ms | **Auth:** JWT administrador
    """
    total = (await session.execute(select(func.count()).select_from(UserModel))).scalar_one()

    activos = (
        await session.execute(select(func.count()).select_from(UserModel).where(UserModel.estado == "activo"))
    ).scalar_one()

    roles_q = (
        select(RoleModel.nombre, func.count(user_roles.c.user_id).label("total"))
        .join(user_roles, RoleModel.id == user_roles.c.role_id)
        .group_by(RoleModel.nombre)
    )
    roles_result = await session.execute(roles_q)
    por_rol: dict[str, int] = {row.nombre: row.total for row in roles_result}

    return MetricsResponse(
        total_usuarios=total,
        usuarios_activos=activos,
        usuarios_inactivos=total - activos,
        usuarios_por_rol=UsuariosPorRolResponse(
            estudiante=por_rol.get("estudiante", 0),
            docente=por_rol.get("docente", 0),
            administrador=por_rol.get("administrador", 0),
        ),
    )


# ---------------------------------------------------------------------------
# Logs de auditoría
# ---------------------------------------------------------------------------


@router.get(
    "/logs",
    response_model=list[AuditLogResponse],
    summary="Logs de auditoría (acciones administrativas)",
    responses={
        200: {"description": "Lista de acciones admin ordenada por fecha descendente"},
        401: {"description": "JWT ausente o inválido"},
        403: {"description": "El usuario no tiene rol administrador"},
    },
)
async def get_logs(
    limit: int = Query(
        default=50,
        ge=1,
        le=200,
        description="Máximo de registros a devolver (1-200)",
    ),
    _: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Retorna el historial de acciones administrativas ordenado por fecha descendente.

    Incluye cambios de estado y asignaciones de rol realizadas por administradores.
    Solo se generan registros cuando se usan los endpoints `PATCH /status` y `POST /roles`.

    **SLA:** <100ms | **Auth:** JWT administrador | **Orden:** más reciente primero
    """
    q = select(AuditLogModel).order_by(AuditLogModel.timestamp.desc()).limit(limit)
    result = await session.execute(q)
    return [
        AuditLogResponse(
            id=str(log.id),
            accion=log.accion,
            entidad=log.entidad,
            entidad_id=log.entidad_id,
            detalle=log.detalle,
            admin_id=str(log.admin_id) if log.admin_id else None,
            timestamp=log.timestamp.isoformat(),
        )
        for log in result.scalars().all()
    ]
