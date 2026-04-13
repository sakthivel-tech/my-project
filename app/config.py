import os
from datetime import timedelta


class Config:
    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY', 'default-secret-key-123456789')
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'

    # SQLAlchemy / PostgreSQL
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    if SQLALCHEMY_DATABASE_URI:
        if SQLALCHEMY_DATABASE_URI.startswith('postgres://'):
            SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace(
                'postgres://', 'postgresql://', 1)
    else:
        SQLALCHEMY_DATABASE_URI = 'sqlite:///' + \
            os.path.join(os.getcwd(), 'instance', 'app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Session / Cookies
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)

    # Security
    RATELIMIT_DEFAULT = "200 per day; 50 per hour"

    # Celery & Redis (Robust detection for Render)
    # Priority: Internal Redis URL (for same-project communication) -> Public REDIS_URL -> localhost
    INTERNAL_REDIS = os.environ.get('INTERNAL_REDIS_URL')
    PUBLIC_REDIS = os.environ.get('REDIS_URL')
    
    REDIS_URL = INTERNAL_REDIS or PUBLIC_REDIS or 'redis://localhost:6379/0'
    
    CELERY_BROKER_URL = REDIS_URL
    CELERY_RESULT_BACKEND = REDIS_URL
    
    # Modern Celery settings (Lowercase for newer versions)
    broker_url = REDIS_URL
    result_backend = REDIS_URL
    
    CACHE_DEFAULT_TIMEOUT = 3600  # 1 hour


class ProductionConfig(Config):
    DEBUG = False


class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False


config_by_name = {
    'dev': DevelopmentConfig,
    'prod': ProductionConfig
}
