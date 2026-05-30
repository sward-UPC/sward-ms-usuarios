from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from jose import JWTError, jwt

from src.domain.ports.out_.token_port import TokenPair, TokenPort
from src.infrastructure.config.settings import settings


class JwtAdapter(TokenPort):
    def generar_access_token(
        self, usuario_id: UUID, rol: str, permisos: list[str]
    ) -> str:
        now = datetime.now(timezone.utc)
        return jwt.encode(
            {
                "sub": str(usuario_id),
                "rol": rol,
                "permisos": permisos,
                "jti": str(uuid4()),
                "iat": now,
                "type": "access",
                "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
            },
            settings.secret_key,
            algorithm=settings.jwt_algorithm,
        )

    def generar_refresh_token(self, usuario_id: UUID, device_id: str) -> str:
        now = datetime.now(timezone.utc)
        return jwt.encode(
            {
                "sub": str(usuario_id),
                "device_id": device_id,
                "jti": str(uuid4()),
                "iat": now,
                "type": "refresh",
                "exp": now + timedelta(days=settings.refresh_token_expire_days),
            },
            settings.secret_key,
            algorithm=settings.jwt_algorithm,
        )

    def validar_access_token(self, token: str) -> dict:
        try:
            payload = jwt.decode(
                token, settings.secret_key, algorithms=[settings.jwt_algorithm]
            )
            if payload.get("type") != "access":
                raise JWTError("Token type inválido")
            return payload
        except JWTError as e:
            raise ValueError(f"Token inválido: {e}") from e

    def generar_par(
        self, usuario_id: UUID, rol: str, permisos: list[str], device_id: str
    ) -> TokenPair:
        return TokenPair(
            access_token=self.generar_access_token(usuario_id, rol, permisos),
            refresh_token=self.generar_refresh_token(usuario_id, device_id),
            expires_in=settings.access_token_expire_minutes * 60,
        )
