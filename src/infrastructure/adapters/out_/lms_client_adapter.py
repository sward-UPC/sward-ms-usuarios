import logging

import httpx

from src.application.ports.out_.lms_client_port import LmsClientPort
from src.infrastructure.config.settings import settings

logger = logging.getLogger(__name__)


class LmsClientAdapter(LmsClientPort):
    async def buscar_usuario_por_correo(self, correo: str) -> dict | None:
        url = f"{settings.lms_service_url}/lms/users/lookup"
        headers = {"X-Service-Key": settings.lms_service_key}
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url, params={"correo": correo}, headers=headers)
        except httpx.RequestError as exc:
            logger.error("Error llamando a ms-integracion-lms: %s", exc)
            raise RuntimeError("No se pudo contactar el servicio de integración LMS.") from exc

        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    async def provisionar_participante(self, correo: str, nombres: str, apellidos: str, password: str) -> dict:
        url = f"{settings.lms_service_url}/lms/users/provision"
        headers = {"X-Service-Key": settings.lms_service_key}
        try:
            # Más holgado que el lookup: crear la cuenta y matricular en dos cursos
            # son varias llamadas a Moodle, no una.
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    url,
                    json={
                        "correo": correo,
                        "nombres": nombres,
                        "apellidos": apellidos,
                        "password": password,
                    },
                    headers=headers,
                )
        except httpx.RequestError as exc:
            logger.error("Error provisionando en ms-integracion-lms: %s", exc)
            raise RuntimeError("No se pudo contactar el servicio de integración LMS.") from exc

        resp.raise_for_status()
        logger.info("Participante provisionado en Moodle: %s", correo)
        return resp.json()

    async def cambiar_password(self, correo: str, password: str) -> bool:
        url = f"{settings.lms_service_url}/lms/users/password"
        headers = {"X-Service-Key": settings.lms_service_key}
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.put(
                    url,
                    json={"correo": correo, "password": password},
                    headers=headers,
                )
                resp.raise_for_status()
                return bool(resp.json().get("cambiada", False))
        except httpx.HTTPError as e:
            # RuntimeError porque es lo que los routers traducen a 503. Se
            # propaga a propósito: si el aula virtual no acepta la contraseña
            # nueva, tampoco debe cambiarse aquí, o las dos se separan otra vez.
            raise RuntimeError(
                "No pudimos actualizar tu contraseña en el aula virtual. Inténtalo de nuevo en unos minutos."
            ) from e
