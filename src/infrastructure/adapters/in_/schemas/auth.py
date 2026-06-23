"""Contratos HTTP del concern de autenticación (registro, login, tokens)."""

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    """Solicitud para registrar un nuevo usuario.

    El rol, nombre y apellido se obtienen automáticamente de Moodle
    usando el correo institucional como clave de búsqueda.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "correo": "estudiante01@sward.edu",
                "password": "SecurePassword123!",
            }
        },
    )

    correo: EmailStr = Field(
        ...,
        description="Correo institucional registrado en Moodle",
        example="estudiante01@sward.edu",
    )
    password: str = Field(
        ...,
        description="Contraseña (mín. 8 chars, 1 mayúscula, 1 número)",
        min_length=8,
        max_length=128,
        example="SecurePassword123!",
    )


class LoginRequest(BaseModel):
    """Solicitud para autenticar un usuario."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "correo": "estudiante@sward.test",
                "password": "SecurePassword123!",
                "device_id": "device-chrome-laptop",
            }
        },
    )

    correo: EmailStr = Field(
        ...,
        description="Correo institucional registrado",
        example="estudiante@sward.test",
    )
    password: str = Field(
        ...,
        description="Contraseña del usuario",
        min_length=8,
        max_length=128,
        example="SecurePassword123!",
    )
    device_id: str = Field(
        default="default",
        description="ID del dispositivo para logout selectivo",
        max_length=128,
        example="device-chrome-laptop",
    )


class TokenResponse(BaseModel):
    """Tokens JWT tras autenticación exitosa."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "expires_in": 900,
            }
        }
    )

    access_token: str = Field(
        ...,
        description="JWT de acceso (válido 15 minutos)",
        example="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    )
    refresh_token: str = Field(
        ...,
        description="JWT de refresco (válido 7 días)",
        example="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    )
    token_type: str = Field(
        default="bearer",
        description="Tipo de token (siempre 'bearer')",
        example="bearer",
    )
    expires_in: int = Field(
        ...,
        description="Segundos hasta expiración del access_token",
        example=900,
    )


class UsuarioRegistradoResponse(BaseModel):
    """Respuesta tras registro exitoso."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "correo": "estudiante@sward.test",
                "estado": "pendiente_verificacion",
            }
        }
    )

    id: str = Field(
        ...,
        description="UUID del usuario recién creado",
        example="550e8400-e29b-41d4-a716-446655440000",
    )
    correo: str = Field(
        ...,
        description="Correo confirmado del usuario",
        example="estudiante@sward.test",
    )
    estado: str = Field(
        ...,
        description="Estado inicial del usuario",
        example="pendiente_verificacion",
    )


class RefreshRequest(BaseModel):
    """Solicitud para refrescar el access token."""

    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(..., description="JWT de refresco obtenido en el login")


class AccessTokenResponse(BaseModel):
    """Nuevo access token tras refresco exitoso."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int


class ChangePasswordRequest(BaseModel):
    """Solicitud para cambiar la contraseña del usuario autenticado."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "password_actual": "OldPassword123!",
                "password_nueva": "NewSecurePassword456!",
            }
        },
    )

    password_actual: str = Field(
        ...,
        description="Contraseña actual del usuario",
        min_length=1,
        max_length=128,
        example="OldPassword123!",
    )
    password_nueva: str = Field(
        ...,
        description="Nueva contraseña (mín. 8 chars, 1 mayúscula, 1 número)",
        min_length=8,
        max_length=128,
        example="NewSecurePassword456!",
    )
