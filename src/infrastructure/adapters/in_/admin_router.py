import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from uuid import UUID, uuid4

import httpx
import psutil
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.use_cases.gestionar_usuarios import (
    EstadoInvalidoError,
    GestionarUsuariosUseCase,
    RolNoEncontradoError,
    UsuarioNoEncontradoError,
)
from src.domain.entities.rol import TipoRol
from src.infrastructure.adapters.in_.middleware import require_admin
from src.infrastructure.adapters.out_.redis_adapter import RedisAdapter
from src.infrastructure.config.settings import settings
from src.infrastructure.db.database import get_session
from src.infrastructure.db.models.audit_log_model import AuditLogModel
from src.infrastructure.db.models.role_model import RoleModel, user_roles
from src.infrastructure.db.models.user_model import UserModel
from src.infrastructure.dependencies import get_gestionar_usuarios_uc, get_redis_adapter

logger = logging.getLogger(__name__)

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
    sesiones_activas: int = Field(0, description="Sesiones activas (refresh tokens vigentes en Redis)", example=12)
    dominio_plataforma: float | None = Field(
        None,
        description="Dominio promedio de la plataforma (0-100); None si no disponible",
        example=68.5,
    )


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
    cache: RedisAdapter = Depends(get_redis_adapter),
):
    """Retorna totales de usuarios, activos, inactivos y distribución por rol.

    Incluye sesiones activas (Redis) y el dominio promedio de la plataforma
    (s2s a ms-trazabilidad, no bloqueante: si falla queda en None).

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

    try:
        sesiones_activas = await cache.contar_sesiones_activas()
    except Exception:  # noqa: BLE001 — métrica best-effort, no debe tumbar el panel
        sesiones_activas = 0

    dominio_plataforma = await _consultar_dominio_plataforma()

    return MetricsResponse(
        total_usuarios=total,
        usuarios_activos=activos,
        usuarios_inactivos=total - activos,
        usuarios_por_rol=UsuariosPorRolResponse(
            estudiante=por_rol.get("estudiante", 0),
            docente=por_rol.get("docente", 0),
            administrador=por_rol.get("administrador", 0),
        ),
        sesiones_activas=sesiones_activas,
        dominio_plataforma=dominio_plataforma,
    )


async def _consultar_dominio_plataforma() -> float | None:
    """Dominio promedio de la plataforma vía ms-trazabilidad (best-effort).

    Devuelve None si el servicio no responde para que el panel degrade limpio.
    """
    url = f"{settings.trazabilidad_service_url}/internal/metrics/platform"
    headers = {"X-Service-Key": settings.service_key}
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.json().get("dominio_promedio")
    except Exception:  # noqa: BLE001 — KPI opcional, nunca debe romper /metrics
        return None


# ---------------------------------------------------------------------------
# Logs de auditoría
# ---------------------------------------------------------------------------


class ServiceHealthResponse(BaseModel):
    """Estado de salud de un componente del sistema."""

    nombre: str = Field(..., description="Nombre del servicio")
    estado: str = Field(..., description="operativo | degradado | caido")
    latencia_ms: float | None = Field(None, description="Latencia en milisegundos (None si no disponible)")
    detalle: str | None = Field(None, description="Información adicional")


class SystemStatusResponse(BaseModel):
    """Estado de salud de todos los componentes de la plataforma."""

    api: ServiceHealthResponse
    base_de_datos: ServiceHealthResponse
    redis: ServiceHealthResponse
    uptime_segundos: float = Field(..., description="Segundos transcurridos desde el inicio del proceso")


class SystemMetricsResponse(BaseModel):
    """Métricas de recursos del proceso y host."""

    cpu_pct: float = Field(..., description="Porcentaje de uso de CPU (0–100)")
    ram_pct: float = Field(..., description="Porcentaje de uso de RAM (0–100)")
    ram_usado_mb: float = Field(..., description="RAM usada en MB")
    ram_total_mb: float = Field(..., description="RAM total del host en MB")
    disco_pct: float = Field(..., description="Porcentaje de uso del disco (0–100)")
    disco_usado_gb: float = Field(..., description="Disco usado en GB")
    disco_total_gb: float = Field(..., description="Disco total en GB")
    uptime_segundos: float = Field(..., description="Segundos transcurridos desde el inicio del proceso")


class ModelConfigResponse(BaseModel):
    """Parámetros de configuración del modelo SAKT."""

    version: str = Field(..., description="Versión del modelo (ej. SAKT v2.1)")
    tasa_aprendizaje: float | None = Field(None, description="Learning rate del modelo")
    umbral_confianza_xai: float = Field(..., description="Umbral de confianza XAI (0–1)")
    ventana_contexto: int | None = Field(None, description="Longitud de secuencia (seq_len) real")
    dimension_embedding: int | None = Field(None, description="Dimensión del embedding real")
    ultimo_reentrenamiento: str | None = Field(None, description="Timestamp ISO 8601 del último reentrenamiento real")
    # Métricas/estado REALES leídas del artefacto en S3 (vía ms-recomendacion).
    datos_disponibles: bool = Field(True, description="False si no se pudo leer el modelo (servicio apagado)")
    modelo_real: bool = Field(False, description="True si el entorno corre el modelo real (no mock)")
    test_auc: float | None = Field(None, description="AUC de validación del modelo entrenado")
    n_conceptos: int | None = Field(None, description="Número de conceptos/skills del modelo")
    n_heads: int | None = Field(None, description="Cabezas de atención del SAKT")
    n_layers: int | None = Field(None, description="Bloques de atención del SAKT")
    n_estudiantes: int | None = Field(None, description="Estudiantes usados en el último entreno")
    n_muestras: int | None = Field(None, description="Secuencias usadas en el último entreno")
    epochs: int | None = Field(None, description="Épocas del último entrenamiento")


class RetrainResponse(BaseModel):
    """Confirmación de solicitud de reentrenamiento."""

    mensaje: str
    tarea_id: str


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


# ---------------------------------------------------------------------------
# Sistema — health y métricas de recursos
# ---------------------------------------------------------------------------


@router.get(
    "/system/status",
    response_model=SystemStatusResponse,
    summary="Estado de salud de los componentes del sistema",
    responses={
        200: {"description": "Estado actual de API, base de datos y Redis"},
        401: {"description": "JWT ausente o inválido"},
        403: {"description": "El usuario no tiene rol administrador"},
    },
)
async def get_system_status(
    _: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    cache: RedisAdapter = Depends(get_redis_adapter),
):
    """Verifica la conectividad y latencia de los componentes principales.

    **SLA:** <500ms | **Auth:** JWT administrador
    """
    proc = psutil.Process(os.getpid())
    uptime = time.time() - proc.create_time()

    # DB health
    db_start = time.monotonic()
    try:
        await session.execute(text("SELECT 1"))
        db_latency = round((time.monotonic() - db_start) * 1000, 2)
        db_health = ServiceHealthResponse(
            nombre="Base de Datos", estado="operativo", latencia_ms=db_latency, detalle=None
        )
    except Exception as exc:
        db_health = ServiceHealthResponse(
            nombre="Base de Datos", estado="caido", latencia_ms=None, detalle=str(exc)[:120]
        )

    # Redis health
    redis_start = time.monotonic()
    try:
        await cache.ping()
        redis_latency = round((time.monotonic() - redis_start) * 1000, 2)
        redis_health = ServiceHealthResponse(
            nombre="Redis", estado="operativo", latencia_ms=redis_latency, detalle=None
        )
    except Exception as exc:
        redis_health = ServiceHealthResponse(nombre="Redis", estado="caido", latencia_ms=None, detalle=str(exc)[:120])

    api_health = ServiceHealthResponse(
        nombre="API",
        estado="operativo",
        latencia_ms=None,
        detalle=f"uptime {round(uptime / 3600, 1)} h",
    )

    return SystemStatusResponse(
        api=api_health,
        base_de_datos=db_health,
        redis=redis_health,
        uptime_segundos=round(uptime, 1),
    )


@router.get(
    "/system/metrics",
    response_model=SystemMetricsResponse,
    summary="Métricas de recursos del host (CPU, RAM, disco)",
    responses={
        200: {"description": "Uso de recursos en tiempo real vía psutil"},
        401: {"description": "JWT ausente o inválido"},
        403: {"description": "El usuario no tiene rol administrador"},
    },
)
async def get_system_metrics(
    _: dict = Depends(require_admin),
):
    """Devuelve CPU, RAM y disco del host donde corre el proceso.

    Usa `psutil` — los valores son del contenedor ECS, no del host EC2 subyacente.

    **SLA:** <200ms | **Auth:** JWT administrador
    """
    proc = psutil.Process(os.getpid())
    uptime = time.time() - proc.create_time()

    # Ventana de 0.5s para una muestra real (interval=0.1 daba casi siempre 0.0
    # en contenedores ociosos). Se combina con el CPU del propio proceso para no
    # reportar 0 cuando el servicio sí está trabajando.
    cpu_sistema = psutil.cpu_percent(interval=0.5)
    cpu_proceso = proc.cpu_percent(interval=None)
    cpu = round(max(cpu_sistema, cpu_proceso), 1)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    return SystemMetricsResponse(
        cpu_pct=cpu,
        ram_pct=round(mem.percent, 1),
        ram_usado_mb=round(mem.used / 1024 / 1024, 1),
        ram_total_mb=round(mem.total / 1024 / 1024, 1),
        disco_pct=round(disk.percent, 1),
        disco_usado_gb=round(disk.used / 1024 / 1024 / 1024, 2),
        disco_total_gb=round(disk.total / 1024 / 1024 / 1024, 2),
        uptime_segundos=round(uptime, 1),
    )


# ---------------------------------------------------------------------------
# Estado de las bases de datos de toda la plataforma
# ---------------------------------------------------------------------------

# Microservicios con base de datos propia (RDS independiente por servicio).
_DB_SERVICES = [
    "usuarios",
    "trazabilidad",
    "recomendacion",
    "cursos-recursos",
    "integracion-lms",
    "xai",
]


class DatabaseHealthResponse(BaseModel):
    """Estado de la base de datos de un microservicio."""

    servicio: str = Field(..., description="Nombre del microservicio")
    base_de_datos: str = Field(..., description="Nombre de la base de datos")
    estado: str = Field(..., description="operativo | caido")
    latencia_ms: float | None = Field(None, description="Latencia del chequeo en ms")
    detalle: str | None = Field(None, description="Información adicional / error")


async def _check_own_db(session: AsyncSession) -> DatabaseHealthResponse:
    """Chequeo profundo de la DB propia (SELECT 1)."""
    start = time.monotonic()
    try:
        await session.execute(text("SELECT 1"))
        return DatabaseHealthResponse(
            servicio="usuarios",
            base_de_datos="sward_usuarios",
            estado="operativo",
            latencia_ms=round((time.monotonic() - start) * 1000, 2),
        )
    except Exception as exc:  # noqa: BLE001
        return DatabaseHealthResponse(
            servicio="usuarios",
            base_de_datos="sward_usuarios",
            estado="caido",
            latencia_ms=None,
            detalle=str(exc)[:120],
        )


async def _check_service_db(client: httpx.AsyncClient, name: str) -> DatabaseHealthResponse:
    """Sondea la salud de otro servicio vía Cloud Map (su /health confirma que
    el servicio y su DB arrancaron; un servicio con DB caída no queda healthy).
    """
    db_name = f"sward_{name.replace('-', '_')}"
    url = f"http://{name}.{settings.internal_namespace}:{settings.internal_port}/health"
    start = time.monotonic()
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        return DatabaseHealthResponse(
            servicio=name,
            base_de_datos=db_name,
            estado="operativo",
            latencia_ms=round((time.monotonic() - start) * 1000, 2),
        )
    except Exception as exc:  # noqa: BLE001
        return DatabaseHealthResponse(
            servicio=name,
            base_de_datos=db_name,
            estado="caido",
            latencia_ms=None,
            detalle=str(exc)[:120],
        )


@router.get(
    "/system/databases",
    response_model=list[DatabaseHealthResponse],
    summary="Estado de las bases de datos de todos los microservicios",
    responses={
        200: {"description": "Estado de cada base de datos de la plataforma"},
        401: {"description": "JWT ausente o inválido"},
        403: {"description": "El usuario no tiene rol administrador"},
    },
)
async def get_databases_status(
    _: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Estado de las 6 bases de datos de la plataforma.

    La DB propia (usuarios) se chequea en profundidad (SELECT 1); las demás se
    sondean vía el /health de cada servicio por Cloud Map, en paralelo.

    **SLA:** <2s | **Auth:** JWT administrador
    """
    own = await _check_own_db(session)
    otros = [s for s in _DB_SERVICES if s != "usuarios"]
    async with httpx.AsyncClient(timeout=2.0) as client:
        resultados = await asyncio.gather(*(_check_service_db(client, name) for name in otros))
    # Mantiene el orden de _DB_SERVICES (usuarios primero).
    por_nombre = {own.servicio: own, **{r.servicio: r for r in resultados}}
    return [por_nombre[name] for name in _DB_SERVICES]


