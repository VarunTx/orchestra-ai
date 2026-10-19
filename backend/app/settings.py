from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    conductor_url: str = 'http://localhost:8080/api'
    control_plane_token: str = Field(min_length=32)
    gemini_api_key: str = ''
    gemini_model: str = 'gemini-2.5-flash'
    enable_gemini: bool = False
