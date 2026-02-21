# flask_api_face/app/config.py

import os
from dotenv import load_dotenv

# Panggil load_dotenv() di awal untuk memuat file .env
load_dotenv()

class BaseConfig:
    # Nilai default atau placeholder
    DATABASE_URL = ''
    TIMEZONE = 'Asia/Makassar'
    DEFAULT_GEOFENCE_RADIUS = 100

    # Nextcloud configuration. Provide your instance URL and credentials here.
    # NEXTCLOUD_URL can be the full WebDAV endpoint or the instance root; the
    # storage layer will resolve the proper path. See
    # `app/services/storage/nextcloud_storage.py` for details.
    NEXTCLOUD_URL = ""
    NEXTCLOUD_USER = ""
    NEXTCLOUD_PASS = ""
    NEXTCLOUD_DEFAULT_FOLDER = "uploads"

    MODEL_NAME = "buffalo_s"
    SIGNED_URL_EXPIRES = 604800
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    JSON_SORT_KEYS = False
    
    # Konfigurasi Celery
    CELERY_BROKER_URL = 'redis://localhost:6379/0'
    CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'

    # Additional service-specific configuration placeholders can be defined here.

class DevConfig(BaseConfig):
    DEBUG = True

class ProdConfig(BaseConfig):
    DEBUG = False

def load_config(app):
    """Memuat konfigurasi berdasarkan lingkungan dan variabel .env."""
    env = os.getenv("FLASK_ENV", "development").lower()
    if env == "production":
        app.config.from_object(ProdConfig)
    else:
        app.config.from_object(DevConfig)
    
    # Muat variabel dari .env secara eksplisit ke dalam app.config.
    # Ini menimpa nilai default di BaseConfig jika ada di .env.
    app.config.update(
        DATABASE_URL = os.getenv('DATABASE_URL', ''),
        TIMEZONE = os.getenv('TIMEZONE', 'Asia/Makassar'),
        DEFAULT_GEOFENCE_RADIUS = int(os.getenv('DEFAULT_GEOFENCE_RADIUS', '100')),
        MODEL_NAME = os.getenv('MODEL_NAME', 'buffalo_s'),
    
        # Nextcloud variables
        NEXTCLOUD_URL = os.getenv("NEXTCLOUD_URL", ""),
        NEXTCLOUD_USER = os.getenv("NEXTCLOUD_USER", ""),
        NEXTCLOUD_PASS = os.getenv("NEXTCLOUD_PASS", ""),
        NEXTCLOUD_DEFAULT_FOLDER = os.getenv("NEXTCLOUD_DEFAULT_FOLDER", "uploads"),
        
        # Variabel Celery
        CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0'),
        CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0'),

        # Placeholder for additional environment-driven configuration
    )