# ---------------------------------------------------------------------------
# Modelo SAKT
# ---------------------------------------------------------------------------

_MODEL_VERSION = "SAKT v2.1"


@router.get(
    "/model/config",
    response_model=ModelConfigResponse,
    summary="Parámetros de configuración del modelo SAKT",
    responses={
        200: {"description": "Configuración actual del modelo de Knowledge Tracing"},
        401: {"description": "JWT ausente o inválido"},
        403: {"description": "El usuario no tiene rol administrador"},
    },
)
async def get_model_config(
    _: dict = Depends(require_admin),
):
    """Devuelve los hiperparámetros y métricas REALES del modelo SAKT.

    Lee la metadata del artefacto entrenado vía ms-recomendacion (s2s), que la
    obtiene del checkpoint en S3: fecha real de reentrenamiento, seq_len, embedding,
    AUC de validación, etc. Si recomendación está apagado, responde
    `datos_disponibles=False` (sin inventar valores).

    **Auth:** JWT administrador
    """
    url = (
        f"http://recomendacion.{settings.internal_namespace}:{settings.internal_port}"
        "/recommendations/internal/model-info"
    )
    headers = {"X-Service-Key": settings.service_key}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            info = resp.json()
    except Exception as exc:  # noqa: BLE001 — el panel debe degradar, no romper
        logger.warning("No se pudo leer la info real del modelo: %s", exc)
        return ModelConfigResponse(
            version=_MODEL_VERSION,
            umbral_confianza_xai=0.75,
            datos_disponibles=False,
        )

    return ModelConfigResponse(
        version=_MODEL_VERSION,
        tasa_aprendizaje=info.get("learning_rate"),
        umbral_confianza_xai=0.75,
        ventana_contexto=info.get("seq_len"),
        dimension_embedding=info.get("emb_size"),
        ultimo_reentrenamiento=info.get("entrenado_en"),
        datos_disponibles=True,
        modelo_real=not info.get("mock", True),
        test_auc=info.get("test_auc"),
        n_conceptos=info.get("n_conceptos"),
        n_heads=info.get("n_heads"),
        n_layers=info.get("n_layers"),
        n_estudiantes=info.get("n_estudiantes"),
        n_muestras=info.get("n_muestras"),
        epochs=info.get("epochs"),
    )


