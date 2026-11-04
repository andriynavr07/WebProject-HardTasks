from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./dev.db"
    secret_key: str = "change-me"
    admin_username: str = "admin"
    admin_password: str = "admin12345"
    cookie_secure: bool = False
    token_ttl_hours: int = 12
    worker_threads: int = 1

    max_linear_n: int = 10000
    max_active_per_user: int = 6


settings = Settings()
