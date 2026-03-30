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


class ProductionConfig(Config):
    DEBUG = False


class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False


config_by_name = {
    'dev': DevelopmentConfig,
    'prod': ProductionConfig
}
