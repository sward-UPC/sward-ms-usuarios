from functools import lru_cache

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.out_.email_port import EmailPort
from src.application.ports.out_.lms_client_port import LmsClientPort
from src.application.ports.out_.password_hasher_port import PasswordHasherPort
from src.application.use_cases.autenticar_usuario import AutenticacionConfig, AutenticarUsuarioUseCase
from src.application.use_cases.gestionar_notificaciones import GestionarNotificacionesUseCase
from src.application.use_cases.gestionar_usuarios import GestionarUsuariosUseCase
from src.application.use_cases.recuperar_contrasena import RecuperacionConfig, RecuperarContrasenaUseCase
from src.application.use_cases.registrar_usuario import RegistrarUsuarioUseCase
from src.infrastructure.adapters.out_.consola_email_adapter import ConsolaEmailAdapter
from src.infrastructure.adapters.out_.eventbridge_adapter import EventBridgeAdapter
from src.infrastructure.adapters.out_.jwt_adapter import JwtAdapter
from src.infrastructure.adapters.out_.lms_client_adapter import LmsClientAdapter
from src.infrastructure.adapters.out_.mock_lms_client_adapter import MockLmsClientAdapter
from src.infrastructure.adapters.out_.notificacion_postgres_adapter import NotificacionPostgresAdapter
from src.infrastructure.adapters.out_.passlib_password_hasher_adapter import PasslibPasswordHasher
from src.infrastructure.adapters.out_.redis_adapter import RedisAdapter
from src.infrastructure.adapters.out_.redis_recuperacion_adapter import RedisRecuperacionAdapter
from src.infrastructure.adapters.out_.rol_postgres_adapter import RolPostgresAdapter
from src.infrastructure.adapters.out_.sin_correo_adapter import SinCorreoAdapter
from src.infrastructure.adapters.out_.smtp_email_adapter import SmtpEmailAdapter
from src.infrastructure.adapters.out_.usuario_postgres_adapter import UsuarioPostgresAdapter
from src.infrastructure.config.settings import settings
from src.infrastructure.db.database import get_session


@lru_cache(maxsize=1)
def get_jwt_adapter() -> JwtAdapter:
    return JwtAdapter()


@lru_cache(maxsize=1)
def get_password_hasher() -> PasswordHasherPort:
    return PasslibPasswordHasher()


@lru_cache(maxsize=1)
def get_redis_adapter() -> RedisAdapter:
    return RedisAdapter()


@lru_cache(maxsize=1)
def get_eventbridge_adapter() -> EventBridgeAdapter:
    return EventBridgeAdapter()


@lru_cache(maxsize=1)
def get_recuperacion_store() -> RedisRecuperacionAdapter:
    return RedisRecuperacionAdapter()


@lru_cache(maxsize=1)
def get_email() -> EmailPort:
    if settings.email_backend == "smtp":
        return SmtpEmailAdapter(
            host=settings.smtp_host,
            port=settings.smtp_port,
            usuario=settings.smtp_user,
            contrasena=settings.smtp_password,
            remitente=settings.email_remitente,
            starttls=settings.smtp_starttls,
            usar_ssl=settings.smtp_ssl,
        )
    if settings.email_backend == "consola" or settings.is_development:
        return ConsolaEmailAdapter()
    return SinCorreoAdapter()


@lru_cache(maxsize=1)
def get_lms_client() -> LmsClientPort:
    if settings.use_mock_lms:
        return MockLmsClientAdapter()
    return LmsClientAdapter()


def get_autenticar_usuario_uc(
    session: AsyncSession = Depends(get_session),
    jwt: JwtAdapter = Depends(get_jwt_adapter),
    cache: RedisAdapter = Depends(get_redis_adapter),
    events: EventBridgeAdapter = Depends(get_eventbridge_adapter),
    hasher: PasswordHasherPort = Depends(get_password_hasher),
) -> AutenticarUsuarioUseCase:
    return AutenticarUsuarioUseCase(
        usuario_repo=UsuarioPostgresAdapter(session),
        rol_repo=RolPostgresAdapter(session),
        token_port=jwt,
        cache=cache,
        event_publisher=events,
        password_hasher=hasher,
        config=AutenticacionConfig(
            max_login_attempts=settings.max_login_attempts,
            login_attempts_ttl=settings.login_attempts_ttl,
            permissions_cache_ttl=settings.permissions_cache_ttl,
            refresh_token_expire_days=settings.refresh_token_expire_days,
        ),
    )


def get_registrar_usuario_uc(
    session: AsyncSession = Depends(get_session),
    events: EventBridgeAdapter = Depends(get_eventbridge_adapter),
    lms: LmsClientPort = Depends(get_lms_client),
    hasher: PasswordHasherPort = Depends(get_password_hasher),
) -> RegistrarUsuarioUseCase:
    return RegistrarUsuarioUseCase(
        usuario_repo=UsuarioPostgresAdapter(session),
        rol_repo=RolPostgresAdapter(session),
        event_publisher=events,
        lms_client=lms,
        password_hasher=hasher,
    )


def get_gestionar_usuarios_uc(
    session: AsyncSession = Depends(get_session),
    cache: RedisAdapter = Depends(get_redis_adapter),
    hasher: PasswordHasherPort = Depends(get_password_hasher),
) -> GestionarUsuariosUseCase:
    return GestionarUsuariosUseCase(
        usuario_repo=UsuarioPostgresAdapter(session),
        rol_repo=RolPostgresAdapter(session),
        cache=cache,
        password_hasher=hasher,
    )


def get_gestionar_notificaciones_uc(
    session: AsyncSession = Depends(get_session),
) -> GestionarNotificacionesUseCase:
    return GestionarNotificacionesUseCase(NotificacionPostgresAdapter(session))


def get_recuperar_contrasena_uc(
    session: AsyncSession = Depends(get_session),
    codigos: RedisRecuperacionAdapter = Depends(get_recuperacion_store),
    cache: RedisAdapter = Depends(get_redis_adapter),
    email: EmailPort = Depends(get_email),
    hasher: PasswordHasherPort = Depends(get_password_hasher),
) -> RecuperarContrasenaUseCase:
    return RecuperarContrasenaUseCase(
        usuario_repo=UsuarioPostgresAdapter(session),
        codigos=codigos,
        cache=cache,
        email=email,
        password_hasher=hasher,
        config=RecuperacionConfig(
            codigo_ttl=settings.recuperacion_codigo_ttl,
            max_intentos=settings.recuperacion_max_intentos,
            espera_reenvio=settings.recuperacion_espera_reenvio,
            max_envios_por_hora=settings.recuperacion_max_envios_hora,
            secreto=settings.secret_key,
        ),
    )
