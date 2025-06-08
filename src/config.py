from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    HUG_TOKEN: str = "REDACTED"

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()