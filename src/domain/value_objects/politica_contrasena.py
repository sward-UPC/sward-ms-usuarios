"""Reglas que debe cumplir una contraseña nueva.

Viven en el dominio porque las aplican varios casos de uso —el registro y el
restablecimiento tras recuperar la cuenta— y deben ser las mismas en ambos.
"""


def validar_contrasena(password: str) -> None:
    """Lanza ValueError con todas las reglas incumplidas, si hay alguna."""
    errores = []
    if len(password) < 8:
        errores.append("mínimo 8 caracteres")
    if not any(c.isupper() for c in password):
        errores.append("al menos una mayúscula")
    if not any(c.isdigit() for c in password):
        errores.append("al menos un número")
    if errores:
        raise ValueError(f"Contraseña insegura: {', '.join(errores)}")
