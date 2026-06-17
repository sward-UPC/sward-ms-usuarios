from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import jwt
from jwt import PyJWTError

from src.domain.ports.out_.token_port import TokenPair, TokenPort
from src.infrastructure.config.settings import settings


class JwtAdapter(TokenPort):
    def generar_access_token(
        self,
        usuario_id: UUID,
        rol: str,
        permisos: list[str],
        nombre: str | None = None,
        moodle_user_id: int | None = None,
    ) -> str:
        now = datetime.now(timezone.utc)
        payload: dict = {
            "sub": str(usuario_id),
            "rol": rol,
            "permisos": permisos,
            "jti": str(uuid4()),
            "iat": now,
            "type": "access",
            "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
        }
        if nombre is not None:
            payload["nombre"] = nombre
        if moodle_user_id is not None:
            payload["moodle_user_id"] = moodle_user_id
        return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)

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

    def validar_refresh_token(self, token: str) -> dict:
        try:
            payload = jwt.decode(
                token,
                settings.secret_key,
                algorithms=["HS256"],
                options={"require": ["exp", "type"]},
            )
            if payload.get("type") != "refresh":
                raise PyJWTError("Token type inválido")
            return payload
        except PyJWTError as e:
            raise ValueError(f"Refresh token inválido: {e}") from e

    def validar_access_token(self, token: str) -> dict:
        try:
            payload = jwt.decode(
                token,
                settings.secret_key,
                algorithms=["HS256"],
                options={"require": ["exp", "type"]},
            )
            if payload.get("type") != "access":
                raise PyJWTError("Token type inválido")
            return payload
        except PyJWTError as e:
            raise ValueError(f"Token inválido: {e}") from e

    def generar_par(
        self,
        usuario_id: UUID,
        rol: str,
        permisos: list[str],
        device_id: str,
        nombre: str | None = None,
        moodle_user_id: int | None = None,
    ) -> TokenPair:
        return TokenPair(
            access_token=self.generar_access_token(usuario_id, rol, permisos, nombre, moodle_user_id),
            refresh_token=self.generar_refresh_token(usuario_id, device_id),
            expires_in=settings.access_token_expire_minutes * 60,
        )
