from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UserModel(Base):
    __tablename__ = "users"
    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    correo_institucional: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    estado: Mapped[str] = mapped_column(String(50), nullable=False, default="activo")
    nombre: Mapped[str | None] = mapped_column(String(100), nullable=True)
    apellido: Mapped[str | None] = mapped_column(String(100), nullable=True)
    moodle_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avatar_color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # server_default ademas del default de Python: el seed del admin en la
    # migracion baseline inserta con SQL crudo, que no pasa por el ORM y por
    # tanto no aplica `default=True`. Sin el default a nivel de base, una BD
    # vacia falla con NotNullViolationError y el servicio no arranca nunca.
    notif_logros: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    # Consentimiento informado: la versión del texto aceptado y cuándo. Nullable
    # porque las cuentas creadas antes del 24-sep-2026 se dieron de alta con el
    # formulario externo, donde el consentimiento quedó registrado aparte.
    carrera: Mapped[str | None] = mapped_column(String(100), nullable=True)
    consentimiento_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    consentimiento_aceptado_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
