from pydantic_settings import BaseSettings, SettingsConfigDict
import os


class Settings(BaseSettings):
    HUG_TOKEN: str = "REDACTED"
    OUTPUT_DIR: str = os.getcwd()  # Default to current working directory
    SECRET_KEY: str = "jindce9w5KEx4qBh9uN"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 43200

    model_config = SettingsConfigDict(env_file="./env/.env")


settings = Settings()
