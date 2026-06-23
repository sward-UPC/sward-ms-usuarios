"""Contratos Pydantic (Request/Response) del adaptador de entrada HTTP.

Organizados por concern (auth, users, admin, notifications, internal) en vez de
inline en cada router, según buenas prácticas de organización. Se re-exportan
aquí para que las rutas importen desde `...adapters.in_.schemas` sin conocer el
submódulo.
"""

from .admin import (
    AssignRoleRequest,
    AssignRoleResponse,
    AuditLogResponse,
    DatabaseHealthResponse,
    MetricsResponse,
    ModelConfigResponse,
    RetrainResponse,
    ServiceHealthResponse,
    SystemMetricsResponse,
    SystemStatusResponse,
    UpdateStatusRequest,
    UpdateStatusResponse,
    UsuarioAdminResponse,
    UsuarioListResponse,
    UsuariosPorRolResponse,
)
from .auth import (
    AccessTokenResponse,
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UsuarioRegistradoResponse,
)
from .internal import InternalUserResponse, UsersByIdsRequest
from .notifications import (
    NotificacionesListResponse,
    NotificacionResponse,
    OkResponse,
    ReadAllResponse,
)
from .users import (
    ActualizarPerfilRequest,
    DeleteCuentaResponse,
    PerfilResponse,
    PreferenciasRequest,
)

__all__ = [
    # auth
    "RegisterRequest",
    "LoginRequest",
    "TokenResponse",
    "UsuarioRegistradoResponse",
    "RefreshRequest",
    "AccessTokenResponse",
    "ChangePasswordRequest",
    # users
    "PreferenciasRequest",
    "ActualizarPerfilRequest",
    "PerfilResponse",
    "DeleteCuentaResponse",
    # admin
    "UpdateStatusRequest",
    "AssignRoleRequest",
    "UsuarioAdminResponse",
    "UsuarioListResponse",
    "UpdateStatusResponse",
    "AssignRoleResponse",
    "UsuariosPorRolResponse",
    "MetricsResponse",
    "AuditLogResponse",
    "ServiceHealthResponse",
    "SystemStatusResponse",
    "SystemMetricsResponse",
    "ModelConfigResponse",
    "RetrainResponse",
    "DatabaseHealthResponse",
    # notifications
    "NotificacionResponse",
    "NotificacionesListResponse",
    "OkResponse",
    "ReadAllResponse",
    # internal
    "UsersByIdsRequest",
    "InternalUserResponse",
]
