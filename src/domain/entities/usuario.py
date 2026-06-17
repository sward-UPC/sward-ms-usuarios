import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

from src.domain.value_objects.estado_usuario import EstadoUsuario


@dataclass
class Usuario:
    id: UUID = field(default_factory=uuid4)
    correo_institucional: str = ""
    password_hash: str = ""
    estado: EstadoUsuario = EstadoUsuario.PENDIENTE_VERIFICACION
    nombre: str | None = None
    apellido: str | None = None
    moodle_user_id: int | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def validar_correo(self) -> bool:
        return bool(
            re.match(
                r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$",
                self.correo_institucional,
            )
        )

    def activar(self) -> None:
        self.estado = EstadoUsuario.ACTIVO
        self.updated_at = datetime.now(timezone.utc)

    def bloquear(self) -> None:
        self.estado = EstadoUsuario.BLOQUEADO
        self.updated_at = datetime.now(timezone.utc)

    def desactivar(self) -> None:
        self.estado = EstadoUsuario.INACTIVO
        self.updated_at = datetime.now(timezone.utc)

    @property
    def esta_activo(self) -> bool:
        return self.estado == EstadoUsuario.ACTIVO
