from pydantic_settings import BaseSettings
from functools import lru_cache
from pathlib import Path
import logging
# Add the project root to sys.path
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent.parent
class Settings(BaseSettings):
    
    DB_HOST: str
    DB_PORT: int
    DB_NAME: str
    DB_USER: str
    DB_PASSWORD: str
    DB_POOL_MIN: int = 1
    DB_POOL_MAX: int = 10
    
    REDIS_HOST: str
    REDIS_PORT: int
    REDIS_DB: int = 0
    REDIS_POOL_MAX_CONN: int = 15
    REDIS_PASSWORD: str | None = None
    
    SOLVER_PATH_SLOW: str = "./bin/satsolver"
    SOLVER_PATH_FAST: str = "./bin/satsolver_opt"
    DEFAULT_TIMEOUT_MS: int = 250_000
    MAX_TIMEOUT_MS: int = 300_000
    
    MAX_FORMULA_LENGTH : int = 300_000
    MAX_TOKENS : int = 85_000
    
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-2.5-flash-lite"
    
    class Config:
        env_file = str(BASE_DIR / ".env.dev")
        env_file_encoding = "utf-8"
    
@lru_cache
def get_settings() -> Settings:
    logger.info("Loading application settings.")
    return Settings()

settings = get_settings()