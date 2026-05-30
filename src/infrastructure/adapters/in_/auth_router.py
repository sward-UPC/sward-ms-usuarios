from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr

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
    correo: EmailStr
    password: str


class LoginRequest(BaseModel):
    correo: EmailStr
    password: str
    device_id: str = "default"


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    uc: RegistrarUsuarioUseCase = Depends(get_registrar_usuario_uc),
):
    try:
        # El registro público SIEMPRE crea un usuario con rol ESTUDIANTE.
        # La asignación de roles docente/administrador es exclusiva del
        # endpoint admin protegido con require_admin.
        u = await uc.execute(
            RegistrarUsuarioCommand(
                correo=body.correo,
                password=body.password,
                rol=TipoRol.ESTUDIANTE,
            )
        )
        return {"id": str(u.id), "correo": u.correo_institucional, "estado": u.estado}
    except CorreoYaRegistradoError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except (CorreoInvalidoError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    uc: AutenticarUsuarioUseCase = Depends(get_autenticar_usuario_uc),
):
    try:
        tp = await uc.execute(
            AutenticarUsuarioCommand(correo=body.correo, password=body.password, device_id=body.device_id)
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


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    current_user: dict = Depends(get_current_user),
    cache: RedisAdapter = Depends(get_redis_adapter),
):
    from datetime import datetime, timezone

    exp = current_user.get("exp", 0)
    remaining = max(0, exp - int(datetime.now(timezone.utc).timestamp()))
    await cache.blacklist_token(current_user["jti"], remaining)


@router.post("/logout-all-devices", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(
    current_user: dict = Depends(get_current_user),
    cache: RedisAdapter = Depends(get_redis_adapter),
):
    from datetime import datetime, timezone
    from uuid import UUID

    await cache.invalidar_todos_refresh_tokens(UUID(current_user["sub"]))
    exp = current_user.get("exp", 0)
    remaining = max(0, exp - int(datetime.now(timezone.utc).timestamp()))
    await cache.blacklist_token(current_user["jti"], remaining)
