from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID, uuid4


class TipoRol(StrEnum):
    ESTUDIANTE = "estudiante"
    DOCENTE = "docente"
    ADMINISTRADOR = "administrador"


@dataclass
class Permiso:
    id: UUID = field(default_factory=uuid4)
    codigo: str = ""
    descripcion: str = ""


@dataclass
class Rol:
    id: UUID = field(default_factory=uuid4)
    nombre: TipoRol = TipoRol.ESTUDIANTE
    descripcion: str = ""
    permisos: list[Permiso] = field(default_factory=list)
