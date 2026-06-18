"""Vinculación determinística Moodle → SWARD.

El UUID de un usuario en SWARD se deriva de su `moodle_user_id` mediante uuid5
con un namespace fijo y compartido por todos los microservicios. Así el mismo
estudiante tiene el MISMO UUID en ms-usuarios y en ms-trazabilidad (que también
deriva `estudiante_id = uuid5(MOODLE_NS, "user:{moodle_user_id}")`), lo que
permite enriquecer/cruzar datos entre servicios sin un mapeo adicional.

NOTA: el namespace debe ser idéntico en todos los servicios. Idealmente vivirá
en `sward-shared`; por ahora se replica el mismo valor que usa ms-trazabilidad.
"""

from uuid import UUID, uuid5

MOODLE_NS = UUID("a9f3e7b5-1234-5678-abcd-ef0123456789")


def id_sward_desde_moodle(moodle_user_id: int) -> UUID:
    """UUID determinístico del usuario en SWARD a partir de su id de Moodle."""
    return uuid5(MOODLE_NS, f"user:{moodle_user_id}")
