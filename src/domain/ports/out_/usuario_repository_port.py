from abc import ABC, abstractmethod
from uuid import UUID

from src.domain.entities.usuario import Usuario


class UsuarioRepositoryPort(ABC):
    @abstractmethod
    async def find_by_correo(self, correo: str) -> Usuario | None: ...
    @abstractmethod
    async def find_by_id(self, id: UUID) -> Usuario | None: ...
    @abstractmethod
    async def save(self, usuario: Usuario) -> Usuario: ...
    @abstractmethod
    async def exists_by_correo(self, correo: str) -> bool: ...
    @abstractmethod
    async def find_all(
        self, offset: int = 0, limit: int = 20
    ) -> tuple[list[Usuario], int]: ...
    @abstractmethod
    async def update_estado(self, id: UUID, estado: str) -> None: ...
