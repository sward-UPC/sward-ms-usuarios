from dataclasses import dataclass

from passlib.context import CryptContext

from src.domain.entities.rol import TipoRol
from src.domain.entities.usuario import Usuario
from src.domain.events.usuario_registrado_event import UsuarioRegistradoEvent
from src.domain.ports.out_.event_publisher_port import EventPublisherPort
from src.domain.ports.out_.lms_client_port import LmsClientPort
from src.domain.ports.out_.rol_repository_port import RolRepositoryPort
from src.domain.ports.out_.usuario_repository_port import UsuarioRepositoryPort
from src.domain.value_objects.estado_usuario import EstadoUsuario

pwd_ctx = CryptContext(schemes=["argon2", "bcrypt"], deprecated="auto")


@dataclass
class RegistrarUsuarioCommand:
    correo: str
    password: str


class CorreoYaRegistradoError(Exception):
    pass


class CorreoInvalidoError(Exception):
    pass


class CorreoNoEnMoodleError(Exception):
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
        lms_client: LmsClientPort,
    ):
        self._usuario_repo = usuario_repo
        self._rol_repo = rol_repo
        self._event_publisher = event_publisher
        self._lms_client = lms_client

    async def execute(self, command: RegistrarUsuarioCommand) -> Usuario:
        correo = command.correo.lower().strip()

        datos_moodle = await self._lms_client.buscar_usuario_por_correo(correo)
        if datos_moodle is None:
            raise CorreoNoEnMoodleError(
                "Correo no registrado en la plataforma educativa. "
                "Usa el correo institucional con el que accedes a Moodle."
            )

        rol_moodle = TipoRol(datos_moodle["rol"])
        moodle_user_id: int = datos_moodle["moodle_user_id"]
        nombre: str | None = datos_moodle.get("nombre")
        apellido: str | None = datos_moodle.get("apellido")

        usuario = Usuario(
            correo_institucional=correo,
            nombre=nombre,
            apellido=apellido,
            moodle_user_id=moodle_user_id,
        )
        if not usuario.validar_correo():
            raise CorreoInvalidoError(f"Correo inválido: {command.correo}")
        if await self._usuario_repo.exists_by_correo(correo):
            raise CorreoYaRegistradoError("El correo ya se encuentra registrado. Intenta iniciar sesión.")

        _validar_password(command.password)

        usuario.password_hash = pwd_ctx.hash(command.password)
        usuario.estado = EstadoUsuario.ACTIVO
        guardado = await self._usuario_repo.save(usuario)

        rol = await self._rol_repo.find_by_nombre(rol_moodle)
        if rol:
            await self._rol_repo.assign_rol(guardado.id, rol.id)

        self._event_publisher.publish(
            UsuarioRegistradoEvent(
                usuario_id=guardado.id,
                correo=guardado.correo_institucional,
                rol=str(rol_moodle),
            )
        )
        return guardado
