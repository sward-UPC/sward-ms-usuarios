"""Fixtures de integración para los endpoints de usuarios.

La app se ejerce in-process con httpx.AsyncClient + ASGITransport (sin servidor).
Los puertos de salida se sustituyen vía dependency_overrides de FastAPI:
- Repos de usuario/rol: implementaciones en memoria (sin Postgres).
- CachePort: FakeRedisCache (sin Redis).
- EventPublisher: stub que descarta eventos.
Se conserva la lógica real de los casos de uso (hashing, validación, JWT).
"""

import json
from uuid import UUID

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.application.use_cases.autenticar_usuario import AutenticarUsuarioUseCase
from src.application.use_cases.registrar_usuario import RegistrarUsuarioUseCase
from src.domain.entities.rol import Permiso, Rol, TipoRol
from src.domain.entities.usuario import Usuario
from src.domain.ports.out_.cache_port import CachePort
from src.domain.ports.out_.rol_repository_port import RolRepositoryPort
from src.domain.ports.out_.usuario_repository_port import UsuarioRepositoryPort
from src.infrastructure.adapters.in_.main import app
from src.infrastructure.adapters.out_.jwt_adapter import JwtAdapter
from src.infrastructure.dependencies import (
    get_autenticar_usuario_uc,
    get_jwt_adapter,
    get_redis_adapter,
    get_registrar_usuario_uc,
)


class FakeUsuarioRepo(UsuarioRepositoryPort):
    def __init__(self):
        self._por_id: dict[UUID, Usuario] = {}

    async def find_by_correo(self, correo: str) -> Usuario | None:
        for u in self._por_id.values():
            if u.correo_institucional.lower() == correo.lower():
                return u
        return None

    async def find_by_id(self, id: UUID) -> Usuario | None:
        return self._por_id.get(id)

    async def save(self, usuario: Usuario) -> Usuario:
        self._por_id[usuario.id] = usuario
        return usuario

    async def exists_by_correo(self, correo: str) -> bool:
        return await self.find_by_correo(correo) is not None

    async def find_all(self, offset: int = 0, limit: int = 20):
        items = list(self._por_id.values())
        return items[offset : offset + limit], len(items)

    async def update_estado(self, id: UUID, estado: str) -> None:
        if id in self._por_id:
            from src.domain.value_objects.estado_usuario import EstadoUsuario

            self._por_id[id].estado = EstadoUsuario(estado)


class FakeRolRepo(RolRepositoryPort):
    def __init__(self):
        self._roles = {
            TipoRol.ESTUDIANTE: Rol(
                nombre=TipoRol.ESTUDIANTE,
                permisos=[Permiso(codigo="ver_cursos")],
            ),
            TipoRol.DOCENTE: Rol(nombre=TipoRol.DOCENTE),
            TipoRol.ADMINISTRADOR: Rol(nombre=TipoRol.ADMINISTRADOR),
        }
        self._asignaciones: dict[UUID, list[UUID]] = {}

    async def find_by_nombre(self, nombre: TipoRol) -> Rol | None:
        return self._roles.get(nombre)

    async def find_by_usuario_id(self, usuario_id: UUID) -> list[Rol]:
        rol_ids = self._asignaciones.get(usuario_id, [])
        return [r for r in self._roles.values() if r.id in rol_ids]

    async def assign_rol(self, usuario_id: UUID, rol_id: UUID) -> None:
        self._asignaciones.setdefault(usuario_id, []).append(rol_id)

    async def revoke_rol(self, usuario_id: UUID, rol_id: UUID) -> None:
        if usuario_id in self._asignaciones:
            self._asignaciones[usuario_id] = [r for r in self._asignaciones[usuario_id] if r != rol_id]

    async def find_all(self) -> list[Rol]:
        return list(self._roles.values())


class FakeRedisCache(CachePort):
    """Cache en memoria que imita el comportamiento usado por los casos de uso."""

    def __init__(self):
        self._store: dict[str, str] = {}

    async def get_permisos(self, usuario_id: UUID):
        data = self._store.get(f"perms:{usuario_id}")
        return json.loads(data) if data else None

    async def set_permisos(self, usuario_id: UUID, permisos, ttl: int) -> None:
        self._store[f"perms:{usuario_id}"] = json.dumps(permisos)

    async def invalidar_permisos(self, usuario_id: UUID) -> None:
        self._store.pop(f"perms:{usuario_id}", None)

    async def incrementar_intentos_login(self, correo: str, ttl: int) -> int:
        key = f"login_attempts:{correo}"
        count = int(self._store.get(key, 0)) + 1
        self._store[key] = str(count)
        return count

    async def get_intentos_login(self, correo: str) -> int:
        return int(self._store.get(f"login_attempts:{correo}", 0))

    async def limpiar_intentos_login(self, correo: str) -> None:
        self._store.pop(f"login_attempts:{correo}", None)

    async def blacklist_token(self, jti: str, ttl_segundos: int) -> None:
        self._store[f"blacklist:{jti}"] = "revoked"

    async def is_token_blacklisted(self, jti: str) -> bool:
        return f"blacklist:{jti}" in self._store

    async def save_refresh_token(self, usuario_id: UUID, device_id: str, token_hash: str, ttl: int) -> None:
        self._store[f"refresh:{usuario_id}:{device_id}"] = token_hash

    async def get_refresh_token(self, usuario_id: UUID, device_id: str):
        return self._store.get(f"refresh:{usuario_id}:{device_id}")

    async def invalidar_todos_refresh_tokens(self, usuario_id: UUID) -> None:
        for k in [k for k in self._store if k.startswith(f"refresh:{usuario_id}:")]:
            self._store.pop(k, None)


class _StubEventPublisher:
    def publish(self, event) -> None:  # noqa: ARG002
        return None


@pytest_asyncio.fixture
async def client():
    usuario_repo = FakeUsuarioRepo()
    rol_repo = FakeRolRepo()
    cache = FakeRedisCache()
    jwt = JwtAdapter()
    events = _StubEventPublisher()

    def _registrar_uc():
        return RegistrarUsuarioUseCase(usuario_repo=usuario_repo, rol_repo=rol_repo, event_publisher=events)

    def _autenticar_uc():
        return AutenticarUsuarioUseCase(
            usuario_repo=usuario_repo,
            rol_repo=rol_repo,
            token_port=jwt,
            cache=cache,
            event_publisher=events,
        )

    app.dependency_overrides[get_registrar_usuario_uc] = _registrar_uc
    app.dependency_overrides[get_autenticar_usuario_uc] = _autenticar_uc
    app.dependency_overrides[get_redis_adapter] = lambda: cache
    app.dependency_overrides[get_jwt_adapter] = lambda: jwt

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
