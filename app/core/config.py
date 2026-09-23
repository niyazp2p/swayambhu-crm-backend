from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import computed_field


class Settings(BaseSettings):
    PROJECT_NAME: str = "Swayambhu Waste Management CRM"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # Primary Cloud Database Connection String (Neon, Render, Supabase)
    DATABASE_URL: str | None = None

    # Fallback individual parameters for local docker compose runs
    POSTGRES_SERVER: str | None = "localhost"
    POSTGRES_USER: str | None = "postgres"
    POSTGRES_PASSWORD: str | None = "postgrespassword"
    POSTGRES_DB: str | None = "waste_crm"
    POSTGRES_PORT: int = 5432

    @computed_field
    @property
    def async_database_url(self) -> str:
        """
        Ensures SQLAlchemy async engine receives the `postgresql+asyncpg://` dialect.
        Handles query parameters like `?sslmode=require` safely.
        """
        raw_url = self.DATABASE_URL
        if not raw_url:
            raw_url = (
                f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
                f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            )

        if raw_url.startswith("postgresql+asyncpg://"):
            return raw_url
        if raw_url.startswith("postgresql://"):
            return raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if raw_url.startswith("postgres://"):
            return raw_url.replace("postgres://", "postgresql+asyncpg://", 1)
        return raw_url

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()