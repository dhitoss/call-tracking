"""
Configurações da aplicação usando Pydantic Settings.
Gerencia variáveis de ambiente de forma type-safe.
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Configurações gerais da aplicação."""
    
    # Supabase
    SUPABASE_URL: str
    SUPABASE_KEY: str
    
    # Twilio
    TWILIO_ACCOUNT_SID: str
    TWILIO_AUTH_TOKEN: str
    
    # Flask
    FLASK_SECRET_KEY: str
    FLASK_HOST: str = "0.0.0.0"
    FLASK_PORT: int = 5000
    FLASK_DEBUG: bool = False
    
    # App Settings
    DEFAULT_TIMEZONE: str = "America/Sao_Paulo"
    CACHE_TTL: int = 300  # 5 minutos
    
    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """
    Retorna instância singleton das configurações.
    Cached para evitar recarregar .env múltiplas vezes.
    """
    return Settings()


# Convenience export
settings = get_settings()