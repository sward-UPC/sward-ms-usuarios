import hashlib
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
from src.application.use_cases.gestionar_usuarios import (
    GestionarUsuariosUseCase,
    PasswordActualInvalidaError,
    UsuarioNoEncontradoError,
)
from src.application.use_cases.registrar_usuario import (
    CorreoInvalidoError,
    CorreoNoEnMoodleError,
    CorreoYaRegistradoError,
    RegistrarUsuarioCommand,
    RegistrarUsuarioUseCase,
)
from src.infrastructure.adapters.in_.middleware import get_current_user
from src.infrastructure.adapters.out_.jwt_adapter import JwtAdapter
from src.infrastructure.adapters.out_.redis_adapter import RedisAdapter
from src.infrastructure.config.settings import settings
from src.infrastructure.dependencies import (
    get_autenticar_usuario_uc,
    get_gestionar_usuarios_uc,
    get_jwt_adapter,
    get_redis_adapter,
    get_registrar_usuario_uc,
)

router = APIRouter(prefix="/auth", tags=["Autenticación"])


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
    """Registra un nuevo usuario verificando su identidad en Moodle.

    **Flujo:**
    1. Busca el correo en Moodle via ms-integracion-lms
    2. Si no existe → 400 "Correo no registrado en la plataforma educativa"
    3. Asigna automáticamente el rol (estudiante/docente) detectado en Moodle
    4. Guarda nombre, apellido y moodle_user_id desde Moodle
    5. Retorna datos del usuario creado

    **SLA:** <300ms | **Auth:** Público | **Campos requeridos:** correo, password
    """
    try:
        u = await uc.execute(RegistrarUsuarioCommand(correo=body.correo, password=body.password))
        return UsuarioRegistradoResponse(id=str(u.id), correo=u.correo_institucional, estado=u.estado)
    except CorreoNoEnMoodleError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except CorreoYaRegistradoError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except (CorreoInvalidoError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))


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


class RefreshRequest(BaseModel):
    """Solicitud para refrescar el access token."""

    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(..., description="JWT de refresco obtenido en el login")


class AccessTokenResponse(BaseModel):
    """Nuevo access token tras refresco exitoso."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int


@router.post(
    "/refresh",
    response_model=AccessTokenResponse,
    responses={
        200: {"description": "Nuevo access token emitido"},
        401: {"description": "Refresh token inválido, expirado o revocado"},
    },
)
async def refresh(
    body: RefreshRequest = Body(...),
    jwt: JwtAdapter = Depends(get_jwt_adapter),
    cache: RedisAdapter = Depends(get_redis_adapter),
    uc: GestionarUsuariosUseCase = Depends(get_gestionar_usuarios_uc),
):
    """Emite un nuevo access token usando el refresh token.

    **Flujo:**
    1. Valida y decodifica el refresh token
    2. Verifica que no esté revocado (Redis blacklist)
    3. Verifica hash almacenado en Redis contra el token recibido
    4. Obtiene rol/permisos actuales del usuario desde DB
    5. Emite nuevo access token

    **SLA:** <100ms | **Auth:** Refresh token en body
    """
    try:
        payload = jwt.validar_refresh_token(body.refresh_token)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    jti = payload.get("jti", "")
    if await cache.is_token_blacklisted(jti):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token revocado.")

    usuario_id = UUID(payload["sub"])
    device_id = payload.get("device_id", "default")
    stored_hash = await cache.get_refresh_token(usuario_id, device_id)
    token_hash = hashlib.sha256(body.refresh_token.encode()).hexdigest()
    if not stored_hash or stored_hash != token_hash:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token inválido.")

    try:
        usuario = await uc.consultar(usuario_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no encontrado.")

    roles = await uc.listar_roles(usuario_id)
    rol_principal = roles[0].nombre if roles else "estudiante"
    permisos = [p.codigo for r in roles for p in r.permisos]

    new_access = jwt.generar_access_token(
        usuario_id=usuario_id,
        rol=str(rol_principal),
        permisos=permisos,
        nombre=usuario.nombre,
        moodle_user_id=usuario.moodle_user_id,
    )
    return AccessTokenResponse(
        access_token=new_access,
        expires_in=settings.access_token_expire_minutes * 60,
    )


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


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        204: {"description": "Contraseña actualizada; sesiones invalidadas"},
        400: {
            "description": "La contraseña actual es incorrecta",
            "content": {"application/json": {"example": {"detail": "La contraseña actual es incorrecta."}}},
        },
        401: {"description": "JWT inválido o ausente"},
    },
)
async def change_password(
    body: ChangePasswordRequest = Body(...),
    current_user: dict = Depends(get_current_user),
    uc: GestionarUsuariosUseCase = Depends(get_gestionar_usuarios_uc),
    cache: RedisAdapter = Depends(get_redis_adapter),
):
    """Cambia la contraseña del usuario autenticado.

    **Flujo:**
    1. Verifica la contraseña actual contra el hash almacenado
    2. Rehashea y persiste la nueva contraseña
    3. Invalida todos los refresh tokens (logout en todos los dispositivos)
    4. Blacklistea el access token actual

    **Auth:** JWT requerido
    """
    if body.password_nueva == body.password_actual:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La nueva contraseña debe ser distinta de la actual.",
        )
    try:
        await uc.cambiar_password(
            UUID(current_user["sub"]),
            password_actual=body.password_actual,
            password_nueva=body.password_nueva,
        )
    except PasswordActualInvalidaError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except UsuarioNoEncontradoError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    exp = current_user.get("exp", 0)
    remaining = max(0, exp - int(datetime.now(timezone.utc).timestamp()))
    await cache.blacklist_token(current_user["jti"], remaining)
