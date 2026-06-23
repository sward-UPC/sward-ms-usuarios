from abc import ABC, abstractmethod
from uuid import UUID

from src.domain.entities.rol import Rol, TipoRol


class RolRepositoryPort(ABC):
    @abstractmethod
    async def find_by_nombre(self, nombre: TipoRol) -> Rol | None: ...
    @abstractmethod
    async def find_by_usuario_id(self, usuario_id: UUID) -> list[Rol]: ...
    @abstractmethod
    async def assign_rol(self, usuario_id: UUID, rol_id: UUID) -> None: ...
    @abstractmethod
    async def revoke_rol(self, usuario_id: UUID, rol_id: UUID) -> None: ...
    @abstractmethod
    async def find_all(self) -> list[Rol]: ...
