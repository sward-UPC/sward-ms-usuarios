# sward-ms-usuarios

Microservicio de **gestión de usuarios** de la plataforma **SWARD**. Es la
fuente de verdad de identidad del sistema: autenticación, control de acceso por
roles/permisos, panel de administración y notificaciones in-app.

## Qué hace

- **Autenticación JWT** — login con access token (15 min) + refresh token
  (7 días), rotación de tokens, logout selectivo por dispositivo y logout global,
  cambio de contraseña. Blacklist de tokens y rate-limit de intentos en Redis
  (bloqueo temporal tras 5 fallos).
- **Registro gated por Moodle** — un usuario solo puede registrarse si su correo
  institucional ya existe en Moodle (vía `ms-integracion-lms`). El rol
  (estudiante / docente), nombre y apellido se toman de Moodle; el cliente nunca
  elige su propio rol. El UUID del usuario es determinístico desde el
  `moodle_user_id` (coincide con el `estudiante_id` de `ms-trazabilidad` para
  cruzar datos entre servicios).
- **Roles y permisos (RBAC)** — estudiante, docente, administrador, con permisos
  cacheados en Redis y resueltos en cada token.
- **Panel de administración** — listado/búsqueda de usuarios, cambio de estado,
  asignación de roles, métricas y auditoría.
- **Notificaciones** — entrega in-app de eventos (p. ej. retroalimentación
  docente → estudiante), persistidas en Postgres.
- **Endpoint interno (s2s)** — resolución de perfiles por lista de UUID para
  otros microservicios.

Al autenticarse o registrarse se publican eventos de dominio
(`UsuarioAutenticadoEvent`, `UsuarioRegistradoEvent`) a **EventBridge**.

## Stack

- **Python 3.11** · **FastAPI** · **Uvicorn**
- **SQLAlchemy 2.0** (async, asyncpg) · **Alembic** · **PostgreSQL**
- **Redis** (cache de permisos, blacklist, intentos de login, refresh tokens)
- **PyJWT** (JWT) · **passlib** con argon2 + bcrypt (hashing de contraseñas)
- **Pydantic v2** / **pydantic-settings** · **boto3** (EventBridge) · **httpx**
  (cliente Moodle/LMS)
- **Scalar** para documentación interactiva de la API
- **sward-shared** (utilidades compartidas, p. ej. identidad determinística)

## Arquitectura hexagonal (Ports & Adapters)

El núcleo (`domain`, `application`) no conoce FastAPI, SQLAlchemy, Redis ni AWS.
Toda dependencia externa entra por un **puerto** (`domain/ports/out_`, definido
por el núcleo) y se implementa en un **adaptador de salida**
(`infrastructure/adapters/out_`). Los adaptadores de entrada (routers FastAPI)
viven en `infrastructure/adapters/in_`. La separación `in_` / `out_` preserva la
distinción driving/driven, que es el corazón del patrón.

```
src/
  application/
    use_cases/                      # casos de uso (orquestan puertos)
      autenticar_usuario.py
      registrar_usuario.py
      gestionar_usuarios.py
      gestionar_notificaciones.py
  domain/                           # NÚCLEO — sin dependencias de frameworks
    entities/                       # Usuario, Rol, Permiso, Notificacion, Sesion (@dataclass)
    value_objects/                  # EstadoUsuario
    events/                         # UsuarioAutenticadoEvent, UsuarioRegistradoEvent
    ports/
      out_/                         # contratos (ABC): repos, token, cache, eventos, LMS
  infrastructure/
    adapters/
      in_/                          # adaptadores de ENTRADA (FastAPI)
        main.py                     # app, middleware, exception handlers, /scalar, /health
        auth_router.py              # /auth
        users_router.py             # /users
        admin_router.py             # /admin
        notifications_router.py     # /notifications
        internal_router.py          # /internal (s2s)
        middleware.py               # get_current_user (JWT)
      out_/                         # adaptadores de SALIDA (implementan los puertos)
        usuario_postgres_adapter.py
        rol_postgres_adapter.py
        notificacion_postgres_adapter.py
        jwt_adapter.py
        redis_adapter.py
        eventbridge_adapter.py
        lms_client_adapter.py       # cliente HTTP a Moodle
        mock_lms_client_adapter.py  # mock para dev/test (USE_MOCK_LMS)
    config/settings.py              # configuración (pydantic-settings)
    db/                             # engine async + modelos ORM (separados del dominio)
      models/                       # UserModel, RoleModel, NotificationModel, AuditLogModel
    dependencies.py                 # composition root (cablea adaptadores a puertos)
```

**Tres representaciones del dato, separadas con mappers explícitos:** schemas
Pydantic (routers) ≠ entidades de dominio (`@dataclass`) ≠ modelos ORM
(`db/models`). Los errores de dominio (excepciones propias de cada use case) se
traducen a `HTTPException` en los routers; el núcleo nunca lanza errores HTTP.

