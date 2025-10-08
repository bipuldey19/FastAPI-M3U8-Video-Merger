from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    # App
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 1
    LOG_LEVEL: str = "INFO"
    
    # API
    ENABLE_DOCS: bool = False
    RATE_LIMIT_PER_MINUTE: int = 10
    MAX_VIDEOS_PER_REQUEST: int = 10
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    JOB_RETENTION_SECONDS: int = 86400
    
    # Video
    REELS_WIDTH: int = 1080
    REELS_HEIGHT: int = 1920
    FFMPEG_PRESET: str = "veryfast"
    FFMPEG_CRF: int = 28
    
    # Security
    ALLOWED_ORIGINS: List[str] = ["*"]
    TRUSTED_HOSTS: List[str] = ["*"]
    
    # Files
    OUTPUT_DIR: str = "output"
    TEMP_DIR: str = "temp"
    LOG_DIR: str = "logs"
    
    # Download
    DOWNLOAD_TIMEOUT: int = 300
    MAX_RETRIES: int = 3
    
    class Config:
        env_file = ".env"

settings = Settings()
