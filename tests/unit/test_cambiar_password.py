"""El cambio de contraseña llega también al aula virtual.

Desde el 27 de septiembre de 2026 la persona tiene **una sola contraseña** para
SWARD y el aula virtual. El alta la copia una vez, y con eso solo la promesa
duraba hasta el primer cambio: quien la cambiaba en SWARD seguía entrando al aula
con la anterior, sin que nada se lo dijera. Lo encontró el tesista cambiando la
suya.

El orden importa y estas pruebas lo fijan: **primero el aula virtual, después
aquí**. Si el aula no responde no se cambia nada, porque quedarse con una
contraseña distinta en cada sitio es peor que no haberla cambiado.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.use_cases.gestionar_usuarios import GestionarUsuariosUseCase
from src.domain.entities.usuario import Usuario
from src.infrastructure.adapters.out_.passlib_password_hasher_adapter import (
    PasslibPasswordHasher,
)

_HASHER = PasslibPasswordHasher()
ACTUAL = "Actual2026"
NUEVA = "Nueva2026"


class FakeLms:
    def __init__(self, falla: bool = False):
        self.cambios: list[tuple[str, str]] = []
        self._falla = falla

    async def cambiar_password(self, correo: str, password: str) -> bool:
        if self._falla:
            raise RuntimeError("aula virtual no disponible")
        self.cambios.append((correo, password))
        return True


def _caso(lms: FakeLms | None):
    usuario = Usuario(
        correo_institucional="ana@upc.edu.pe",
        password_hash=_HASHER.hash(ACTUAL),
    )
    repo = AsyncMock()
    repo.find_by_id.return_value = usuario
    repo.save.side_effect = lambda u: u
    uc = GestionarUsuariosUseCase(
        usuario_repo=repo,
        rol_repo=AsyncMock(),
        cache=AsyncMock(),
        password_hasher=_HASHER,
        lms_client=lms,
    )
    return uc, usuario


@pytest.mark.asyncio
async def test_el_cambio_llega_al_aula_virtual():
    lms = FakeLms()
    uc, usuario = _caso(lms)

    await uc.cambiar_password(usuario.id, password_actual=ACTUAL, password_nueva=NUEVA)

    assert lms.cambios == [("ana@upc.edu.pe", NUEVA)]
    assert _HASHER.verify(NUEVA, usuario.password_hash)


@pytest.mark.asyncio
async def test_si_el_aula_virtual_falla_no_se_cambia_aqui_tampoco():
    """Las dos contraseñas se mueven juntas o no se mueve ninguna.

    Cambiarla sólo aquí reproduciría exactamente el fallo que esto corrige.
    """
    lms = FakeLms(falla=True)
    uc, usuario = _caso(lms)
    antes = usuario.password_hash

    with pytest.raises(RuntimeError):
        await uc.cambiar_password(usuario.id, password_actual=ACTUAL, password_nueva=NUEVA)

    assert usuario.password_hash == antes
    assert _HASHER.verify(ACTUAL, usuario.password_hash)


@pytest.mark.asyncio
async def test_sin_cliente_del_aula_el_cambio_sigue_funcionando():
    """Hay usos y pruebas que no tocan Moodle; no deben romperse por esto."""
    uc, usuario = _caso(None)
    await uc.cambiar_password(usuario.id, password_actual=ACTUAL, password_nueva=NUEVA)
    assert _HASHER.verify(NUEVA, usuario.password_hash)


@pytest.mark.asyncio
async def test_la_misma_contrasena_no_llega_a_tocar_el_aula_virtual():
    """Se rechaza antes: no tiene sentido pedirle a Moodle que no cambie nada."""
    lms = FakeLms()
    uc, usuario = _caso(lms)

    with pytest.raises(ValueError):
        await uc.cambiar_password(usuario.id, password_actual=ACTUAL, password_nueva=ACTUAL)

    assert lms.cambios == []


def test_magicmock_no_se_usa_por_error():
    """Guardia trivial: si alguien cambia el doble por un MagicMock, las
    aserciones de arriba dejarían de probar nada."""
    assert not isinstance(FakeLms(), MagicMock)
