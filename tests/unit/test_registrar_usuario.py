from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.ports.out_.email_port import EnvioCorreoError
from src.application.ports.out_.lms_client_port import LmsClientPort
from src.application.use_cases.registrar_usuario import (
    CONSENTIMIENTO_VERSION_VIGENTE,
    ConsentimientoNoAceptadoError,
    CorreoYaRegistradoError,
    DatosDeAltaIncompletosError,
    RegistrarUsuarioCommand,
    RegistrarUsuarioUseCase,
)
from src.infrastructure.adapters.out_.passlib_password_hasher_adapter import PasslibPasswordHasher

_HASHER = PasslibPasswordHasher()

MOODLE_ESTUDIANTE = {
    "moodle_user_id": 7,
    "nombre": "Test",
    "apellido": "User",
    "correo": "nuevo@upc.edu.pe",
    "rol": "estudiante",
}


def comando(**extra) -> RegistrarUsuarioCommand:
    """Comando válido por defecto; los casos cambian sólo lo que están probando."""
    datos = {
        "correo": "nuevo@upc.edu.pe",
        "password": "SecurePass1",
        "nombres": "Test",
        "apellidos": "User",
        "consentimiento_version": CONSENTIMIENTO_VERSION_VIGENTE,
    }
    datos.update(extra)
    return RegistrarUsuarioCommand(**datos)


class FakeLmsClient(LmsClientPort):
    """LMS de mentira. Registra si le pidieron provisionar y con qué datos."""

    def __init__(self, respuesta: dict | None):
        self._respuesta = respuesta
        self.provisiones: list[tuple[str, str, str, str]] = []
        self.cambios: list[tuple[str, str]] = []

    async def buscar_usuario_por_correo(self, correo: str) -> dict | None:
        return self._respuesta

    async def cambiar_password(self, correo: str, password: str) -> bool:
        self.cambios.append((correo, password))
        return True

    async def provisionar_participante(self, correo, nombres, apellidos, password) -> dict:
        # Se guarda también la contraseña para poder comprobar que el registro la
        # manda: sin ella Moodle generaría una temporal y el participante acabaría
        # con tres contraseñas, que es justo lo que se corrigió el 27 de septiembre.
        self.provisiones.append((correo, nombres, apellidos, password))
        return {
            "moodle_user_id": 99,
            "nombre": nombres,
            "apellido": apellidos,
            "correo": correo,
            "rol": "estudiante",
        }


class FakeEmail:
    """Correo de mentira. `falla` simula un servidor de salida caído."""

    disponible = True

    def __init__(self, falla: bool = False):
        self.enviados: list[tuple[str, str, str]] = []
        self._falla = falla

    async def enviar(self, destinatario: str, asunto: str, cuerpo: str) -> None:
        if self._falla:
            raise EnvioCorreoError("servidor de salida caído")
        self.enviados.append((destinatario, asunto, cuerpo))


def _use_case(lms: FakeLmsClient, email: FakeEmail | None = None) -> RegistrarUsuarioUseCase:
    repo = AsyncMock()
    repo.exists_by_correo.return_value = False
    repo.save.side_effect = lambda u: u
    rol_repo = AsyncMock()
    rol_repo.find_by_nombre.return_value = None
    return RegistrarUsuarioUseCase(
        repo,
        rol_repo,
        MagicMock(),
        lms,
        _HASHER,
        email=email,
        aula_virtual_url="https://aula.example/",
        sward_app_url="https://app.example/",
    )


@pytest.fixture
def use_case():
    return _use_case(FakeLmsClient(MOODLE_ESTUDIANTE))


@pytest.mark.asyncio
async def test_registro_exitoso(use_case):
    u = await use_case.execute(comando())
    assert u.correo_institucional == "nuevo@upc.edu.pe"
    assert u.nombre == "Test"
    assert u.moodle_user_id == 7


