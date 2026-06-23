import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from scalar_fastapi import get_scalar_api_reference

from src.infrastructure.adapters.in_.admin_router import router as admin_router
from src.infrastructure.adapters.in_.auth_router import router as auth_router
from src.infrastructure.adapters.in_.internal_router import router as internal_router
from src.infrastructure.adapters.in_.notifications_router import router as notifications_router
from src.infrastructure.adapters.in_.users_router import router as users_router
from src.infrastructure.config.settings import settings
from src.infrastructure.db.database import engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # El esquema y los datos base (roles y admin) los gestiona Alembic
    # (`alembic upgrade head` en el entrypoint del contenedor); aquí solo
    # liberamos el engine al apagar.
    yield
    await engine.dispose()


app = FastAPI(
    title="SWARD — Microservicio de Usuarios",
    version="0.1.0",
    openapi_url="/auth/openapi.json",
    description=(
        "Gestiona el registro, la autenticación (JWT) y la administración de "
        "usuarios, roles y permisos de la plataforma SWARD."
    ),
    lifespan=lifespan,
    openapi_tags=[
        {"name": "Autenticación", "description": "Registro, inicio y cierre de sesión, y emisión de tokens JWT."},
        {"name": "Usuarios", "description": "Consulta y gestión del perfil de los usuarios."},
        {"name": "Administración", "description": "Operaciones administrativas sobre roles y permisos."},
        {"name": "Notificaciones", "description": "Notificaciones del usuario (feedback, alertas, logros)."},
        {"name": "Health", "description": "Sonda de estado del servicio."},
    ],
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if not settings.is_development:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Error interno no controlado en %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Error interno del servidor."},
    )


app.include_router(auth_router)
app.include_router(users_router)
app.include_router(admin_router)
app.include_router(internal_router)
app.include_router(notifications_router)


@app.get("/scalar", include_in_schema=False)
async def scalar_docs():
    """Renderiza la referencia de API interactiva (Scalar) del servicio."""
    return get_scalar_api_reference(openapi_url=app.openapi_url, title=app.title)


@app.get("/health", tags=["Health"], summary="Estado del servicio")
async def health():
    """Devuelve el estado de salud del microservicio para sondas de liveness/readiness."""
    return {"status": "ok", "service": settings.service_name, "version": "0.1.0"}
