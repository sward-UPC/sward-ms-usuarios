from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.application.use_cases.gestionar_notificaciones import GestionarNotificacionesUseCase
from src.domain.entities.notificacion import Notificacion
from src.infrastructure.adapters.in_.middleware import get_current_user
from src.infrastructure.dependencies import get_gestionar_notificaciones_uc

router = APIRouter(prefix="/notifications", tags=["Notificaciones"])


def _notif_response(n: Notificacion) -> dict:
    return {
        "id": str(n.id),
        "tipo": n.tipo,
        "titulo": n.titulo,
        "mensaje": n.mensaje,
        "payload": n.payload,
        "leida": n.leida,
        "created_at": n.created_at.isoformat(),
    }


@router.get("", summary="Notificaciones del usuario autenticado")
async def listar_notificaciones(
    solo_no_leidas: bool = Query(default=False, description="Filtra solo las no leídas"),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    uc: GestionarNotificacionesUseCase = Depends(get_gestionar_notificaciones_uc),
):
    """Lista las notificaciones del usuario autenticado (las más recientes primero)
    junto con el conteo de no leídas.

    **Auth:** JWT requerido
    """
    items, no_leidas = await uc.listar(UUID(current_user["sub"]), solo_no_leidas=solo_no_leidas, limit=limit)
    return {
        "items": [_notif_response(n) for n in items],
        "no_leidas": no_leidas,
    }


@router.post("/{notif_id}/read", summary="Marca una notificación como leída")
async def marcar_leida(
    notif_id: UUID,
    current_user: dict = Depends(get_current_user),
    uc: GestionarNotificacionesUseCase = Depends(get_gestionar_notificaciones_uc),
):
    """Marca como leída una notificación propia. **Auth:** JWT requerido."""
    ok = await uc.marcar_leida(notif_id, UUID(current_user["sub"]))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notificación no encontrada.")
    return {"ok": True}


@router.post("/read-all", summary="Marca todas como leídas")
async def marcar_todas_leidas(
    current_user: dict = Depends(get_current_user),
    uc: GestionarNotificacionesUseCase = Depends(get_gestionar_notificaciones_uc),
):
    """Marca todas las notificaciones del usuario como leídas. **Auth:** JWT requerido."""
    n = await uc.marcar_todas_leidas(UUID(current_user["sub"]))
    return {"ok": True, "actualizadas": n}


@router.delete("/{notif_id}", summary="Elimina una notificación")
async def eliminar_notificacion(
    notif_id: UUID,
    current_user: dict = Depends(get_current_user),
    uc: GestionarNotificacionesUseCase = Depends(get_gestionar_notificaciones_uc),
):
    """Elimina una notificación propia. **Auth:** JWT requerido."""
    ok = await uc.eliminar(notif_id, UUID(current_user["sub"]))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notificación no encontrada.")
    return {"ok": True}
