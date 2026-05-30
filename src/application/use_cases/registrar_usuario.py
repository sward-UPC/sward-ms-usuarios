from dataclasses import dataclass

from src.domain.entities.rol import TipoRol
from src.domain.entities.usuario import Usuario
from src.domain.events.usuario_registrado_event import UsuarioRegistradoEvent
from src.domain.ports.out_.event_publisher_port import EventPublisherPort
from src.domain.ports.out_.rol_repository_port import RolRepositoryPort
from src.domain.ports.out_.usuario_repository_port import UsuarioRepositoryPort
from src.domain.value_objects.estado_usuario import EstadoUsuario


@dataclass
class RegistrarUsuarioCommand:
    correo: str
    password: str
    rol: TipoRol = TipoRol.ESTUDIANTE


class CorreoYaRegistradoError(Exception):
    pass


class CorreoInvalidoError(Exception):
    pass


def _validar_password(password: str) -> None:
    errores = []
    if len(password) < 8:
        errores.append("mínimo 8 caracteres")
    if not any(c.isupper() for c in password):
        errores.append("al menos una mayúscula")
    if not any(c.isdigit() for c in password):
        errores.append("al menos un número")
    if errores:
        raise ValueError(f"Contraseña insegura: {', '.join(errores)}")


class RegistrarUsuarioUseCase:
    def __init__(
        self,
        usuario_repo: UsuarioRepositoryPort,
        rol_repo: RolRepositoryPort,
        event_publisher: EventPublisherPort,
    ):
        self._usuario_repo = usuario_repo
        self._rol_repo = rol_repo
        self._event_publisher = event_publisher

    async def execute(self, command: RegistrarUsuarioCommand) -> Usuario:
        from passlib.context import CryptContext

        pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

        usuario = Usuario(correo_institucional=command.correo.lower().strip())
        if not usuario.validar_correo():
            raise CorreoInvalidoError(f"Correo inválido: {command.correo}")
        if await self._usuario_repo.exists_by_correo(command.correo.lower()):
            raise CorreoYaRegistradoError(
                "El correo ya se encuentra registrado. Intente iniciar sesión."
            )

        _validar_password(command.password)

        usuario.password_hash = pwd_ctx.hash(command.password)
        usuario.estado = EstadoUsuario.ACTIVO
        guardado = await self._usuario_repo.save(usuario)

        rol = await self._rol_repo.find_by_nombre(command.rol)
        if rol:
            await self._rol_repo.assign_rol(guardado.id, rol.id)

        self._event_publisher.publish(
            UsuarioRegistradoEvent(
                usuario_id=guardado.id,
                correo=guardado.correo_institucional,
                rol=str(command.rol),
            )
        )
        return guardado
