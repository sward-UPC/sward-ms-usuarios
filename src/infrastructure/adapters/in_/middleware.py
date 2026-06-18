from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.infrastructure.adapters.out_.jwt_adapter import JwtAdapter
from src.infrastructure.adapters.out_.redis_adapter import RedisAdapter
from src.infrastructure.config.settings import settings
from src.infrastructure.dependencies import get_jwt_adapter, get_redis_adapter

security = HTTPBearer()


async def require_service_key(x_service_key: str = Header(default="")) -> None:
    """Autoriza llamadas service-to-service (s2s) vía header X-Service-Key.

    Valida contra el conjunto de claves autorizadas. Usado por endpoints
    /internal consumidos por otros microservicios (p.ej. ms-trazabilidad).
    """
    if not x_service_key or x_service_key not in settings.authorized_service_keys_set:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Service key inválida.")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    jwt: JwtAdapter = Depends(get_jwt_adapter),
    cache: RedisAdapter = Depends(get_redis_adapter),
) -> dict:
    try:
        payload = jwt.validar_access_token(credentials.credentials)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    if await cache.is_token_blacklisted(payload["jti"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token revocado.")
    return payload


async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("rol") != "administrador":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso denegado.")
    return current_user
