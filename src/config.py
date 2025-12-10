from pydantic_settings import BaseSettings, SettingsConfigDict
import os


class Settings(BaseSettings):
    # WhisperX
    HUG_TOKEN: str

    # Output
    # local
    OUTPUT_DIR: str = os.getcwd()
    # docker
    # OUTPUT_DIR: str = os.path.join(os.getcwd(), "uploads")  # Default to uploads subdirectory

    # Auth
    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int

    # DB
    DATABASE_URL: str

    # Ollama
    OLLAMA_API_URL: str = "http://0.0.0.0:11434"

    model_config = SettingsConfigDict(env_file="./env/.env")


settings = Settings()
