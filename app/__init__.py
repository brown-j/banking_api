"""
Factory principale de l'application Flask.
JWT géré par PyJWT natif via app/common/jwt_utils.py
"""
from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_bcrypt import Bcrypt
from flasgger import Swagger

from config import get_config

# ── Extensions ────────────────────────────────────────────────────────────────
db      = SQLAlchemy()
migrate = Migrate()
bcrypt  = Bcrypt()
swagger = Swagger()


# Tokens révoqués (en prod : Redis)
BLACKLISTED_TOKENS: set = set()


def create_app(config_class=None):
    """Crée et configure l'instance Flask."""
    app = Flask(__name__)
    cfg = config_class or get_config()
    app.config.from_object(cfg)

    # 1. Définir le template de sécurité
    template = {
        "swagger": "2.0",
        "info": {
            "title": "Banking API",
            "version": "1.0.0",
            "description": "API de gestion bancaire"
        },
        "securityDefinitions": {
            "BearerAuth": {
                "type": "apiKey",
                "name": "Authorization",
                "in": "header",
                "description": "Entrez votre token comme ceci : Bearer <votre_token>"
            }
        }
    }
    
    db.init_app(app)
    migrate.init_app(app, db)
    bcrypt.init_app(app)
    swagger.template = template
    swagger.init_app(app)

    # ── Blueprints ────────────────────────────────────────────────────────────
    from app.auth.routes          import auth_bp
    from app.accounts.routes      import accounts_bp
    from app.transactions.routes  import transactions_bp
    from app.notifications.routes import notifications_bp
    from app.admin.routes         import admin_bp
    from app.audit.routes         import audit_bp

    app.register_blueprint(auth_bp,           url_prefix="/api/v1/auth")
    app.register_blueprint(accounts_bp,       url_prefix="/api/v1/accounts")
    app.register_blueprint(transactions_bp,   url_prefix="/api/v1/transactions")
    app.register_blueprint(notifications_bp,  url_prefix="/api/v1/notifications")
    app.register_blueprint(admin_bp,          url_prefix="/api/v1/admin")
    app.register_blueprint(audit_bp,          url_prefix="/api/v1/audit")

    # ── Handlers d'erreurs ────────────────────────────────────────────────────
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"status": "error", "message": "Ressource introuvable"}), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({"status": "error", "message": "Méthode non autorisée"}), 405

    @app.errorhandler(500)
    def internal_error(e):
        db.session.rollback()
        return jsonify({"status": "error", "message": "Erreur serveur interne"}), 500

    @app.route("/api/v1/health")
    def health():
        return jsonify({"status": "ok", "service": "STB API", "version": "1.0.0"}), 200

    return app
