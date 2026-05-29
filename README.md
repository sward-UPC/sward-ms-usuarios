# sward-ms-usuarios

Microservicio de gestión de usuarios del sistema **SWARD**.  
Implementa autenticación JWT, registro, recuperación de contraseña y control de acceso basado en roles (RBAC).

## Arquitectura

Arquitectura **Hexagonal (Ports & Adapters)**:

```
src/
  domain/           # Usuario, Rol, Permiso, Sesion + puertos
  application/      # AutenticarUsuarioUseCase, RegistrarUsuarioUseCase...
  infrastructure/   # FastAPI routers, PostgresAdapter, JwtAdapter
```

## Stack

- Python 3.11 · FastAPI · SQLAlchemy 2.0 · Alembic · PostgreSQL
- python-jose (JWT) · passlib/bcrypt · Pydantic v2 · boto3

## Desarrollo local

```bash
cp .env.example .env
docker compose up -d db
alembic upgrade head
uvicorn src.infrastructure.adapters.in_.main:app --reload --port 8001
```

## Tests

```bash
pytest tests/ -v --cov=src
```

## Endpoints principales

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/auth/register` | Registro de usuario |
| POST | `/auth/login` | Login → JWT |
| POST | `/auth/logout` | Cierre de sesión |
| GET | `/users/{id}` | Perfil de usuario |
| GET | `/admin/users` | Lista de usuarios (admin) |

## Proyecto

**TP202610051** — Universidad Peruana de Ciencias Aplicadas (UPC)  
Taller de Proyecto 1 / 2026
