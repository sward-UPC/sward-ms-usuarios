from dataclasses import dataclass, field
from uuid import UUID, uuid4

from sward_shared.events.domain_event import DomainEvent


@dataclass
class UsuarioAutenticadoEvent(DomainEvent):
    usuario_id: UUID = field(default_factory=uuid4)
    rol: str = ""
    correo: str = ""
    source: str = "sward-ms-usuarios"

    @property
    def event_type(self) -> str:
        return "sward.usuarios.UsuarioAutenticado"