@router.post(
    "/model/retrain",
    response_model=RetrainResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Solicitar reentrenamiento del modelo SAKT",
    responses={
        202: {"description": "Solicitud de reentrenamiento aceptada"},
        401: {"description": "JWT ausente o inválido"},
        403: {"description": "El usuario no tiene rol administrador"},
    },
)
async def trigger_retrain(
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Registra en auditoría una solicitud de reentrenamiento del modelo SAKT.

    El reentrenamiento real es un job programado (GitHub Actions semanal) que
    reentrena con las interacciones reales y sube el checkpoint a S3; la fecha y
    métricas resultantes se reflejan luego en `/model/config`. Esta acción deja
    constancia de la solicitud manual, no dispara el entrenamiento al instante.

    **Auth:** JWT administrador
    """
    tarea_id = str(uuid4())

    await _write_audit(
        session,
        admin_id=UUID(admin["sub"]),
        accion="retrain_modelo",
        entidad="modelo_sakt",
        entidad_id=None,
        detalle=f"tarea_id={tarea_id}",
    )

    return RetrainResponse(
        mensaje=(
            "Solicitud registrada en auditoría. El reentrenamiento se ejecuta de "
            "forma programada (semanal) con las interacciones reales; la fecha y el "
            "AUC se actualizarán al completarse."
        ),
        tarea_id=tarea_id,
    )
