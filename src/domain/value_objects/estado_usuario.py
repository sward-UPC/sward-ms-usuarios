from enum import StrEnum


class EstadoUsuario(StrEnum):
    ACTIVO = "activo"
    INACTIVO = "inactivo"
    BLOQUEADO = "bloqueado"
    PENDIENTE_VERIFICACION = "pendiente_verificacion"
