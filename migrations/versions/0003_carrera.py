"""carrera declarada al registrarse

El formulario externo pedía la carrera para describir la muestra del estudio. Al
trasladar el alta al propio sistema, el dato tenía que tener dónde vivir.

Es puramente descriptivo: no interviene en permisos, ni en el rol, ni en las
recomendaciones. Nullable, porque las cuentas anteriores a esta fecha se crearon
sin él.

Revision ID: 0003_carrera
Revises: 0002_consentimiento
Create Date: 2026-09-24
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_carrera"
down_revision = "0002_consentimiento"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("carrera", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "carrera")
