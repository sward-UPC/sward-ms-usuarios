from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4


@dataclass
class Notificacion:
    """Notificación dirigida a un usuario (estudiante, docente o admin).

    Las crea un productor externo (p. ej. lambda-notificaciones a partir de
    eventos de EventBridge) y las consume el usuario destinatario vía la API.
    """

    destinatario_id: UUID
    tipo: str = "general"  # feedback | alerta | logro | sistema | general
    titulo: str = ""
    mensaje: str = ""
    payload: dict[str, Any] | None = None
    leida: bool = False
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def marcar_leida(self) -> None:
        self.leida = True
