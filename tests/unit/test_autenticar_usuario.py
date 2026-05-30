import pytest
from unittest.mock import AsyncMock, MagicMock
from src.application.use_cases.autenticar_usuario import (
    AutenticacionError,
    AutenticarUsuarioCommand,
    AutenticarUsuarioUseCase,
    CuentaBloqueadaError,
)
from src.domain.entities.rol import Rol, TipoRol
from src.domain.entities.usuario import Usuario
from src.domain.ports.out_.token_port import TokenPair
from src.domain.value_objects.estado_usuario import EstadoUsuario


def _make_usuario():
    from passlib.context import CryptContext

    u = Usuario(correo_institucional="test@upc.edu.pe")
    u.password_hash = CryptContext(schemes=["bcrypt"], deprecated="auto").hash(
        "Password1"
    )
    u.estado = EstadoUsuario.ACTIVO
    return u


@pytest.fixture
def use_case():
    u = _make_usuario()
    usuario_repo = AsyncMock()
    usuario_repo.find_by_correo.return_value = u
    usuario_repo.save.return_value = u
    rol_repo = AsyncMock()
    rol_repo.find_by_usuario_id.return_value = [Rol(nombre=TipoRol.ESTUDIANTE)]
    token_port = MagicMock()
    token_port.generar_par.return_value = TokenPair(
        access_token="access.jwt", refresh_token="refresh.jwt"
    )
    cache = AsyncMock()
    cache.get_intentos_login.return_value = 0
    cache.incrementar_intentos_login.return_value = 1
    return AutenticarUsuarioUseCase(
        usuario_repo, rol_repo, token_port, cache, MagicMock()
    )


@pytest.mark.asyncio
async def test_login_exitoso(use_case):
    result = await use_case.execute(
        AutenticarUsuarioCommand(correo="test@upc.edu.pe", password="Password1")
    )
    assert result.access_token == "access.jwt"


@pytest.mark.asyncio
async def test_password_incorrecta(use_case):
    with pytest.raises(AutenticacionError):
        await use_case.execute(
            AutenticarUsuarioCommand(correo="test@upc.edu.pe", password="wrong")
        )


@pytest.mark.asyncio
async def test_cuenta_bloqueada_por_intentos(use_case):
    use_case._cache.get_intentos_login.return_value = 5
    with pytest.raises(CuentaBloqueadaError):
        await use_case.execute(
            AutenticarUsuarioCommand(correo="test@upc.edu.pe", password="Password1")
        )
