from src.domain.ports.out_.lms_client_port import LmsClientPort

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
