from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from src.infrastructure.adapters.out_.jwt_adapter import JwtAdapter
from src.infrastructure.adapters.out_.redis_adapter import RedisAdapter

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    try:
        payload = JwtAdapter().validar_access_token(credentials.credentials)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    if await RedisAdapter().is_token_blacklisted(payload["jti"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token revocado."
        )
    return payload


async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("rol") != "administrador":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Acceso denegado."
        )
    return current_user
