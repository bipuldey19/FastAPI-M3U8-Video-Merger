"""
Configuration settings for production deployment
"""
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # Application settings
    APP_NAME: str = "M3U8 Video Merger API"
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 2  # Reduced for ARM/free tier
    LOG_LEVEL: str = "INFO"
    
    # API settings
    ENABLE_DOCS: bool = False  # Disable in production
    API_PREFIX: str = "/api"
    RATE_LIMIT_PER_MINUTE: int = 10
    MAX_VIDEOS_PER_REQUEST: int = 10  # Reduced for free tier
    
    # Redis settings
    REDIS_URL: str = "redis://localhost:6379/0"
    JOB_RETENTION_SECONDS: int = 86400  # 24 hours
    
    # Video settings
    REELS_WIDTH: int = 1080
    REELS_HEIGHT: int = 1920
    FFMPEG_PRESET: str = "veryfast"  # Faster for ARM
    FFMPEG_CRF: int = 28  # Slightly lower quality for performance
    
    # Security settings
    ALLOWED_ORIGINS: List[str] = ["*"]  # Configure for production
    TRUSTED_HOSTS: List[str] = ["*"]  # Configure for production
    
    # File management
    OUTPUT_DIR: str = "output"
    TEMP_DIR: str = "temp"
    LOG_DIR: str = "logs"
    MAX_OUTPUT_FILE_AGE_HOURS: int = 24
    
    # Download settings
    DOWNLOAD_TIMEOUT: int = 300  # seconds
    MAX_RETRIES: int = 3
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
