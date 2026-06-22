import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from scalar_fastapi import get_scalar_api_reference
from sqlalchemy import text

from src.infrastructure.adapters.in_.admin_router import router as admin_router
from src.infrastructure.adapters.in_.auth_router import router as auth_router
from src.infrastructure.adapters.in_.internal_router import router as internal_router
from src.infrastructure.adapters.in_.notifications_router import router as notifications_router
from src.infrastructure.adapters.in_.users_router import router as users_router
from src.infrastructure.config.settings import settings
from src.infrastructure.db.database import engine
from src.infrastructure.db.models.audit_log_model import AuditLogModel  # noqa: F401
from src.infrastructure.db.models.notification_model import NotificationModel  # noqa: F401
from src.infrastructure.db.models.role_model import PermissionModel, RoleModel  # noqa: F401
from src.infrastructure.db.models.user_model import Base, UserModel  # noqa: F401

logger = logging.getLogger(__name__)


async def _migrate_columns() -> None:
    """Agrega columnas nuevas a tablas existentes sin romper datos previos."""
    migrations = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS nombre VARCHAR(100)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS apellido VARCHAR(100)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS moodle_user_id INTEGER",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_color VARCHAR(20)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS notif_logros BOOLEAN NOT NULL DEFAULT TRUE",
    ]
    async with engine.begin() as conn:
        for stmt in migrations:
            await conn.execute(text(stmt))


async def _seed_roles() -> None:
    """Inserta los roles base si no existen. Idempotente."""
    from uuid import uuid4

    roles = [
        ("estudiante", "Estudiante de la plataforma"),
        ("docente", "Docente de la plataforma"),
        ("administrador", "Administrador del sistema"),
    ]
    async with engine.begin() as conn:
        for nombre, descripcion in roles:
            existing = await conn.execute(
                text("SELECT id FROM roles WHERE nombre = :nombre"),
                {"nombre": nombre},
            )
            if not existing.fetchone():
                await conn.execute(
                    text("INSERT INTO roles(id, nombre, descripcion) VALUES(:id, :nombre, :descripcion)"),
                    {"id": uuid4(), "nombre": nombre, "descripcion": descripcion},
                )
                logger.info("Roles seed: rol '%s' creado.", nombre)


async def _seed_admin() -> None:
    """Crea el usuario administrador inicial si no existe. Idempotente."""
    from uuid import uuid4

    from passlib.context import CryptContext
    from sqlalchemy import text

    from src.infrastructure.config.settings import settings

    correo = getattr(settings, "admin_seed_email", "admin@sward.upc.edu.pe")
    password = getattr(settings, "admin_seed_password", None)
    if not password:
        logger.info("Admin seed: ADMIN_SEED_PASSWORD no configurado, omitiendo.")
        return

    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    pw_hash = pwd_ctx.hash(password)

    async with engine.begin() as conn:
        existing = await conn.execute(
            text("SELECT id FROM users WHERE correo_institucional = :correo"),
            {"correo": correo},
        )
        row = existing.fetchone()
        if row:
            uid = row[0]
            logger.info("Admin seed: usuario %s ya existe, verificando rol.", correo)
        else:
            uid = uuid4()
            await conn.execute(
                text(
                    "INSERT INTO users"
                    "(id, correo_institucional, password_hash, estado,"
                    " nombre, apellido, created_at, updated_at)"
                    " VALUES(:id, :correo, :pw, 'activo', 'Admin', 'SWARD', NOW(), NOW())"
                ),
                {"id": uid, "correo": correo, "pw": pw_hash},
            )

        rol = await conn.execute(text("SELECT id FROM roles WHERE nombre = 'administrador'"))
        rol_row = rol.fetchone()
        if rol_row:
            await conn.execute(
                text("INSERT INTO user_roles(user_id, role_id) VALUES(:uid, :rid) ON CONFLICT DO NOTHING"),
                {"uid": uid, "rid": rol_row[0]},
            )
            logger.info("Admin seed: usuario %s creado con rol administrador.", correo)
        else:
            logger.warning("Admin seed: tabla roles vacía, no se asignó rol administrador.")


async def _init_db() -> None:
    for intento in range(10):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            await _migrate_columns()
            await _seed_roles()
            await _seed_admin()
            logger.info("Base de datos lista.")
            return
        except Exception as exc:
            logger.warning("BD no disponible (intento %d/10): %s", intento + 1, exc)
            await asyncio.sleep(5)
    logger.error("No se pudo conectar a la BD tras 10 intentos.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(_init_db())
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
