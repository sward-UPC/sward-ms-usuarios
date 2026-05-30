from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4


@dataclass
class Sesion:
    id: UUID = field(default_factory=uuid4)
    usuario_id: UUID = field(default_factory=uuid4)
    jwt_id: str = ""
    refresh_token_hash: str = ""
    device_id: str = "default"
    expira_en: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    activa: bool = True

    def invalidar(self) -> None:
        self.activa = False
