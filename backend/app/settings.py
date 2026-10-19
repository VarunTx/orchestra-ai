from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    conductor_url: str = ''
    conductor_host: str = 'localhost'
    control_plane_token: str = Field(min_length=32)
    gemini_api_key: str = ''
    gemini_model: str = 'gemini-2.5-flash'
    enable_gemini: bool = False

    @model_validator(mode="after")
    def resolve_conductor(self):
        if not self.conductor_url:
            self.conductor_url = f"http://{self.conductor_host}:8080/api"
        return self
