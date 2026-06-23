"""Contratos HTTP del concern de notificaciones del usuario."""

from typing import Any

from pydantic import BaseModel, Field


class NotificacionResponse(BaseModel):
    """Una notificación dirigida al usuario."""

    id: str = Field(..., description="UUID de la notificación")
    tipo: str = Field(..., description="Tipo (feedback, alerta, logro, sistema, general)")
    titulo: str = Field(..., description="Título de la notificación")
    mensaje: str = Field(..., description="Cuerpo de la notificación")
    payload: dict[str, Any] | None = Field(None, description="Datos adicionales asociados")
    leida: bool = Field(..., description="Si ya fue leída por el usuario")
    created_at: str = Field(..., description="Fecha de creación (ISO 8601)")


class NotificacionesListResponse(BaseModel):
    """Lista de notificaciones más el conteo de no leídas."""

    items: list[NotificacionResponse]
    no_leidas: int = Field(..., description="Cantidad de notificaciones sin leer")


class OkResponse(BaseModel):
    """Confirmación genérica de operación exitosa."""

    ok: bool = Field(True, description="True si la operación se completó")


class ReadAllResponse(BaseModel):
    """Confirmación de marcar todas como leídas."""

    ok: bool = Field(True, description="True si la operación se completó")
    actualizadas: int = Field(..., description="Número de notificaciones marcadas como leídas")
