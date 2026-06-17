from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID


@dataclass
class TokenPair:
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 900


class TokenPort(ABC):
    @abstractmethod
    def generar_access_token(
        self,
        usuario_id: UUID,
        rol: str,
        permisos: list[str],
        nombre: str | None = None,
        moodle_user_id: int | None = None,
    ) -> str: ...
    @abstractmethod
    def generar_refresh_token(self, usuario_id: UUID, device_id: str) -> str: ...
    @abstractmethod
    def validar_access_token(self, token: str) -> dict: ...
    @abstractmethod
    def validar_refresh_token(self, token: str) -> dict: ...
    @abstractmethod
    def generar_par(
        self,
        usuario_id: UUID,
        rol: str,
        permisos: list[str],
        device_id: str,
        nombre: str | None = None,
        moodle_user_id: int | None = None,
    ) -> TokenPair: ...
