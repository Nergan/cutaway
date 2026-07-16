from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parent

class Settings(BaseSettings):
    mongodb_uri: str = "mongodb://localhost:27017"
    mongo_tls: bool = True
    mongo_tls_allow_invalid_certificates: bool = False
    tags_yaml_path: str = str(_PROJECT_ROOT / "tags.yaml")

    cloudinary_cloud_name: str = ""
    cloudinary_api_key: str = ""
    cloudinary_api_secret: str = ""

    max_media_items: int = 10
    max_bio_length: int = 200
    max_upload_bytes: int = 25 * 1024 * 1024
    image_max_dimension: int = 1600
    audio_bitrate: str = "96k"
    
    pow_difficulty: int = 4
    bot_protection_delay: float = 0.5

    admin_api_key: str = ""
    trusted_bot_ips: str = "" # Comma-separated Render static IPs for the Telegram bot

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()