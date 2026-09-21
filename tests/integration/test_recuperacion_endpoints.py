"""La recuperación de contraseña de punta a punta, por HTTP.

La historia que importa: alguien olvida su contraseña, la intenta varias veces,
la cuenta se bloquea, pide un código, lo usa y vuelve a entrar.
"""

import re

import pytest

REGISTER = "/auth/register"
LOGIN = "/auth/login"
RECOVERY = "/auth/password-recovery"
VERIFY = "/auth/password-recovery/verify"
RESET = "/auth/password-reset"

CORREO = "alumno@upc.edu.pe"
USER = {"correo": CORREO, "password": "Password1"}


def _codigo(client) -> str:
    return re.search(r"Tu código es: (\d{6})", client.buzon.correos[-1]["cuerpo"]).group(1)


def _otro(codigo: str) -> str:
    return "000000" if codigo != "000000" else "111111"


@pytest.mark.asyncio
async def test_olvido_bloqueo_recuperacion_y_vuelta_a_entrar(client):
    await client.post(REGISTER, json=USER)

    # Cinco intentos fallidos bloquean la cuenta.
    for _ in range(5):
        await client.post(LOGIN, json={"correo": CORREO, "password": "Equivocada1"})
    bloqueado = await client.post(LOGIN, json=USER)
    assert bloqueado.status_code == 423

    # Pide el código y lo recibe por correo.
    resp = await client.post(RECOVERY, json={"correo": CORREO})
    assert resp.status_code == 202
    assert len(client.buzon.correos) == 1
    assert client.buzon.correos[0]["para"] == CORREO
    codigo = _codigo(client)

    # Lo verifica y fija la contraseña nueva.
    assert (await client.post(VERIFY, json={"correo": CORREO, "codigo": codigo})).status_code == 204
    resp = await client.post(RESET, json={"correo": CORREO, "codigo": codigo, "password_nueva": "Recuperada2026"})
    assert resp.status_code == 204

    # La contraseña vieja ya no sirve y la nueva sí, con la cuenta desbloqueada.
    assert (await client.post(LOGIN, json=USER)).status_code == 401
    entra = await client.post(LOGIN, json={"correo": CORREO, "password": "Recuperada2026"})
    assert entra.status_code == 200
    assert "access_token" in entra.json()


@pytest.mark.asyncio
async def test_la_respuesta_no_revela_si_el_correo_existe(client):
    await client.post(REGISTER, json=USER)
    existe = await client.post(RECOVERY, json={"correo": CORREO})
    no_existe = await client.post(RECOVERY, json={"correo": "nadie@upc.edu.pe"})
    assert existe.status_code == no_existe.status_code == 202
    assert existe.json() == no_existe.json()
    assert len(client.buzon.correos) == 1, "al correo inexistente no se le envía nada"


@pytest.mark.asyncio
async def test_codigo_equivocado(client):
    await client.post(REGISTER, json=USER)
    await client.post(RECOVERY, json={"correo": CORREO})
    resp = await client.post(VERIFY, json={"correo": CORREO, "codigo": _otro(_codigo(client))})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_el_codigo_no_sirve_dos_veces(client):
    await client.post(REGISTER, json=USER)
    await client.post(RECOVERY, json={"correo": CORREO})
    codigo = _codigo(client)
    primera = await client.post(RESET, json={"correo": CORREO, "codigo": codigo, "password_nueva": "Primera2026"})
    segunda = await client.post(RESET, json={"correo": CORREO, "codigo": codigo, "password_nueva": "Segunda2026"})
    assert primera.status_code == 204
    assert segunda.status_code == 400


@pytest.mark.asyncio
async def test_contrasena_debil(client):
    await client.post(REGISTER, json=USER)
    await client.post(RECOVERY, json={"correo": CORREO})
    resp = await client.post(
        RESET, json={"correo": CORREO, "codigo": _codigo(client), "password_nueva": "sinmayuscula1"}
    )
    assert resp.status_code == 422
    assert "mayúscula" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_el_codigo_debe_tener_seis_digitos(client):
    resp = await client.post(VERIFY, json={"correo": CORREO, "codigo": "12ab"})
    assert resp.status_code == 422
