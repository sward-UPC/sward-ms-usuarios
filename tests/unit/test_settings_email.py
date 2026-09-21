"""El correo de desarrollo no debe usarse fuera de development, y su ausencia
no debe impedir que el servicio arranque."""

import pytest

from src.infrastructure.config.settings import Settings

_SEGURO = "x" * 64


def test_development_admite_consola():
    s = Settings(environment="development", email_backend="consola")
    assert s.email_backend == "consola"


def test_produccion_rechaza_consola():
    with pytest.raises(ValueError, match="solo se permite en development"):
        Settings(environment="production", secret_key=_SEGURO, email_backend="consola")


def test_produccion_sin_correo_arranca():
    """Sin SMTP el servicio arranca; solo la recuperación queda no disponible."""
    s = Settings(environment="production", secret_key=_SEGURO, email_backend="")
    assert s.email_backend == ""


def test_produccion_con_smtp():
    s = Settings(environment="production", secret_key=_SEGURO, email_backend="smtp")
    assert s.email_backend == "smtp"


def test_valor_desconocido():
    with pytest.raises(ValueError, match="EMAIL_BACKEND"):
        Settings(environment="development", email_backend="sendgrid")


def test_remitente_vacio_usa_la_cuenta_smtp():
    """En AWS el remitente llega de un secreto que puede venir vacío."""
    s = Settings(environment="development", email_remitente="", smtp_user="sward.proyecto@gmail.com")
    assert s.remitente_efectivo == "SWARD <sward.proyecto@gmail.com>"


def test_remitente_explicito_se_respeta():
    s = Settings(environment="development", email_remitente="Proyecto <x@y.com>", smtp_user="otra@y.com")
    assert s.remitente_efectivo == "Proyecto <x@y.com>"
