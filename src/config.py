from pydantic_settings import BaseSettings, SettingsConfigDict
import os


class Settings(BaseSettings):
    # WhisperX
    HUG_TOKEN: str

    # Output
    OUTPUT_DIR: str = os.getcwd()  # Default to current working directory

    # Auth
    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int

    # DB
    DATABASE_URL: str

    model_config = SettingsConfigDict(env_file="./env/.env")


settings = Settings()
