from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from src.application.use_cases.autenticar_usuario import (
    AutenticacionError,
    AutenticarUsuarioCommand,
    AutenticarUsuarioUseCase,
    CuentaBloqueadaError,
)
from src.application.use_cases.registrar_usuario import (
    CorreoInvalidoError,
    CorreoYaRegistradoError,
    RegistrarUsuarioCommand,
    RegistrarUsuarioUseCase,
)
from src.domain.entities.rol import TipoRol
from src.infrastructure.adapters.in_.middleware import get_current_user
from src.infrastructure.adapters.out_.redis_adapter import RedisAdapter
from src.infrastructure.dependencies import (
    get_autenticar_usuario_uc,
    get_redis_adapter,
    get_registrar_usuario_uc,
)

router = APIRouter(prefix="/auth", tags=["Autenticación"])


class RegisterRequest(BaseModel):
    """Solicitud para registrar un nuevo usuario."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "correo": "estudiante@sward.test",
                "password": "SecurePassword123!",
            }
        },
    )

    correo: EmailStr = Field(
        ...,
        description="Correo institucional (debe ser único)",
        example="estudiante@sward.test",
    )
    password: str = Field(
        ...,
        description="Contraseña (8-128 caracteres)",
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


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=UsuarioRegistradoResponse,
    responses={
        201: {
            "description": "Usuario registrado exitosamente",
        },
        409: {
            "description": "Correo ya registrado",
            "content": {"application/json": {"example": {"detail": "El correo ya está registrado"}}},
        },
        422: {
            "description": "Parámetros inválidos",
            "content": {"application/json": {"example": {"detail": "Correo inválido o contraseña muy corta"}}},
        },
    },
)
async def register(
    body: RegisterRequest = Body(...),
    uc: RegistrarUsuarioUseCase = Depends(get_registrar_usuario_uc),
):
    """Registra un nuevo usuario en el sistema.

    **Flujo:**
    1. Valida correo (formato, unicidad) y contraseña (min 8 chars)
    2. Hashea la contraseña con bcrypt
    3. Crea usuario con rol ESTUDIANTE y estado PENDIENTE_VERIFICACION
    4. Retorna datos del usuario creado

    **Nota:** Solo registro público con rol fijo ESTUDIANTE.
    Asignación de docente/admin exclusiva del endpoint admin.

    **SLA:** <200ms | **Auth:** Público | **Campos requeridos:** correo, password
    """
    try:
        u = await uc.execute(
            RegistrarUsuarioCommand(
                correo=body.correo,
                password=body.password,
                rol=TipoRol.ESTUDIANTE,
            )
        )
        return UsuarioRegistradoResponse(id=str(u.id), correo=u.correo_institucional, estado=u.estado)
    except CorreoYaRegistradoError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except (CorreoInvalidoError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.post(
    "/login",
    response_model=TokenResponse,
    responses={
        200: {
            "description": "Autenticación exitosa",
        },
        401: {
            "description": "Credenciales inválidas",
            "content": {"application/json": {"example": {"detail": "Correo o contraseña incorrecto"}}},
        },
        423: {
            "description": "Cuenta bloqueada tras 5 intentos fallidos",
            "content": {"application/json": {"example": {"detail": "Cuenta bloqueada. Intenta en 15 minutos."}}},
        },
    },
)
async def login(
    body: LoginRequest = Body(...),
    uc: AutenticarUsuarioUseCase = Depends(get_autenticar_usuario_uc),
):
    """Autentica un usuario y retorna tokens JWT.

    **Flujo:**
    1. Busca usuario por correo y verifica contraseña (bcrypt)
    2. Valida estado (no BLOQUEADO, no INACTIVO)
    3. Si fallida: incrementa contador; tras 5, bloquea 15min
    4. Si exitosa: genera JWT (15 min) + refresh (7 días)
    5. Retorna tokens para uso inmediato

    **JWT incluye:** sub (UUID), rol, permisos, jti (ID único), exp, type

    **SLA:** <150ms | **Auth:** Público | **Rate Limit:** 5 intentos → 15min bloqueo
    """
    try:
        tp = await uc.execute(
            AutenticarUsuarioCommand(
                correo=body.correo,
                password=body.password,
                device_id=body.device_id,
            )
        )
        return TokenResponse(
            access_token=tp.access_token,
            refresh_token=tp.refresh_token,
            expires_in=tp.expires_in,
        )
    except CuentaBloqueadaError as e:
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail=str(e))
    except AutenticacionError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        204: {
            "description": "Logout exitoso",
        },
        401: {
            "description": "JWT inválido o ausente",
            "content": {"application/json": {"example": {"detail": "Not authenticated"}}},
        },
    },
)
async def logout(
    current_user: dict = Depends(get_current_user),
    cache: RedisAdapter = Depends(get_redis_adapter),
):
    """Invalida el JWT actual en el dispositivo.

    **Flujo:**
    1. Extrae jti del token actual
    2. Calcula tiempo restante hasta exp
    3. Blacklistea token en Redis
    4. Solo cierra este dispositivo; otros permanecen activos

    **SLA:** <50ms | **Auth:** JWT requerido | **Nota:** Logout selectivo por dispositivo
    """
    exp = current_user.get("exp", 0)
    remaining = max(0, exp - int(datetime.now(timezone.utc).timestamp()))
    await cache.blacklist_token(current_user["jti"], remaining)


@router.post(
    "/logout-all-devices",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        204: {
            "description": "Logout en todos los dispositivos",
        },
        401: {
            "description": "JWT inválido o ausente",
            "content": {"application/json": {"example": {"detail": "Not authenticated"}}},
        },
    },
)
async def logout_all(
    current_user: dict = Depends(get_current_user),
    cache: RedisAdapter = Depends(get_redis_adapter),
):
    """Invalida todos los refresh tokens en todos los dispositivos.

    **Flujo:**
    1. Extrae UUID del usuario
    2. Borra TODOS los refresh tokens en Redis
    3. Blacklistea access token actual
    4. Cierra sesión irreversible en todos los dispositivos
    5. Debe hacer login nuevamente para acceder

    **SLA:** <100ms | **Auth:** JWT requerido | **Uso:** cambios de contraseña/seguridad
    """
    await cache.invalidar_todos_refresh_tokens(UUID(current_user["sub"]))
    exp = current_user.get("exp", 0)
    remaining = max(0, exp - int(datetime.now(timezone.utc).timestamp()))
    await cache.blacklist_token(current_user["jti"], remaining)