> Para las convenciones detalladas y la auditoría de cumplimiento, ver
> `AUDIT_HEXAGONAL.md`.

## Endpoints principales (alto nivel)

| Método | Ruta | Descripción | Auth |
|--------|------|-------------|------|
| POST | `/auth/register` | Registro verificando identidad en Moodle | Público |
| POST | `/auth/login` | Login → access + refresh JWT | Público |
| POST | `/auth/refresh` | Nuevo access token desde refresh | Refresh token |
| POST | `/auth/logout` | Logout del dispositivo actual | JWT |
| POST | `/auth/logout-all-devices` | Logout en todos los dispositivos | JWT |
| POST | `/auth/change-password` | Cambio de contraseña | JWT |
| GET | `/users/me` | Perfil del usuario autenticado | JWT |
| PUT | `/users/me` | Actualiza perfil (avatar) | JWT |
| GET | `/users/{id}` | Perfil de un usuario | JWT |
| GET | `/admin/users` | Listado/búsqueda de usuarios | Admin |
| PATCH | `/admin/users/{id}` | Cambia estado de usuario | Admin |
| POST | `/admin/users/{id}/roles` | Asigna rol | Admin |
| GET | `/admin/metrics`, `/admin/audit` ... | Métricas y auditoría | Admin |
| GET | `/notifications` | Notificaciones del usuario | JWT |
| POST | `/notifications/{id}/read`, `/read-all` | Marca leídas | JWT |
| DELETE | `/notifications/{id}` | Elimina notificación | JWT |
| POST | `/internal/users/by-ids` | Perfiles por lista de UUID (s2s) | Service key |
| GET | `/health` | Health check | Público |
| GET | `/scalar` | Documentación interactiva de la API | Público |

## Variables de entorno

| Variable | Descripción | Ejemplo / default |
|----------|-------------|-------------------|
| `DATABASE_URL` | Postgres async (asyncpg) | `postgresql+asyncpg://sward:sward@localhost:5432/usuarios_db` |
| `SECRET_KEY` | Clave de firma JWT. Fuera de `development` debe tener ≥ 32 chars y no ser el default, o el servicio no arranca | — |
| `JWT_ALGORITHM` | Algoritmo de firma | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Vida del access token | `15` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Vida del refresh token | `7` |
| `REDIS_URL` | Conexión Redis | `redis://localhost:6379/0` |
| `PERMISSIONS_CACHE_TTL` | TTL del cache de permisos (s) | `600` |
| `LOGIN_ATTEMPTS_TTL` | Ventana de bloqueo por intentos (s) | `900` |
| `MAX_LOGIN_ATTEMPTS` | Intentos fallidos antes de bloquear | `5` |
| `AWS_REGION` | Región AWS | `us-east-1` |
| `EVENTBRIDGE_BUS_NAME` | Bus de EventBridge para publicar eventos | `sward-event-bus` |
| `ENVIRONMENT` | `development` / `production` | `development` |
| `SERVICE_NAME` | Nombre del servicio | `sward-ms-usuarios` |
| `AUTHORIZED_SERVICE_KEYS` | Claves para llamadas s2s al router `/internal` | — |

Genera un `SECRET_KEY` seguro con:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

## Desarrollo local

```bash
cp .env.example .env            # ajusta SECRET_KEY, etc.
docker compose up -d            # PostgreSQL + Redis
alembic upgrade head            # migraciones
uvicorn src.infrastructure.adapters.in_.main:app --reload --port 8001
```

Documentación interactiva en `http://localhost:8001/scalar`.

En desarrollo puede usarse un cliente Moodle simulado (`mock_lms_client_adapter`)
para no depender de `ms-integracion-lms`.

## Tests

```bash
python -m pytest -q              # unitarios + integración
ruff check                       # linting
```

Los tests unitarios (`tests/unit`) prueban los use cases con *fakes* en memoria
que cumplen los puertos (sin BD ni Redis reales). Los de integración
(`tests/integration`) levantan la app FastAPI y validan el cableado de los
endpoints.

## Flujo de deploy

CI/CD vía GitHub Actions, usando workflows reutilizables del repo
`sward-UPC/.github`:

- **CI** (`.github/workflows/ci.yml`) — corre en cada *push* y *pull request*
  contra `main`: ejecuta tests y linting (`ci-microservice.yml`).
- **Build & Push** (`.github/workflows/build-push.yml`) — corre al hacer *push* a
  la rama `deploy`: construye la imagen Docker, la publica en **GHCR**
  (`ghcr.io/sward-UPC/sward-ms-usuarios`) y dispara el despliegue del servicio
  **ECS** (`usuarios` en `sward-cluster`).

Flujo típico:

```
feature branch  ──PR──▶  main   (CI: tests + ruff)
       main      ──────▶  deploy (Build & Push → GHCR → ECS)
```

`needs_shared: true` indica que la imagen depende de `sward-shared`.

## Proyecto

**TP202610051** — Universidad Peruana de Ciencias Aplicadas (UPC) ·
Taller de Proyecto · 2026.
