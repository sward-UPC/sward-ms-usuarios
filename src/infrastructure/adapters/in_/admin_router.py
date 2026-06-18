from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
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


class UpdateStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    estado: str = Field(max_length=32)


class AssignRoleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rol: TipoRol


async def _write_audit(
    session: AsyncSession,
    admin_id: UUID | None,
    accion: str,
    entidad: str,
    entidad_id: str | None = None,
    detalle: str | None = None,
) -> None:
    log = AuditLogModel(
        id=uuid4(),
        admin_id=admin_id,
        accion=accion,
        entidad=entidad,
        entidad_id=entidad_id,
        detalle=detalle,
        timestamp=datetime.now(timezone.utc),
    )
    session.add(log)


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------


@router.get("/users", summary="Listar usuarios con rol (admin)")
async def list_users(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    _: dict = Depends(require_admin),
    uc: GestionarUsuariosUseCase = Depends(get_gestionar_usuarios_uc),
):
    """Lista paginada de usuarios con nombre, apellido, rol y moodle_user_id.

    **Auth:** JWT administrador | **Paginación:** offset + limit (máx 100)
    """
    usuarios_con_rol, total = await uc.listar_con_roles(offset=offset, limit=limit)
    items = [
        {
            "id": str(u.id),
            "correo": u.correo_institucional,
            "nombre": u.nombre,
            "apellido": u.apellido,
            "estado": u.estado if isinstance(u.estado, str) else u.estado.value,
            "rol": rol,
            "moodle_user_id": u.moodle_user_id,
        }
        for u, rol in usuarios_con_rol
    ]
    return {"items": items, "total": total}


@router.patch("/users/{user_id}/status", summary="Cambiar estado de usuario")
async def update_user_status(
    user_id: UUID,
    body: UpdateStatusRequest,
    admin: dict = Depends(require_admin),
    uc: GestionarUsuariosUseCase = Depends(get_gestionar_usuarios_uc),
    session: AsyncSession = Depends(get_session),
):
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
    return {"id": str(user_id), "estado": usuario.estado}


@router.post("/users/{user_id}/roles", status_code=status.HTTP_200_OK, summary="Asignar rol a usuario")
async def assign_user_role(
    user_id: UUID,
    body: AssignRoleRequest,
    admin: dict = Depends(require_admin),
    uc: GestionarUsuariosUseCase = Depends(get_gestionar_usuarios_uc),
    session: AsyncSession = Depends(get_session),
):
    """Asigna un rol a un usuario. Único punto autorizado para conceder docente/admin."""
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
    return {"id": str(user_id), "rol": str(body.rol)}


# ---------------------------------------------------------------------------
# Métricas
# ---------------------------------------------------------------------------


@router.get("/metrics", summary="KPIs del panel de administración")
async def get_metrics(
    _: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Retorna totales de usuarios, activos e inactivos, y distribución por rol.

    **Auth:** JWT administrador
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
    usuarios_por_rol: dict[str, int] = {row.nombre: row.total for row in roles_result}

    return {
        "total_usuarios": total,
        "usuarios_activos": activos,
        "usuarios_inactivos": total - activos,
        "usuarios_por_rol": {
            "estudiante": usuarios_por_rol.get("estudiante", 0),
            "docente": usuarios_por_rol.get("docente", 0),
            "administrador": usuarios_por_rol.get("administrador", 0),
        },
    }


# ---------------------------------------------------------------------------
# Logs de auditoría
# ---------------------------------------------------------------------------


@router.get("/logs", summary="Logs de auditoría (acciones admin)")
async def get_logs(
    limit: int = Query(default=50, ge=1, le=200),
    _: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Retorna el historial de acciones administrativas ordenado por fecha descendente.

    Registra cambios de estado y asignaciones de rol realizadas por administradores.

    **Auth:** JWT administrador | **Orden:** más reciente primero
    """
    q = select(AuditLogModel).order_by(AuditLogModel.timestamp.desc()).limit(limit)
    result = await session.execute(q)
    logs = result.scalars().all()
    return [
        {
            "id": str(log.id),
            "accion": log.accion,
            "entidad": log.entidad,
            "entidad_id": log.entidad_id,
            "detalle": log.detalle,
            "admin_id": str(log.admin_id) if log.admin_id else None,
            "timestamp": log.timestamp.isoformat(),
        }
        for log in logs
    ]
