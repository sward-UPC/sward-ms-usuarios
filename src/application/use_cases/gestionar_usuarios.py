from uuid import UUID

from src.domain.entities.rol import TipoRol
from src.domain.entities.usuario import Usuario
from src.domain.ports.out_.cache_port import CachePort
from src.domain.ports.out_.rol_repository_port import RolRepositoryPort
from src.domain.ports.out_.usuario_repository_port import UsuarioRepositoryPort
from src.domain.value_objects.estado_usuario import EstadoUsuario


class UsuarioNoEncontradoError(Exception):
    pass


class RolNoEncontradoError(Exception):
    pass


class EstadoInvalidoError(Exception):
    pass


# Estados que un administrador puede asignar manualmente (excluye el transitorio
# PENDIENTE_VERIFICACION, que solo gestiona el flujo de registro/verificación).
_ESTADOS_ADMIN = {EstadoUsuario.ACTIVO, EstadoUsuario.INACTIVO, EstadoUsuario.BLOQUEADO}


class GestionarUsuariosUseCase:
    """Casos de uso administrativos sobre usuarios: consulta, listado,
    cambio de estado y asignación de roles. Orquesta los puertos de dominio
    sin conocer la infraestructura concreta."""

    def __init__(
        self,
        usuario_repo: UsuarioRepositoryPort,
        rol_repo: RolRepositoryPort,
        cache: CachePort,
    ):
        self._usuario_repo = usuario_repo
        self._rol_repo = rol_repo
        self._cache = cache

    async def listar(self, offset: int = 0, limit: int = 20) -> tuple[list[Usuario], int]:
        return await self._usuario_repo.find_all(offset=offset, limit=limit)

    async def consultar(self, user_id: UUID) -> Usuario:
        usuario = await self._usuario_repo.find_by_id(user_id)
        if not usuario:
            raise UsuarioNoEncontradoError("Usuario no encontrado.")
        return usuario

    async def cambiar_estado(self, user_id: UUID, estado: str) -> Usuario:
        try:
            nuevo_estado = EstadoUsuario(estado)
        except ValueError as e:
            raise EstadoInvalidoError(f"Estado inválido: {estado}") from e
        if nuevo_estado not in _ESTADOS_ADMIN:
            raise EstadoInvalidoError(f"Estado inválido: {estado}")

        usuario = await self._usuario_repo.find_by_id(user_id)
        if not usuario:
            raise UsuarioNoEncontradoError("Usuario no encontrado.")

        await self._usuario_repo.update_estado(user_id, nuevo_estado.value)
        await self._cache.invalidar_permisos(user_id)
        usuario.estado = nuevo_estado
        return usuario

    async def asignar_rol(self, user_id: UUID, rol: TipoRol) -> None:
        usuario = await self._usuario_repo.find_by_id(user_id)
        if not usuario:
            raise UsuarioNoEncontradoError("Usuario no encontrado.")

        rol_entity = await self._rol_repo.find_by_nombre(rol)
        if not rol_entity:
            raise RolNoEncontradoError("Rol no encontrado.")

        await self._rol_repo.assign_rol(user_id, rol_entity.id)
        await self._cache.invalidar_permisos(user_id)
