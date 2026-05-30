from functools import lru_cache

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.use_cases.autenticar_usuario import AutenticarUsuarioUseCase
from src.application.use_cases.registrar_usuario import RegistrarUsuarioUseCase
from src.infrastructure.adapters.out_.eventbridge_adapter import EventBridgeAdapter
from src.infrastructure.adapters.out_.jwt_adapter import JwtAdapter
from src.infrastructure.adapters.out_.redis_adapter import RedisAdapter
from src.infrastructure.adapters.out_.rol_postgres_adapter import RolPostgresAdapter
from src.infrastructure.adapters.out_.usuario_postgres_adapter import UsuarioPostgresAdapter
from src.infrastructure.db.database import get_session


@lru_cache(maxsize=1)
def get_jwt_adapter() -> JwtAdapter:
    return JwtAdapter()


@lru_cache(maxsize=1)
def get_redis_adapter() -> RedisAdapter:
    return RedisAdapter()


@lru_cache(maxsize=1)
def get_eventbridge_adapter() -> EventBridgeAdapter:
    return EventBridgeAdapter()


def get_autenticar_usuario_uc(
    session: AsyncSession = Depends(get_session),
    jwt: JwtAdapter = Depends(get_jwt_adapter),
    cache: RedisAdapter = Depends(get_redis_adapter),
    events: EventBridgeAdapter = Depends(get_eventbridge_adapter),
) -> AutenticarUsuarioUseCase:
    return AutenticarUsuarioUseCase(
        usuario_repo=UsuarioPostgresAdapter(session),
        rol_repo=RolPostgresAdapter(session),
        token_port=jwt,
        cache=cache,
        event_publisher=events,
    )


def get_registrar_usuario_uc(
    session: AsyncSession = Depends(get_session),
    events: EventBridgeAdapter = Depends(get_eventbridge_adapter),
) -> RegistrarUsuarioUseCase:
    return RegistrarUsuarioUseCase(
        usuario_repo=UsuarioPostgresAdapter(session),
        rol_repo=RolPostgresAdapter(session),
        event_publisher=events,
    )
