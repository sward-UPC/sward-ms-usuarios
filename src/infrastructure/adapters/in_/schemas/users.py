"""Contratos HTTP del concern de perfil de usuario (self-service)."""

from pydantic import BaseModel, ConfigDict, Field


class PreferenciasRequest(BaseModel):
    """Preferencias de notificación del usuario."""

    model_config = ConfigDict(extra="forbid")
    notif_logros: bool = Field(description="Recibir notificaciones de logros (racha/recursos)")


class ActualizarPerfilRequest(BaseModel):
    """Campos personalizables del perfil. Nombre, correo, institución y rol
    provienen de Moodle y son de solo lectura: no se aceptan aquí."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "avatar_color": "#6366f1",
                "avatar_url": "data:image/jpeg;base64,/9j/4AAQSkZJRg...",
            }
        },
    )

    avatar_color: str | None = Field(
        default=None,
        description="Color del avatar en formato hex (ej. #6366f1)",
        max_length=20,
        example="#6366f1",
    )
    avatar_url: str | None = Field(
        default=None,
        description="Imagen de perfil como data URL base64 (JPEG comprimido)",
        example="data:image/jpeg;base64,/9j/4AAQSkZJRg...",
    )


class PerfilResponse(BaseModel):
    """Perfil del usuario tal como lo consumen los endpoints `/users`.

    Combina los datos persistidos del usuario con el rol y los permisos
    vigentes leídos del JWT de la sesión actual.
    """

    id: str = Field(..., description="UUID del usuario")
    correo: str = Field(..., description="Correo institucional")
    estado: str = Field(..., description="Estado actual (activo, inactivo, bloqueado)")
    nombre: str | None = Field(None, description="Nombre (proviene de Moodle)")
    apellido: str | None = Field(None, description="Apellido (proviene de Moodle)")
    moodle_user_id: int | None = Field(None, description="ID del usuario en Moodle")
    avatar_color: str | None = Field(None, description="Color del avatar (hex)")
    avatar_url: str | None = Field(None, description="Imagen de perfil (data URL)")
    notif_logros: bool = Field(True, description="Si recibe notificaciones de logros")
    rol: str | None = Field(None, description="Rol principal del JWT de la sesión")
    permisos: list[str] = Field(default_factory=list, description="Permisos del JWT de la sesión")


class DeleteCuentaResponse(BaseModel):
    """Confirmación de baja de cuenta."""

    ok: bool = Field(True, description="True si la cuenta se desactivó correctamente")
