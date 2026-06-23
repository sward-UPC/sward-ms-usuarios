from passlib.context import CryptContext

from src.domain.ports.out_.password_hasher_port import PasswordHasherPort

# Contexto de hashing compartido por todos los casos de uso (argon2 + bcrypt).
_pwd_ctx = CryptContext(schemes=["argon2", "bcrypt"], deprecated="auto")


class PasslibPasswordHasher(PasswordHasherPort):
    """Implementación del puerto de hashing basada en passlib."""

    def hash(self, password: str) -> str:
        return _pwd_ctx.hash(password)

    def verify(self, password: str, password_hash: str) -> bool:
        return _pwd_ctx.verify(password, password_hash)
