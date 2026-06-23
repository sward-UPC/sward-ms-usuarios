import hashlib
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, status

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
from src.infrastructure.adapters.in_.schemas import (
    AccessTokenResponse,
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UsuarioRegistradoResponse,
)
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
