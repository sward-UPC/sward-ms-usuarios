from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.db.models.user_model import Base


class NotificationModel(Base):
    __tablename__ = "notificaciones"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    destinatario_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    tipo: Mapped[str] = mapped_column(String(50), nullable=False, default="general")
    titulo: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    mensaje: Mapped[str] = mapped_column(Text, nullable=False, default="")
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    leida: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