@pytest.mark.asyncio
async def test_id_determinístico_desde_moodle(use_case):
    """El UUID del usuario se deriva de moodle_user_id (coincide con trazabilidad)."""
    from sward_shared.identidad import id_sward_desde_moodle

    u = await use_case.execute(comando())
    assert u.id == id_sward_desde_moodle(7)


@pytest.mark.asyncio
async def test_correo_duplicado(use_case):
    use_case._usuario_repo.exists_by_correo.return_value = True
    with pytest.raises(CorreoYaRegistradoError):
        await use_case.execute(comando(correo="existe@upc.edu.pe"))


@pytest.mark.asyncio
async def test_password_debil(use_case):
    with pytest.raises(ValueError):
        await use_case.execute(comando(password="1234"))


# --------------------------------------------------------------- alta en Moodle
# Antes del 24-sep-2026, un correo que no existiera en Moodle se rechazaba: las
# cuentas las creaba un script externo alimentado por un formulario de Google.
# Ahora el registro da de alta al participante.


@pytest.mark.asyncio
async def test_da_de_alta_en_moodle_a_quien_no_existe():
    lms = FakeLmsClient(None)
    uc = _use_case(lms)

    u = await uc.execute(comando(correo="fantasma@upc.edu.pe", nombres="Ana", apellidos="Torres"))

    assert lms.provisiones == [("fantasma@upc.edu.pe", "Ana", "Torres", "SecurePass1")]
    assert u.moodle_user_id == 99
    assert u.nombre == "Ana"


@pytest.mark.asyncio
async def test_no_provisiona_a_quien_ya_esta_en_moodle(use_case):
    await use_case.execute(comando())
    assert use_case._lms_client.provisiones == []


@pytest.mark.asyncio
async def test_sin_nombre_no_se_puede_dar_de_alta():
    """Moodle exige nombre y apellido; sin ellos no se crea nada a medias."""
    uc = _use_case(FakeLmsClient(None))
    with pytest.raises(DatosDeAltaIncompletosError):
        await uc.execute(comando(correo="x@upc.edu.pe", nombres="", apellidos=""))


# ------------------------------------------------------------- consentimiento


@pytest.mark.asyncio
async def test_sin_consentimiento_no_hay_registro(use_case):
    with pytest.raises(ConsentimientoNoAceptadoError):
        await use_case.execute(comando(consentimiento_version=None))


@pytest.mark.asyncio
async def test_una_version_vieja_del_consentimiento_no_vale(use_case):
    with pytest.raises(ConsentimientoNoAceptadoError):
        await use_case.execute(comando(consentimiento_version="2026-01-01"))


@pytest.mark.asyncio
async def test_sin_consentimiento_no_se_toca_moodle():
    """Si no consintió, no debe quedar rastro suyo en ninguna parte."""
    lms = FakeLmsClient(None)
    uc = _use_case(lms)
    with pytest.raises(ConsentimientoNoAceptadoError):
        await uc.execute(comando(consentimiento_version=None))
    assert lms.provisiones == []


@pytest.mark.asyncio
async def test_queda_registrada_la_version_y_la_fecha(use_case):
    u = await use_case.execute(comando())
    assert u.consentimiento_version == CONSENTIMIENTO_VERSION_VIGENTE
    assert u.consentimiento_aceptado_en is not None


# ------------------------------------------------------------------ el docente
# El panel docente muestra la trazabilidad individual de los 30 estudiantes. Si
# alguien pudiera auto-registrarse como docente vería los datos de todos, así que
# el registro sólo puede crear estudiantes: la cuenta del profesor se da de alta
# aparte, y al registrarse el sistema lee su rol de Moodle y lo respeta.


@pytest.mark.asyncio
async def test_el_registro_nunca_crea_un_docente():
    """Quien no existe en Moodle se provisiona, y el alta es siempre de estudiante."""
    lms = FakeLmsClient(None)
    uc = _use_case(lms)

    u = await uc.execute(comando(correo="quiensea@upc.edu.pe"))

    # El puerto no recibe rol: no hay forma de pedir un alta de docente desde aquí.
    assert lms.provisiones == [("quiensea@upc.edu.pe", "Test", "User", "SecurePass1")]
    assert u.moodle_user_id == 99


