from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.use_cases.registrar_usuario import (
    CorreoYaRegistradoError,
    RegistrarUsuarioCommand,
    RegistrarUsuarioUseCase,
)


@pytest.fixture
def use_case():
    repo = AsyncMock()
    repo.exists_by_correo.return_value = False
    repo.save.side_effect = lambda u: u
    rol_repo = AsyncMock()
    rol_repo.find_by_nombre.return_value = None
    return RegistrarUsuarioUseCase(repo, rol_repo, MagicMock())


@pytest.mark.asyncio
async def test_registro_exitoso(use_case):
    u = await use_case.execute(RegistrarUsuarioCommand(correo="nuevo@upc.edu.pe", password="SecurePass1"))
    assert u.correo_institucional == "nuevo@upc.edu.pe"


@pytest.mark.asyncio
async def test_correo_duplicado(use_case):
    use_case._usuario_repo.exists_by_correo.return_value = True
    with pytest.raises(CorreoYaRegistradoError):
        await use_case.execute(RegistrarUsuarioCommand(correo="existe@upc.edu.pe", password="SecurePass1"))


@pytest.mark.asyncio
async def test_password_debil(use_case):
    with pytest.raises(ValueError):
        await use_case.execute(RegistrarUsuarioCommand(correo="nuevo@upc.edu.pe", password="1234"))
