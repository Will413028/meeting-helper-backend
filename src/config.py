from pydantic_settings import BaseSettings, SettingsConfigDict
import os


class Settings(BaseSettings):
    HUG_TOKEN: str = "REDACTED"
    OUTPUT_DIR: str = os.getcwd()  # Default to current working directory

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
