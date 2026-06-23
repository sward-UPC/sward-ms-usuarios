from unittest.mock import AsyncMock

import pytest

from src.application.use_cases.gestionar_usuarios import (
    GestionarUsuariosUseCase,
    PasswordActualInvalidaError,
    UsuarioNoEncontradoError,
)
from src.domain.entities.usuario import Usuario
from src.domain.value_objects.estado_usuario import EstadoUsuario
from src.infrastructure.adapters.out_.passlib_password_hasher_adapter import PasslibPasswordHasher

pwd_ctx = PasslibPasswordHasher()


def _make_usuario():
    u = Usuario(correo_institucional="test@upc.edu.pe")
    u.password_hash = pwd_ctx.hash("Password1")
    u.estado = EstadoUsuario.ACTIVO
    return u


def _make_use_case(usuario):
    usuario_repo = AsyncMock()
    usuario_repo.find_by_id.return_value = usuario
    usuario_repo.save.side_effect = lambda u: u
    cache = AsyncMock()
    return GestionarUsuariosUseCase(usuario_repo, AsyncMock(), cache, pwd_ctx), usuario_repo, cache


@pytest.mark.asyncio
async def test_actualizar_perfil_persiste_avatar():
    u = _make_usuario()
    uc, repo, _ = _make_use_case(u)

    result = await uc.actualizar_perfil(u.id, avatar_color="#6366f1", avatar_url="data:image/jpeg;base64,abc")

    assert result.avatar_color == "#6366f1"
    assert result.avatar_url == "data:image/jpeg;base64,abc"
    repo.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_actualizar_perfil_usuario_no_encontrado():
    uc, repo, _ = _make_use_case(None)
    repo.find_by_id.return_value = None
    with pytest.raises(UsuarioNoEncontradoError):
        await uc.actualizar_perfil(_make_usuario().id, avatar_color="#000")


@pytest.mark.asyncio
async def test_cambiar_password_exitoso():
    u = _make_usuario()
    uc, repo, cache = _make_use_case(u)

    await uc.cambiar_password(u.id, password_actual="Password1", password_nueva="NuevaPassword2")

    assert pwd_ctx.verify("NuevaPassword2", u.password_hash)
    repo.save.assert_awaited_once()
    cache.invalidar_todos_refresh_tokens.assert_awaited_once_with(u.id)


@pytest.mark.asyncio
async def test_cambiar_password_actual_incorrecta():
    u = _make_usuario()
    uc, repo, cache = _make_use_case(u)

    with pytest.raises(PasswordActualInvalidaError):
        await uc.cambiar_password(u.id, password_actual="Incorrecta", password_nueva="NuevaPassword2")

    repo.save.assert_not_awaited()
    cache.invalidar_todos_refresh_tokens.assert_not_awaited()
