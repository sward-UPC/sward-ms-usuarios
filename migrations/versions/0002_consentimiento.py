"""consentimiento informado en el registro

Hasta ahora el consentimiento de los participantes del estudio se recogía en un
formulario de Google externo al sistema, y las cuentas de Moodle las creaba un
script a partir de ese CSV. Desde el 24 de septiembre de 2026 el registro de
SWARD da de alta al participante y recoge su consentimiento, de modo que la
aceptación tiene que quedar guardada aquí.

Se guarda la **versión** del texto aceptado, no un booleano: si el texto cambia
hay que poder acreditar cuál aceptó cada persona, que es lo que exige la Ley
29733 para sostener el consentimiento.

Ambas columnas son nullable: las cuentas anteriores a esta fecha se crearon con
el formulario, donde la aceptación quedó registrada por separado, y no se les
puede inventar una versión ni una fecha.

Revision ID: 0002_consentimiento
Revises: 0001_baseline
Create Date: 2026-09-24
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_consentimiento"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("consentimiento_version", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "consentimiento_aceptado_en", sa.DateTime(timezone=True), nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "consentimiento_aceptado_en")
    op.drop_column("users", "consentimiento_version")
