from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Finance Tracker"
    database_url: str = "postgresql+psycopg://finance:finance@localhost:5432/finance"
    secret_key: str = "change-me"
    session_max_age: int = 60 * 60 * 24 * 7  # 7 days
    cookie_secure: bool = False  # True when behind HTTPS (Caddy)
    rp_id: str = "localhost"  # relying party id for WebAuthn
    rp_origin: str = "http://localhost:8000"
    admin_email: str = "admin@example.com"
    admin_password: str = "change-me"

    class Config:
        env_file = ".env"


settings = Settings()
