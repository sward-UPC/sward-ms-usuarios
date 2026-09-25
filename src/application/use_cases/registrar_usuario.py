from dataclasses import dataclass
from datetime import datetime, timezone

from sward_shared.identidad import id_sward_desde_moodle

from src.application.ports.out_.event_publisher_port import EventPublisherPort
from src.application.ports.out_.lms_client_port import LmsClientPort
from src.application.ports.out_.password_hasher_port import PasswordHasherPort
from src.application.ports.out_.rol_repository_port import RolRepositoryPort
from src.application.ports.out_.usuario_repository_port import UsuarioRepositoryPort
from src.domain.entities.rol import TipoRol
from src.domain.entities.usuario import Usuario
from src.domain.events.usuario_registrado_event import UsuarioRegistradoEvent
from src.domain.value_objects.estado_usuario import EstadoUsuario
from src.domain.value_objects.politica_contrasena import validar_contrasena


# Versión del texto de consentimiento que el registro exige aceptar. Se guarda
# junto a la aceptación: si el texto cambia, hay que poder saber cuál aceptó cada
# participante, y eso es lo que pide la Ley 29733 para acreditar el consentimiento.
CONSENTIMIENTO_VERSION_VIGENTE = "2026-09-24"


@dataclass
class RegistrarUsuarioCommand:
    correo: str
    password: str
    nombres: str = ""
    apellidos: str = ""
    carrera: str = ""
    consentimiento_version: str | None = None


class CorreoYaRegistradoError(Exception):
    pass


class CorreoInvalidoError(Exception):
    pass


class CorreoNoEnMoodleError(Exception):
    pass


class ConsentimientoNoAceptadoError(Exception):
    """No se registra a nadie sin consentimiento informado vigente."""


class DatosDeAltaIncompletosError(Exception):
    """Falta el nombre o el apellido para dar de alta al participante en Moodle."""


class RegistrarUsuarioUseCase:
    def __init__(
        self,
        usuario_repo: UsuarioRepositoryPort,
        rol_repo: RolRepositoryPort,
        event_publisher: EventPublisherPort,
        lms_client: LmsClientPort,
        password_hasher: PasswordHasherPort,
    ):
        self._usuario_repo = usuario_repo
        self._rol_repo = rol_repo
        self._event_publisher = event_publisher
        self._lms_client = lms_client
        self._password_hasher = password_hasher

    async def execute(self, cmd: RegistrarUsuarioCommand) -> Usuario:
        correo = cmd.correo.lower().strip()

        # El consentimiento se comprueba antes que nada: si no está aceptado no se
        # crea ninguna cuenta ni se toca Moodle, de modo que no queda ningún dato
        # de la persona en ninguna parte.
        if cmd.consentimiento_version != CONSENTIMIENTO_VERSION_VIGENTE:
            raise ConsentimientoNoAceptadoError(
                "Debes aceptar el consentimiento informado vigente para registrarte."
            )

        datos_moodle = await self._lms_client.buscar_usuario_por_correo(correo)
        if datos_moodle is None:
            # Antes esto era un rechazo: las cuentas de Moodle las creaba un script
            # externo a partir de un formulario, y el sistema no podía incorporar a
            # nadie por sí mismo. Ahora el registro provisiona.
            if not cmd.nombres.strip() or not cmd.apellidos.strip():
                raise DatosDeAltaIncompletosError(
                    "Necesitamos tu nombre y tus apellidos para crear tu cuenta."
                )
            datos_moodle = await self._lms_client.provisionar_participante(
                correo, cmd.nombres.strip(), cmd.apellidos.strip()
            )

        rol_moodle = TipoRol(datos_moodle["rol"])
        moodle_user_id: int = datos_moodle["moodle_user_id"]
        nombre: str | None = datos_moodle.get("nombre")
        apellido: str | None = datos_moodle.get("apellido")

        usuario = Usuario(
            # UUID determinístico desde Moodle: coincide con el estudiante_id que
            # usa ms-trazabilidad, permitiendo cruzar datos entre servicios.
            id=id_sward_desde_moodle(moodle_user_id),
            correo_institucional=correo,
            nombre=nombre,
            apellido=apellido,
            moodle_user_id=moodle_user_id,
            carrera=cmd.carrera.strip() or None,
            consentimiento_version=cmd.consentimiento_version,
            consentimiento_aceptado_en=datetime.now(timezone.utc),
        )
        if not usuario.validar_correo():
            raise CorreoInvalidoError(f"Correo inválido: {cmd.correo}")
        if await self._usuario_repo.exists_by_correo(correo):
            raise CorreoYaRegistradoError("El correo ya se encuentra registrado. Intenta iniciar sesión.")

        validar_contrasena(cmd.password)

        usuario.password_hash = self._password_hasher.hash(cmd.password)
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
