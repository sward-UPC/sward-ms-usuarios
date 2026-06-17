import logging

import httpx

from src.domain.ports.out_.lms_client_port import LmsClientPort
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
