"""Contratos HTTP del concern interno service-to-service (s2s)."""

from uuid import UUID

from pydantic import BaseModel, Field


class UsersByIdsRequest(BaseModel):
    ids: list[UUID] = Field(..., description="Lista de UUIDs de usuarios a consultar")


class InternalUserResponse(BaseModel):
    """Perfil mínimo de usuario expuesto a otros microservicios (s2s)."""

    id: str = Field(..., description="UUID del usuario")
    correo: str = Field(..., description="Correo institucional")
    nombre: str | None = Field(None, description="Nombre")
    apellido: str | None = Field(None, description="Apellido")
    moodle_user_id: int | None = Field(None, description="ID del usuario en Moodle")
