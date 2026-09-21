import re
from uuid import UUID

import pytest

from src.application.ports.out_.codigo_recuperacion_port import CodigoGuardado, CodigoRecuperacionPort
from src.application.ports.out_.email_port import EmailPort, EnvioCorreoError
from src.application.use_cases.recuperar_contrasena import (
    CodigoInvalidoError,
    RecuperacionConfig,
    RecuperarContrasenaUseCase,
)
from src.domain.entities.usuario import Usuario
from src.domain.value_objects.estado_usuario import EstadoUsuario
from src.infrastructure.adapters.out_.passlib_password_hasher_adapter import PasslibPasswordHasher

_HASHER = PasslibPasswordHasher()
_CONFIG = RecuperacionConfig(
    codigo_ttl=900,
    max_intentos=5,
    espera_reenvio=60,
    max_envios_por_hora=5,
    secreto="clave-de-prueba-suficientemente-larga-para-hmac",
)
CORREO = "ana@sward.test"


# --------------------------------------------------------------------- dobles
class RepoFalso:
    def __init__(self, usuario: Usuario | None):
        self.usuario = usuario
        self.guardados = 0

    async def find_by_correo(self, correo: str):
        if self.usuario and self.usuario.correo_institucional == correo:
            return self.usuario
        return None

    async def save(self, usuario):
        self.guardados += 1
        return usuario


class CodigosFalsos(CodigoRecuperacionPort):
    """Almacén en memoria; `vencer()` simula que pasó el tiempo."""

    def __init__(self):
        self.huellas: dict[UUID, str] = {}
        self.intentos: dict[UUID, int] = {}
        self.espera: set[UUID] = set()
        self.envios: dict[UUID, int] = {}

    async def guardar(self, usuario_id, huella, ttl_segundos):
        self.huellas[usuario_id] = huella
        self.intentos.pop(usuario_id, None)

    async def obtener(self, usuario_id):
        if usuario_id not in self.huellas:
            return None
        return CodigoGuardado(self.huellas[usuario_id], self.intentos.get(usuario_id, 0))

    async def registrar_intento_fallido(self, usuario_id):
        self.intentos[usuario_id] = self.intentos.get(usuario_id, 0) + 1
        return self.intentos[usuario_id]

    async def eliminar(self, usuario_id):
        self.huellas.pop(usuario_id, None)
        self.intentos.pop(usuario_id, None)

    async def en_espera(self, usuario_id):
        return usuario_id in self.espera

    async def iniciar_espera(self, usuario_id, segundos):
        self.espera.add(usuario_id)

    async def contar_envio(self, usuario_id, ventana_segundos):
        self.envios[usuario_id] = self.envios.get(usuario_id, 0) + 1
        return self.envios[usuario_id]

    def vencer(self):
        self.huellas.clear()
        self.intentos.clear()

    def fin_de_espera(self):
        self.espera.clear()


class CacheFalsa:
    def __init__(self):
        self.bloqueados_por_intentos: set[UUID] = set()
        self.tokens_invalidados: list[UUID] = []
        self.intentos_limpiados: list[str] = []

    async def fue_bloqueado_por_intentos(self, usuario_id):
        return usuario_id in self.bloqueados_por_intentos

    async def limpiar_bloqueo_por_intentos(self, usuario_id):
        self.bloqueados_por_intentos.discard(usuario_id)

    async def invalidar_todos_refresh_tokens(self, usuario_id):
        self.tokens_invalidados.append(usuario_id)

    async def limpiar_intentos_login(self, correo):
        self.intentos_limpiados.append(correo)


class CorreoFalso(EmailPort):
    def __init__(self, falla: bool = False):
        self.enviados: list[tuple[str, str, str]] = []
        self.falla = falla

    async def enviar(self, destinatario, asunto, cuerpo):
        if self.falla:
            raise EnvioCorreoError("servidor caído")
        self.enviados.append((destinatario, asunto, cuerpo))

    @property
    def ultimo_codigo(self) -> str:
        return re.search(r"Tu código es: (\d{6})", self.enviados[-1][2]).group(1)


def _usuario(estado=EstadoUsuario.ACTIVO) -> Usuario:
    u = Usuario(correo_institucional=CORREO, nombre="Ana")
    u.password_hash = _HASHER.hash("ClaveVieja1")
    u.estado = estado
    return u


