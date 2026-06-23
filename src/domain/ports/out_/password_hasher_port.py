from abc import ABC, abstractmethod


class PasswordHasherPort(ABC):
    """Puerto de salida para el hashing y verificación de contraseñas.

    Aísla al núcleo de la librería concreta (passlib/argon2/bcrypt): los casos
    de uso solo conocen este contrato, nunca el algoritmo ni la implementación.
    """

    @abstractmethod
    def hash(self, password: str) -> str: ...

    @abstractmethod
    def verify(self, password: str, password_hash: str) -> bool: ...
