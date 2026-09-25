from abc import ABC, abstractmethod


class LmsClientPort(ABC):
    @abstractmethod
    async def buscar_usuario_por_correo(self, correo: str) -> dict | None:
        """Retorna {moodle_user_id, nombre, apellido, correo, rol} o None si no existe."""
        ...

    @abstractmethod
    async def provisionar_participante(
        self, correo: str, nombres: str, apellidos: str
    ) -> dict:
        """Da de alta al participante en Moodle y lo matricula en los cursos del estudio.

        Se usa cuando alguien se registra en SWARD y todavía no existe en Moodle.
        Hasta el 24 de septiembre ese caso se rechazaba, porque las cuentas las creaba
        un script externo alimentado por un formulario.

        Retorna el mismo dict que `buscar_usuario_por_correo`.
        """
        ...
