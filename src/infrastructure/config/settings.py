from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SECRET_KEY = "dev-secret-change-in-production"
MIN_SECRET_KEY_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql+asyncpg://sward:sward@localhost:5432/usuarios_db"
    # Componentes inyectados por ECS task definition (CDK via Secrets Manager).
    db_username: str = ""
    db_password: str = ""
    database_host: str = ""
    database_port: str = "5432"
    database_name: str = ""

    secret_key: str = DEFAULT_SECRET_KEY
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    redis_url: str = "redis://localhost:6379/0"
    permissions_cache_ttl: int = 600
    login_attempts_ttl: int = 900
    max_login_attempts: int = 5
    aws_region: str = "us-east-1"
    eventbridge_bus_name: str = "sward-event-bus"
    environment: str = "development"
    service_name: str = "sward-ms-usuarios"
    authorized_service_keys: str = ""
    cors_allowed_origins: list[str] = ["http://localhost:5173"]

    # Integración interna con ms-integracion-lms
    lms_service_url: str = "http://integracion-lms.sward.local:8000"
    lms_service_key: str = "dev-lms-key"
    use_mock_lms: bool = True

    # Seed de administrador inicial (solo corre si ambas están definidas)
    admin_seed_email: str = "admin@sward.upc.edu.pe"
    admin_seed_password: str = ""

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @model_validator(mode="after")
    def _compose_database_url(self) -> "Settings":
        if self.database_host and self.db_username:
            self.database_url = (
                f"postgresql+asyncpg://{self.db_username}:{self.db_password}"
                f"@{self.database_host}:{self.database_port}/{self.database_name}"
            )
        return self

    @model_validator(mode="after")
    def _validar_secret_key(self) -> "Settings":
        """Impide arrancar fuera de development con un secret_key inseguro.

        En cualquier entorno distinto de "development" el secret_key no puede
        ser el valor por defecto ni tener menos de 32 caracteres. En desarrollo
        el default se permite para facilitar el arranque local.
        """
        if self.environment == "development":
            return self
        if self.secret_key == DEFAULT_SECRET_KEY:
            raise ValueError(
                "SECRET_KEY inseguro: no se permite el valor por defecto fuera de "
                f"development (environment={self.environment!r}). Genera uno seguro con "
                '`python -c "import secrets; print(secrets.token_urlsafe(64))"`.'
            )
        if len(self.secret_key) < MIN_SECRET_KEY_LENGTH:
            raise ValueError(
                f"SECRET_KEY inseguro: debe tener al menos {MIN_SECRET_KEY_LENGTH} "
                f"caracteres fuera de development (environment={self.environment!r}). "
                'Genera uno seguro con `python -c "import secrets; '
                'print(secrets.token_urlsafe(64))"`.'
            )
        return self


settings = Settings()
