"""Tests de integración de los endpoints de autenticación (in-process)."""

import pytest

from src.application.use_cases.registrar_usuario import CONSENTIMIENTO_VERSION_VIGENTE

REGISTER = "/auth/register"
LOGIN = "/auth/login"
LOGOUT = "/auth/logout"
HEALTH = "/health"

# Desde el 24 de septiembre el registro exige la versión del consentimiento que
# la persona leyó y aceptó. Se toma del código en vez de copiarla, para que un
# cambio de versión no obligue a editar cada prueba; que una versión vieja se
# rechace lo comprueban las pruebas unitarias del caso de uso.
USER = {"correo": "alumno@upc.edu.pe", "password": "Password1"}
# El consentimiento va solo en el alta: el login rechaza campos de más.
REGISTRO = {**USER, "consentimiento_version": CONSENTIMIENTO_VERSION_VIGENTE}


@pytest.mark.asyncio
async def test_health_ok(client):
    resp = await client.get(HEALTH)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_registro_crea_usuario(client):
    resp = await client.post(REGISTER, json=REGISTRO)
    assert resp.status_code == 201
    body = resp.json()
    assert body["correo"] == USER["correo"]
    assert "id" in body


@pytest.mark.asyncio
async def test_registro_publico_ignora_rol_y_no_escala_a_admin(client):
    """C-01: el registro público nunca puede asignar rol administrador.

    Con `extra="forbid"` cualquier campo `rol` en el body se rechaza con 422,
    impidiendo de raíz la escalada de privilegios. Un registro limpio se
    autentica siempre como `estudiante`.
    """
    payload = {**REGISTRO, "rol": "administrador"}
    resp = await client.post(REGISTER, json=payload)
    assert resp.status_code == 422

    resp = await client.post(REGISTER, json=REGISTRO)
    assert resp.status_code == 201

    login = await client.post(LOGIN, json=USER)
    assert login.status_code == 200
    access_token = login.json()["access_token"]

    import jwt as pyjwt

    claims = pyjwt.decode(access_token, options={"verify_signature": False})
    assert claims["rol"] == "estudiante"
    assert claims["rol"] != "administrador"


@pytest.mark.asyncio
async def test_flujo_registro_y_login_devuelve_token(client):
    reg = await client.post(REGISTER, json=REGISTRO)
    assert reg.status_code == 201

    resp = await client.post(LOGIN, json=USER)
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["expires_in"] > 0


@pytest.mark.asyncio
async def test_login_password_incorrecta_devuelve_401(client):
    await client.post(REGISTER, json=REGISTRO)
    resp = await client.post(LOGIN, json={"correo": USER["correo"], "password": "ClaveErronea9"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_endpoint_protegido_sin_token_es_rechazado(client):
    # /auth/logout exige Bearer token vía get_current_user (HTTPBearer).
    resp = await client.post(LOGOUT)
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_endpoint_protegido_con_token_valido(client):
    await client.post(REGISTER, json=REGISTRO)
    login = await client.post(LOGIN, json=USER)
    token = login.json()["access_token"]

    resp = await client.post(LOGOUT, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 204
