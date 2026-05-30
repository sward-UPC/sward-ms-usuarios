from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.infrastructure.adapters.in_.admin_router import router as admin_router
from src.infrastructure.adapters.in_.auth_router import router as auth_router
from src.infrastructure.adapters.in_.users_router import router as users_router
from src.infrastructure.config.settings import settings
from src.infrastructure.db.database import engine
from src.infrastructure.db.models.audit_log_model import AuditLogModel  # noqa: F401
from src.infrastructure.db.models.role_model import PermissionModel, RoleModel  # noqa: F401
from src.infrastructure.db.models.user_model import Base, UserModel  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(title="SWARD — Microservicio de Usuarios", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(admin_router)


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": settings.service_name, "version": "0.1.0"}
