"""Contratos HTTP del concern de administración (panel admin)."""

from pydantic import BaseModel, ConfigDict, Field

from src.domain.entities.rol import TipoRol

_EXAMPLE_UUID = "550e8400-e29b-41d4-a716-446655440000"


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


class DatabaseHealthResponse(BaseModel):
    """Estado de la base de datos de un microservicio."""

    servicio: str = Field(..., description="Nombre del microservicio")
    base_de_datos: str = Field(..., description="Nombre de la base de datos")
    estado: str = Field(..., description="operativo | caido")
    latencia_ms: float | None = Field(None, description="Latencia del chequeo en ms")
    detalle: str | None = Field(None, description="Información adicional / error")
