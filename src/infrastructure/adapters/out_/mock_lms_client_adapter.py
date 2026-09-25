from src.application.ports.out_.lms_client_port import LmsClientPort

_MOCK_USERS: dict[str, dict] = {
    "estudiante01@sward.edu": {
        "moodle_user_id": 7,
        "nombre": "Estudiante",
        "apellido": "Uno",
        "correo": "estudiante01@sward.edu",
        "rol": "estudiante",
    },
    "estudiante02@sward.edu": {
        "moodle_user_id": 8,
        "nombre": "Estudiante",
        "apellido": "Dos",
        "correo": "estudiante02@sward.edu",
        "rol": "estudiante",
    },
    "docente01@sward.edu": {
        "moodle_user_id": 2,
        "nombre": "Docente",
        "apellido": "Uno",
        "correo": "docente01@sward.edu",
        "rol": "docente",
    },
}


class MockLmsClientAdapter(LmsClientPort):
    async def buscar_usuario_por_correo(self, correo: str) -> dict | None:
        return _MOCK_USERS.get(correo.lower())

    async def provisionar_participante(
        self, correo: str, nombres: str, apellidos: str
    ) -> dict:
        # El mock da de alta de verdad sobre su diccionario: así una prueba puede
        # registrar a alguien nuevo y después encontrarlo.
        correo = correo.lower()
        if correo in _MOCK_USERS:
            return _MOCK_USERS[correo]
        nuevo = {
            "moodle_user_id": max((u["moodle_user_id"] for u in _MOCK_USERS.values()), default=100) + 1,
            "nombre": nombres,
            "apellido": apellidos,
            "correo": correo,
            "rol": "estudiante",
        }
        _MOCK_USERS[correo] = nuevo
        return nuevo
