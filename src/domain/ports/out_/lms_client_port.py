from abc import ABC, abstractmethod


class LmsClientPort(ABC):
    @abstractmethod
    async def buscar_usuario_por_correo(self, correo: str) -> dict | None:
        """Retorna {moodle_user_id, nombre, apellido, correo, rol} o None si no existe."""
        ...
