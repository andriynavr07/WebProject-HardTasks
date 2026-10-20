from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./dev.db"
    secret_key: str = "change-me"
    admin_username: str = "admin"
    admin_password: str = "admin12345"
    cookie_secure: bool = False
    token_ttl_hours: int = 12
    worker_threads: int = 1

    # ліміти складності
    max_linear_n: int = 1500
    max_pixels: int = 4_000_000
    max_upload_bytes: int = 5 * 1024 * 1024
    max_kernel: int = 21
    max_passes: int = 5
    max_active_per_user: int = 3


settings = Settings()
