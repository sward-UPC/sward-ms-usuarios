from datetime import datetime, timezone
from uuid import UUID

from passlib.context import CryptContext

from src.domain.entities.rol import TipoRol
from src.domain.entities.usuario import Usuario
from src.domain.ports.out_.cache_port import CachePort
from src.domain.ports.out_.rol_repository_port import RolRepositoryPort
from src.domain.ports.out_.usuario_repository_port import UsuarioRepositoryPort
from src.domain.value_objects.estado_usuario import EstadoUsuario

# Mismo contexto de hashing usado en autenticación (argon2 + bcrypt).
pwd_ctx = CryptContext(schemes=["argon2", "bcrypt"], deprecated="auto")


class UsuarioNoEncontradoError(Exception):
    pass


class PasswordActualInvalidaError(Exception):
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

    async def consultar_varios(self, ids: list[UUID]) -> list[Usuario]:
        """Consulta múltiples usuarios por UUID en una sola query (uso s2s).

        No lanza error si algún ID no existe: retorna solo los encontrados.
        """
        return await self._usuario_repo.find_by_ids(ids)

    async def actualizar_perfil(
        self,
        user_id: UUID,
        avatar_color: str | None = None,
        avatar_url: str | None = None,
    ) -> Usuario:
        """Actualiza únicamente los campos personalizables del perfil (avatar).

        Nombre, correo, institución y rol provienen de Moodle y son de solo
        lectura: nunca se modifican aquí.
        """
        usuario = await self._usuario_repo.find_by_id(user_id)
        if not usuario:
            raise UsuarioNoEncontradoError("Usuario no encontrado.")

        usuario.avatar_color = avatar_color
        usuario.avatar_url = avatar_url
        usuario.updated_at = datetime.now(timezone.utc)
        return await self._usuario_repo.save(usuario)

    async def actualizar_preferencias(self, user_id: UUID, notif_logros: bool) -> Usuario:
        """Actualiza las preferencias de notificación del usuario."""
        usuario = await self._usuario_repo.find_by_id(user_id)
        if not usuario:
            raise UsuarioNoEncontradoError("Usuario no encontrado.")
        usuario.notif_logros = notif_logros
        usuario.updated_at = datetime.now(timezone.utc)
        return await self._usuario_repo.save(usuario)

    async def cambiar_password(
        self,
        user_id: UUID,
        password_actual: str,
        password_nueva: str,
    ) -> None:
        """Cambia la contraseña verificando la actual contra el hash almacenado.

        Tras el cambio se invalidan todos los refresh tokens del usuario para
        forzar un nuevo inicio de sesión en todos los dispositivos.
        """
        usuario = await self._usuario_repo.find_by_id(user_id)
        if not usuario:
            raise UsuarioNoEncontradoError("Usuario no encontrado.")

        if not pwd_ctx.verify(password_actual, usuario.password_hash):
            raise PasswordActualInvalidaError("La contraseña actual es incorrecta.")

        usuario.password_hash = pwd_ctx.hash(password_nueva)
        usuario.updated_at = datetime.now(timezone.utc)
        await self._usuario_repo.save(usuario)
        await self._cache.invalidar_todos_refresh_tokens(user_id)

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

    async def eliminar_cuenta(self, user_id: UUID) -> None:
        """Elimina la cuenta del propio usuario (soft-delete): la desactiva y
        revoca sus sesiones para que pierda el acceso de inmediato."""
        usuario = await self._usuario_repo.find_by_id(user_id)
        if not usuario:
            raise UsuarioNoEncontradoError("Usuario no encontrado.")
        await self._usuario_repo.update_estado(user_id, EstadoUsuario.INACTIVO.value)
        await self._cache.invalidar_todos_refresh_tokens(user_id)
        await self._cache.invalidar_permisos(user_id)

    async def listar_roles(self, user_id: UUID):
        return await self._rol_repo.find_by_usuario_id(user_id)

    async def listar_con_roles(self, offset: int = 0, limit: int = 20) -> tuple[list[tuple], int]:
        """Retorna (usuarios, total) donde cada usuario incluye su rol principal."""
        usuarios, total = await self._usuario_repo.find_all(offset=offset, limit=limit)
        result = []
        for u in usuarios:
            roles = await self._rol_repo.find_by_usuario_id(u.id)
            rol_principal = str(roles[0].nombre) if roles else "estudiante"
            result.append((u, rol_principal))
        return result, total

    async def asignar_rol(self, user_id: UUID, rol: TipoRol) -> None:
        usuario = await self._usuario_repo.find_by_id(user_id)
        if not usuario:
            raise UsuarioNoEncontradoError("Usuario no encontrado.")

        rol_entity = await self._rol_repo.find_by_nombre(rol)
        if not rol_entity:
            raise RolNoEncontradoError("Rol no encontrado.")

        await self._rol_repo.assign_rol(user_id, rol_entity.id)
        await self._cache.invalidar_permisos(user_id)
