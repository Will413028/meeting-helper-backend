from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    HUG_TOKEN: str = "your_huggingface_token_here"

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()