def _armar(usuario=None, correo_falla=False):
    usuario = usuario if usuario is not None else _usuario()
    repo, codigos, cache, correo = RepoFalso(usuario), CodigosFalsos(), CacheFalsa(), CorreoFalso(correo_falla)
    uc = RecuperarContrasenaUseCase(repo, codigos, cache, correo, _HASHER, _CONFIG)
    return uc, repo, codigos, cache, correo


# --------------------------------------------------------------- solicitar
@pytest.mark.asyncio
async def test_solicitar_envia_un_codigo_de_seis_digitos():
    uc, _, codigos, _, correo = _armar()
    await uc.solicitar(CORREO)
    assert len(correo.enviados) == 1
    assert correo.enviados[0][0] == CORREO
    assert re.fullmatch(r"\d{6}", correo.ultimo_codigo)


@pytest.mark.asyncio
async def test_el_codigo_no_se_guarda_en_claro():
    uc, _, codigos, _, correo = _armar()
    await uc.solicitar(CORREO)
    huella = next(iter(codigos.huellas.values()))
    assert correo.ultimo_codigo not in huella
    assert len(huella) == 64  # HMAC-SHA256 en hexadecimal


@pytest.mark.asyncio
async def test_correo_desconocido_no_envia_nada_ni_falla():
    uc, _, _, _, correo = _armar()
    await uc.solicitar("nadie@sward.test")
    assert correo.enviados == []


@pytest.mark.asyncio
async def test_el_correo_se_normaliza():
    uc, _, _, _, correo = _armar()
    await uc.solicitar("  ANA@Sward.Test ")
    assert len(correo.enviados) == 1


@pytest.mark.asyncio
async def test_cuenta_desactivada_no_recibe_codigo():
    uc, _, _, _, correo = _armar(_usuario(EstadoUsuario.INACTIVO))
    await uc.solicitar(CORREO)
    assert correo.enviados == []


@pytest.mark.asyncio
async def test_no_se_reenvia_durante_la_espera():
    uc, _, _, _, correo = _armar()
    await uc.solicitar(CORREO)
    await uc.solicitar(CORREO)
    assert len(correo.enviados) == 1


@pytest.mark.asyncio
async def test_limite_de_envios_por_hora():
    uc, _, codigos, _, correo = _armar()
    for _ in range(8):
        await uc.solicitar(CORREO)
        codigos.fin_de_espera()
    assert len(correo.enviados) == _CONFIG.max_envios_por_hora


@pytest.mark.asyncio
async def test_si_el_correo_falla_el_codigo_se_descarta():
    uc, _, codigos, _, _ = _armar(correo_falla=True)
    await uc.solicitar(CORREO)  # no propaga el error: la respuesta es la misma
    assert codigos.huellas == {}


# ---------------------------------------------------------------- verificar
@pytest.mark.asyncio
async def test_verificar_acepta_el_codigo_correcto_sin_consumirlo():
    uc, _, codigos, _, correo = _armar()
    await uc.solicitar(CORREO)
    await uc.verificar(CORREO, correo.ultimo_codigo)
    assert codigos.huellas, "verificar no debe consumir el código"


@pytest.mark.asyncio
async def test_verificar_rechaza_un_codigo_equivocado():
    uc, _, _, _, correo = _armar()
    await uc.solicitar(CORREO)
    otro = "000000" if correo.ultimo_codigo != "000000" else "111111"
    with pytest.raises(CodigoInvalidoError):
        await uc.verificar(CORREO, otro)


@pytest.mark.asyncio
async def test_tras_cinco_fallos_el_codigo_deja_de_servir():
    uc, _, _, _, correo = _armar()
    await uc.solicitar(CORREO)
    bueno = correo.ultimo_codigo
    malo = "000000" if bueno != "000000" else "111111"
    for _ in range(_CONFIG.max_intentos):
        with pytest.raises(CodigoInvalidoError):
            await uc.verificar(CORREO, malo)
    with pytest.raises(CodigoInvalidoError):
        await uc.verificar(CORREO, bueno)


@pytest.mark.asyncio
async def test_codigo_vencido():
    uc, _, codigos, _, correo = _armar()
    await uc.solicitar(CORREO)
    codigos.vencer()
    with pytest.raises(CodigoInvalidoError):
        await uc.verificar(CORREO, correo.ultimo_codigo)


