"""
Configuration de l'application Flask.
Charge les variables d'environnement depuis .env
"""
import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Configuration de base."""

    # ── Application ───────────────────────────────────────────────────────────
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    FLASK_ENV  = os.getenv("FLASK_ENV", "development")

    # ── Base de données ───────────────────────────────────────────────────────
    SQLALCHEMY_DATABASE_URI    = os.getenv("DATABASE_URL", "sqlite:///banking_dev.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO            = False

    # ── JWT ───────────────────────────────────────────────────────────────────
    JWT_SECRET_KEY                = os.getenv("JWT_SECRET_KEY", "dev-jwt-secret")
    JWT_ACCESS_TOKEN_EXPIRES      = timedelta(seconds=int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES", 900)))
    JWT_REFRESH_TOKEN_EXPIRES     = timedelta(seconds=int(os.getenv("JWT_REFRESH_TOKEN_EXPIRES", 604800)))
    JWT_TOKEN_LOCATION            = ["headers"]
    JWT_HEADER_NAME               = "Authorization"
    JWT_HEADER_TYPE               = "Bearer"
    JWT_BLACKLIST_ENABLED         = True
    JWT_BLACKLIST_TOKEN_CHECKS    = ["access", "refresh"]

    # ── Sécurité ──────────────────────────────────────────────────────────────
    MAX_LOGIN_ATTEMPTS            = int(os.getenv("MAX_LOGIN_ATTEMPTS", 5))
    LOCKOUT_DURATION              = int(os.getenv("LOCKOUT_DURATION", 1800))
    BCRYPT_LOG_ROUNDS             = int(os.getenv("BCRYPT_LOG_ROUNDS", 12))

    # ── Plafonds ──────────────────────────────────────────────────────────────
    DEFAULT_DAILY_WITHDRAWAL_LIMIT = float(os.getenv("DEFAULT_DAILY_WITHDRAWAL_LIMIT", 500000))
    DEFAULT_DAILY_DEPOSIT_LIMIT    = float(os.getenv("DEFAULT_DAILY_DEPOSIT_LIMIT", 5000000))
    DEFAULT_TRANSFER_LIMIT         = float(os.getenv("DEFAULT_TRANSFER_LIMIT", 2000000))
    HIGH_VALUE_THRESHOLD           = float(os.getenv("HIGH_VALUE_THRESHOLD", 1000000))

    # ── Swagger ───────────────────────────────────────────────────────────────
    SWAGGER = {
        "title": "Système de Transaction Bancaire — API",
        "uiversion": 3,
        "version": "1.0.0",
        "description": (
            "API REST complète pour le Système de Transaction Bancaire (STB). "
            "Permet la gestion des comptes, des dépôts, retraits, virements, "
            "notifications et de l'administration. "
            "**Authentification** : Bearer JWT dans le header `Authorization`."
        ),
        "termsOfService": "",
        "contact": {"name": "Équipe IT Bancaire", "email": "it@banque.cm"},
        "license": {"name": "Propriétaire"},
        "securityDefinitions": {
            "BearerAuth": {
                "type": "apiKey",
                "in": "header",
                "name": "Authorization",
                "description": "JWT token. Format : **Bearer &lt;token&gt;**",
            }
        },
        "security": [{"BearerAuth": []}],
        "specs_route": "/api/docs/",
    }


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_ECHO = False


class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_ECHO = False
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=15)


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=5)


config_map = {
    "development": DevelopmentConfig,
    "production":  ProductionConfig,
    "testing":     TestingConfig,
}


def get_config():
    env = os.getenv("FLASK_ENV", "development")
    return config_map.get(env, DevelopmentConfig)
