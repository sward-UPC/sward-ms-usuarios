from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
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
from src.infrastructure.adapters.out_.eventbridge_adapter import EventBridgeAdapter
from src.infrastructure.adapters.out_.jwt_adapter import JwtAdapter
from src.infrastructure.adapters.out_.redis_adapter import RedisAdapter
from src.infrastructure.adapters.out_.rol_postgres_adapter import RolPostgresAdapter
from src.infrastructure.adapters.out_.usuario_postgres_adapter import (
    UsuarioPostgresAdapter,
)
from src.infrastructure.db.database import get_session

router = APIRouter(prefix="/auth", tags=["Autenticación"])


class RegisterRequest(BaseModel):
    correo: EmailStr
    password: str
    rol: TipoRol = TipoRol.ESTUDIANTE


class LoginRequest(BaseModel):
    correo: EmailStr
    password: str
    device_id: str = "default"


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


@router.post("/register", status_code=201)
async def register(body: RegisterRequest, session: AsyncSession = Depends(get_session)):
    uc = RegistrarUsuarioUseCase(
        UsuarioPostgresAdapter(session),
        RolPostgresAdapter(session),
        EventBridgeAdapter(),
    )
    try:
        u = await uc.execute(
            RegistrarUsuarioCommand(
                correo=body.correo, password=body.password, rol=body.rol
            )
        )
        return {"id": str(u.id), "correo": u.correo_institucional, "estado": u.estado}
    except CorreoYaRegistradoError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except (CorreoInvalidoError, ValueError) as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)):
    uc = AutenticarUsuarioUseCase(
        UsuarioPostgresAdapter(session),
        RolPostgresAdapter(session),
        JwtAdapter(),
        RedisAdapter(),
        EventBridgeAdapter(),
    )
    try:
        tp = await uc.execute(
            AutenticarUsuarioCommand(
                correo=body.correo, password=body.password, device_id=body.device_id
            )
        )
        return TokenResponse(
            access_token=tp.access_token,
            refresh_token=tp.refresh_token,
            expires_in=tp.expires_in,
        )
    except CuentaBloqueadaError as e:
        raise HTTPException(status_code=423, detail=str(e))
    except AutenticacionError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.post("/logout", status_code=204)
async def logout(current_user: dict = Depends(get_current_user)):
    from datetime import datetime, timezone

    exp = current_user.get("exp", 0)
    remaining = max(0, exp - int(datetime.now(timezone.utc).timestamp()))
    await RedisAdapter().blacklist_token(current_user["jti"], remaining)


@router.post("/logout-all-devices", status_code=204)
async def logout_all(current_user: dict = Depends(get_current_user)):
    from uuid import UUID
    from datetime import datetime, timezone

    cache = RedisAdapter()
    await cache.invalidar_todos_refresh_tokens(UUID(current_user["sub"]))
    exp = current_user.get("exp", 0)
    remaining = max(0, exp - int(datetime.now(timezone.utc).timestamp()))
    await cache.blacklist_token(current_user["jti"], remaining)
