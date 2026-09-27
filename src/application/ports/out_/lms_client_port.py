from abc import ABC, abstractmethod


class LmsClientPort(ABC):
    @abstractmethod
    async def buscar_usuario_por_correo(self, correo: str) -> dict | None:
        """Retorna {moodle_user_id, nombre, apellido, correo, rol} o None si no existe."""
        ...

    @abstractmethod
    async def provisionar_participante(self, correo: str, nombres: str, apellidos: str) -> dict:
        """Da de alta al participante en Moodle y lo matricula en los cursos del estudio.

        Se usa cuando alguien se registra en SWARD y todavía no existe en Moodle.
        Hasta el 24 de septiembre ese caso se rechazaba, porque las cuentas las creaba
        un script externo alimentado por un formulario.

        Se envía **la contraseña que la persona acaba de elegir**, para que le sirva
        también en el aula virtual. Desde el 27 de septiembre: antes Moodle generaba
        una temporal y se la mandaba por correo, y el participante acababa con tres
        contraseñas y dos reglamentos distintos. No se registra en ningún log.

        Retorna el mismo dict que `buscar_usuario_por_correo`.
        """
        ...

    @abstractmethod
    async def cambiar_password(self, correo: str, password: str) -> bool:
        """Lleva al aula virtual la contraseña que la persona acaba de fijar aquí.

        Sin esto, «una sola contraseña» valía sólo hasta el primer cambio: el alta
        la copia una vez y a partir de ahí las dos cuentas se separan en silencio.
        Se encontró el 27 de septiembre de 2026.

        Devuelve False si esa persona no existe en Moodle, que no es un error.
        """
        ...
