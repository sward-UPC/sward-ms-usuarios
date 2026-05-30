# PROGRESS — sward-ms-usuarios

## Sprint 1 — 2026-05-29

### Implementado
- [x] Dominio: Usuario, Rol, Permiso, Sesion
- [x] Value objects: EstadoUsuario, TipoRol
- [x] Eventos: UsuarioAutenticadoEvent, UsuarioRegistradoEvent
- [x] Puertos: UsuarioRepositoryPort, RolRepositoryPort, TokenPort, CachePort, EventPublisherPort
- [x] Use Case: AutenticarUsuarioUseCase (JWT 15min, Redis lockout, cache permisos)
- [x] Use Case: RegistrarUsuarioUseCase (bcrypt, validación ISO 27001)
- [x] JwtAdapter: access 15min + refresh 7d
- [x] RedisAdapter: permisos, blacklist, login_attempts, refresh tokens
- [x] UsuarioPostgresAdapter, RolPostgresAdapter
- [x] EventBridgeAdapter (dev: log local)
- [x] Routers: /auth, /users, /admin
- [x] SQLAlchemy models: users, roles, permissions, user_roles, audit_logs
- [x] Docker Compose: PostgreSQL 15 + Redis 7
- [x] Tests unitarios: 6 tests (3 autenticar + 3 registrar)

### Pendiente
- [ ] RecuperarPasswordUseCase (requiere SMTP)
- [ ] GitHub Actions CI
- [ ] Alembic migrations formales
