"""baseline: esquema inicial de usuarios + datos base (roles y admin)

Adopta el esquema existente. Crea todas las tablas del modelo con
``checkfirst=True``, de modo que:
  - en una BD nueva crea todo desde cero;
  - en la BD compartida de dev (que ya tiene las tablas creadas por el antiguo
    ``create_all`` + los ALTER inline) NO toca nada y solo registra la versión.

Además siembra los datos base que antes insertaba el arranque de la app
(``_seed_roles`` / ``_seed_admin``): los tres roles de la plataforma y, si
``ADMIN_SEED_PASSWORD`` está configurado, el usuario administrador inicial.
Ambos seeds son idempotentes.

A partir de aquí, todo cambio de esquema (nuevas columnas/tablas/índices) debe
ir en su propia revisión Alembic, no como DDL inline en el arranque.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-06-23
"""

import logging
from collections.abc import Sequence
from uuid import uuid4

from alembic import op
from sqlalchemy import text

from src.infrastructure.config.settings import settings

# Importar todos los modelos asegura que sus tablas queden registradas en
# Base.metadata antes del create_all.
from src.infrastructure.db.models.audit_log_model import AuditLogModel  # noqa: F401
from src.infrastructure.db.models.notification_model import NotificationModel  # noqa: F401
from src.infrastructure.db.models.role_model import PermissionModel, RoleModel  # noqa: F401
from src.infrastructure.db.models.user_model import Base, UserModel  # noqa: F401

logger = logging.getLogger("alembic.runtime.migration")

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ROLES = [
    ("estudiante", "Estudiante de la plataforma"),
    ("docente", "Docente de la plataforma"),
    ("administrador", "Administrador del sistema"),
]


def _seed_roles(conn) -> None:
    """Inserta los roles base si no existen. Idempotente."""
    for nombre, descripcion in _ROLES:
        existing = conn.execute(
            text("SELECT id FROM roles WHERE nombre = :nombre"),
            {"nombre": nombre},
        ).fetchone()
        if not existing:
            conn.execute(
                text("INSERT INTO roles(id, nombre, descripcion) VALUES(:id, :nombre, :descripcion)"),
                {"id": uuid4(), "nombre": nombre, "descripcion": descripcion},
            )


def _seed_admin(conn) -> None:
    """Crea el usuario administrador inicial si no existe. Idempotente.

    Omitido si ``ADMIN_SEED_PASSWORD`` no está configurado.
    """
    correo = getattr(settings, "admin_seed_email", "admin@sward.upc.edu.pe")
    password = getattr(settings, "admin_seed_password", None)
    if not password:
        return

    from passlib.context import CryptContext

    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    pw_hash = pwd_ctx.hash(password)

    row = conn.execute(
        text("SELECT id FROM users WHERE correo_institucional = :correo"),
        {"correo": correo},
    ).fetchone()
    if row:
        uid = row[0]
    else:
        uid = uuid4()
        conn.execute(
            text(
                "INSERT INTO users"
                "(id, correo_institucional, password_hash, estado,"
                " nombre, apellido, created_at, updated_at)"
                " VALUES(:id, :correo, :pw, 'activo', 'Admin', 'SWARD', NOW(), NOW())"
            ),
            {"id": uid, "correo": correo, "pw": pw_hash},
        )

    rol_row = conn.execute(text("SELECT id FROM roles WHERE nombre = 'administrador'")).fetchone()
    if rol_row:
        conn.execute(
            text("INSERT INTO user_roles(user_id, role_id) VALUES(:uid, :rid) ON CONFLICT DO NOTHING"),
            {"uid": uid, "rid": rol_row[0]},
        )


def upgrade() -> None:
    bind = op.get_bind()
    # checkfirst=True -> idempotente sobre BD existente (no recrea tablas).
    Base.metadata.create_all(bind=bind, checkfirst=True)
    _seed_roles(bind)
    _seed_admin(bind)


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
