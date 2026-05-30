"""C-03: la guardia de secret_key impide arrancar inseguro fuera de development."""

import pytest

from src.infrastructure.config.settings import DEFAULT_SECRET_KEY, Settings


def test_development_permite_secret_default():
    s = Settings(environment="development", secret_key=DEFAULT_SECRET_KEY)
    assert s.secret_key == DEFAULT_SECRET_KEY


def test_produccion_rechaza_secret_default():
    with pytest.raises(ValueError, match="SECRET_KEY inseguro"):
        Settings(environment="production", secret_key=DEFAULT_SECRET_KEY)


def test_produccion_rechaza_secret_corto():
    with pytest.raises(ValueError, match="SECRET_KEY inseguro"):
        Settings(environment="production", secret_key="corto")


def test_produccion_acepta_secret_seguro():
    seguro = "x" * 64
    s = Settings(environment="production", secret_key=seguro)
    assert s.secret_key == seguro
