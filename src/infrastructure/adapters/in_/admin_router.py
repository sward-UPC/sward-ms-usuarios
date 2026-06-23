import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from uuid import UUID, uuid4

import httpx
import psutil
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.use_cases.gestionar_usuarios import (
    EstadoInvalidoError,
    GestionarUsuariosUseCase,
    RolNoEncontradoError,
    UsuarioNoEncontradoError,
)
from src.infrastructure.adapters.in_.middleware import require_admin
from src.infrastructure.adapters.in_.schemas import (
    AssignRoleRequest,
    AssignRoleResponse,
    AuditLogResponse,
    DatabaseHealthResponse,
    MetricsResponse,
    ModelConfigResponse,
    RetrainResponse,
    ServiceHealthResponse,
    SystemMetricsResponse,
    SystemStatusResponse,
    UpdateStatusRequest,
    UpdateStatusResponse,
    UsuarioAdminResponse,
    UsuarioListResponse,
    UsuariosPorRolResponse,
)
from src.infrastructure.adapters.out_.redis_adapter import RedisAdapter
from src.infrastructure.config.settings import settings
from src.infrastructure.db.database import get_session
from src.infrastructure.db.models.audit_log_model import AuditLogModel
from src.infrastructure.db.models.role_model import RoleModel, user_roles
from src.infrastructure.db.models.user_model import UserModel
from src.infrastructure.dependencies import get_gestionar_usuarios_uc, get_redis_adapter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Administración"])


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