@pytest.mark.asyncio
async def test_el_docente_dado_de_alta_aparte_conserva_su_rol():
    lms = FakeLmsClient(
        {
            "moodle_user_id": 2,
            "nombre": "Luis",
            "apellido": "Gómez",
            "correo": "profesor@upc.edu.pe",
            "rol": "docente",
        }
    )
    repo = AsyncMock()
    repo.exists_by_correo.return_value = False
    repo.save.side_effect = lambda u: u
    rol_repo = AsyncMock()
    rol_encontrado = MagicMock()
    rol_repo.find_by_nombre.return_value = rol_encontrado
    uc = RegistrarUsuarioUseCase(repo, rol_repo, MagicMock(), lms, _HASHER)

    u = await uc.execute(comando(correo="profesor@upc.edu.pe", nombres="Luis", apellidos="Gómez"))

    assert lms.provisiones == []  # ya existía: no se recrea
    assert u.moodle_user_id == 2
    # El rol que se le asigna en SWARD es el que dijo Moodle, no el que pidió nadie.
    from src.domain.entities.rol import TipoRol

    rol_repo.find_by_nombre.assert_awaited_once_with(TipoRol("docente"))


@pytest.mark.asyncio
async def test_la_carrera_queda_guardada(use_case):
    u = await use_case.execute(comando(carrera="Ingeniería Industrial"))
    assert u.carrera == "Ingeniería Industrial"


@pytest.mark.asyncio
async def test_sin_carrera_queda_en_none(use_case):
    u = await use_case.execute(comando(carrera="   "))
    assert u.carrera is None


# ------------------------------------------------------------ correo de bienvenida
# Existe desde el 27-sep-2026, cuando se pasó a una sola contraseña: el correo que
# mandaba Moodle desapareció, y con él la confirmación de que la dirección existe
# y la explicación de dónde entrar.


@pytest.mark.asyncio
async def test_la_bienvenida_dice_donde_entrar_y_con_que():
    email = FakeEmail()
    uc = _use_case(FakeLmsClient(MOODLE_ESTUDIANTE), email)

    await uc.execute(comando(correo="ana@upc.edu.pe"))

    assert len(email.enviados) == 1
    destinatario, asunto, cuerpo = email.enviados[0]
    assert destinatario == "ana@upc.edu.pe"
    assert "inscrito" in asunto.lower()
    # Lo que no puede faltar: la regla de la contraseña única y las dos direcciones.
    assert "la contraseña que elegiste" in cuerpo
    assert "https://aula.example" in cuerpo
    assert "https://app.example" in cuerpo
    # Y lo que no debe aparecer nunca: la contraseña.
    assert "SecurePass1" not in cuerpo


@pytest.mark.asyncio
async def test_si_el_correo_falla_el_registro_igual_se_completa():
    """La cuenta ya existe en los dos sitios cuando se intenta el envío.

    Hacer repetir el trámite por un fallo del servidor de correo cambiaría un
    problema menor por uno mayor.
    """
    email = FakeEmail(falla=True)
    uc = _use_case(FakeLmsClient(MOODLE_ESTUDIANTE), email)

    usuario = await uc.execute(comando(correo="ana@upc.edu.pe"))

    assert usuario.correo_institucional == "ana@upc.edu.pe"
    assert email.enviados == []


@pytest.mark.asyncio
async def test_sin_correo_configurado_no_se_intenta_enviar():
    uc = _use_case(FakeLmsClient(MOODLE_ESTUDIANTE), email=None)
    usuario = await uc.execute(comando(correo="ana@upc.edu.pe"))
    assert usuario.correo_institucional == "ana@upc.edu.pe"