@pytest.mark.asyncio
async def test_correo_desconocido_da_el_mismo_error_que_un_codigo_malo():
    uc, _, _, _, _ = _armar()
    with pytest.raises(CodigoInvalidoError):
        await uc.verificar("nadie@sward.test", "123456")


@pytest.mark.asyncio
async def test_un_codigo_no_sirve_para_otra_cuenta():
    """La huella incluye el id del usuario: el mismo número no vale en otra cuenta."""
    uc_a, _, codigos_a, _, correo_a = _armar()
    await uc_a.solicitar(CORREO)
    otra = Usuario(correo_institucional="otra@sward.test")
    assert codigos_a.huellas[uc_a._usuario_repo.usuario.id] != uc_a._huella(otra.id, correo_a.ultimo_codigo)


# -------------------------------------------------------------- restablecer
@pytest.mark.asyncio
async def test_restablecer_cambia_la_contrasena_y_cierra_sesiones():
    uc, repo, codigos, cache, correo = _armar()
    await uc.solicitar(CORREO)
    await uc.restablecer(CORREO, correo.ultimo_codigo, "ClaveNueva2026")
    assert _HASHER.verify("ClaveNueva2026", repo.usuario.password_hash)
    assert not _HASHER.verify("ClaveVieja1", repo.usuario.password_hash)
    assert cache.tokens_invalidados == [repo.usuario.id]
    assert cache.intentos_limpiados == [CORREO]
    assert codigos.huellas == {}, "el código se consume al usarlo"


@pytest.mark.asyncio
async def test_el_codigo_no_se_puede_usar_dos_veces():
    uc, _, _, _, correo = _armar()
    await uc.solicitar(CORREO)
    codigo = correo.ultimo_codigo
    await uc.restablecer(CORREO, codigo, "ClaveNueva2026")
    with pytest.raises(CodigoInvalidoError):
        await uc.restablecer(CORREO, codigo, "OtraClave2026")


@pytest.mark.asyncio
async def test_contrasena_debil_no_gasta_el_codigo():
    uc, repo, codigos, _, correo = _armar()
    await uc.solicitar(CORREO)
    with pytest.raises(ValueError, match="mayúscula"):
        await uc.restablecer(CORREO, correo.ultimo_codigo, "sinmayuscula1")
    assert codigos.huellas and codigos.intentos == {}, "ni se consume ni cuenta como intento"
    await uc.restablecer(CORREO, correo.ultimo_codigo, "ConMayuscula1")
    assert _HASHER.verify("ConMayuscula1", repo.usuario.password_hash)


@pytest.mark.asyncio
async def test_desbloquea_la_cuenta_bloqueada_por_intentos():
    uc, repo, _, cache, correo = _armar(_usuario(EstadoUsuario.BLOQUEADO))
    cache.bloqueados_por_intentos.add(repo.usuario.id)
    await uc.solicitar(CORREO)
    await uc.restablecer(CORREO, correo.ultimo_codigo, "ClaveNueva2026")
    assert repo.usuario.estado == EstadoUsuario.ACTIVO
    assert repo.usuario.id not in cache.bloqueados_por_intentos


@pytest.mark.asyncio
async def test_respeta_el_bloqueo_puesto_por_un_administrador():
    uc, repo, _, _, correo = _armar(_usuario(EstadoUsuario.BLOQUEADO))
    await uc.solicitar(CORREO)
    await uc.restablecer(CORREO, correo.ultimo_codigo, "ClaveNueva2026")
    assert repo.usuario.estado == EstadoUsuario.BLOQUEADO
    assert _HASHER.verify("ClaveNueva2026", repo.usuario.password_hash)


# ------------------------------------------------------------ sin correo
@pytest.mark.asyncio
async def test_sin_correo_configurado_no_esta_disponible():
    from src.application.use_cases.recuperar_contrasena import RecuperacionNoDisponibleError
    from src.infrastructure.adapters.out_.sin_correo_adapter import SinCorreoAdapter

    usuario = _usuario()
    uc = RecuperarContrasenaUseCase(
        RepoFalso(usuario), CodigosFalsos(), CacheFalsa(), SinCorreoAdapter(), _HASHER, _CONFIG
    )
    with pytest.raises(RecuperacionNoDisponibleError):
        await uc.solicitar(CORREO)
    # El aviso es el mismo para un correo que no existe: no revela nada.
    with pytest.raises(RecuperacionNoDisponibleError):
        await uc.solicitar("nadie@sward.test")
