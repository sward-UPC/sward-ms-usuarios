from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.use_cases.registrar_usuario import (
    CorreoNoEnMoodleError,
    CorreoYaRegistradoError,
    RegistrarUsuarioCommand,
    RegistrarUsuarioUseCase,
)
from src.domain.ports.out_.lms_client_port import LmsClientPort

MOODLE_ESTUDIANTE = {
    "moodle_user_id": 7,
    "nombre": "Test",
    "apellido": "User",
    "correo": "nuevo@upc.edu.pe",
    "rol": "estudiante",
}


class FakeLmsClient(LmsClientPort):
    def __init__(self, respuesta: dict | None):
        self._respuesta = respuesta

    async def buscar_usuario_por_correo(self, correo: str) -> dict | None:
        return self._respuesta


@pytest.fixture
def use_case():
    repo = AsyncMock()
    repo.exists_by_correo.return_value = False
    repo.save.side_effect = lambda u: u
    rol_repo = AsyncMock()
    rol_repo.find_by_nombre.return_value = None
    lms = FakeLmsClient(MOODLE_ESTUDIANTE)
    return RegistrarUsuarioUseCase(repo, rol_repo, MagicMock(), lms)


@pytest.mark.asyncio
async def test_registro_exitoso(use_case):
    u = await use_case.execute(RegistrarUsuarioCommand(correo="nuevo@upc.edu.pe", password="SecurePass1"))
    assert u.correo_institucional == "nuevo@upc.edu.pe"
    assert u.nombre == "Test"
    assert u.moodle_user_id == 7


@pytest.mark.asyncio
async def test_correo_no_en_moodle():
    repo = AsyncMock()
    rol_repo = AsyncMock()
    lms = FakeLmsClient(None)
    uc = RegistrarUsuarioUseCase(repo, rol_repo, MagicMock(), lms)
    with pytest.raises(CorreoNoEnMoodleError):
        await uc.execute(RegistrarUsuarioCommand(correo="fantasma@upc.edu.pe", password="SecurePass1"))


@pytest.mark.asyncio
async def test_correo_duplicado(use_case):
    use_case._usuario_repo.exists_by_correo.return_value = True
    with pytest.raises(CorreoYaRegistradoError):
        await use_case.execute(RegistrarUsuarioCommand(correo="existe@upc.edu.pe", password="SecurePass1"))


@pytest.mark.asyncio
async def test_password_debil(use_case):
    with pytest.raises(ValueError):
        await use_case.execute(RegistrarUsuarioCommand(correo="nuevo@upc.edu.pe", password="1234"))
