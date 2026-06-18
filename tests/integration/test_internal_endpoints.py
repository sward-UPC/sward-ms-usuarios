"""Tests del router interno s2s (/internal/users/by-ids)."""

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.application.use_cases.gestionar_usuarios import GestionarUsuariosUseCase
from src.domain.entities.usuario import Usuario
from src.infrastructure.adapters.in_.main import app
from src.infrastructure.config.settings import settings
from src.infrastructure.dependencies import get_gestionar_usuarios_uc
from tests.integration.conftest import FakeRedisCache, FakeRolRepo, FakeUsuarioRepo

SERVICE_KEY = "test-trazabilidad-key"


@pytest.mark.asyncio
async def test_internal_users_by_ids_devuelve_perfiles(monkeypatch):
    monkeypatch.setattr(settings, "authorized_trazabilidad_key", SERVICE_KEY)
    repo = FakeUsuarioRepo()
    usuario = Usuario(
        correo_institucional="ana@upc.edu.pe",
        nombre="Ana",
        apellido="Quispe",
        moodle_user_id=11,
    )
    await repo.save(usuario)
    uc = GestionarUsuariosUseCase(usuario_repo=repo, rol_repo=FakeRolRepo(), cache=FakeRedisCache())
    app.dependency_overrides[get_gestionar_usuarios_uc] = lambda: uc

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/internal/users/by-ids",
            json={"ids": [str(usuario.id), str(uuid4())]},  # un id inexistente se omite
            headers={"X-Service-Key": SERVICE_KEY},
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["nombre"] == "Ana"
    assert data[0]["apellido"] == "Quispe"
    assert data[0]["correo"] == "ana@upc.edu.pe"
    assert data[0]["moodle_user_id"] == 11


@pytest.mark.asyncio
async def test_internal_sin_service_key_devuelve_401():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/internal/users/by-ids", json={"ids": [str(uuid4())]})
    assert resp.status_code == 401
