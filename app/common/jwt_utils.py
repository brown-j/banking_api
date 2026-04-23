"""
Module JWT maison — remplace flask-jwt-extended.
Utilise PyJWT (déjà installé) directement.

Fonctions disponibles :
  - create_access_token(identity, extra_claims)
  - create_refresh_token(identity)
  - jwt_required()          → décorateur de route
  - jwt_required(refresh=True) → exige un refresh token
  - get_jwt_identity()      → retourne l'identity du token courant
  - get_jwt()               → retourne le payload complet
  - verify_jwt_in_request() → lève une exception si token invalide
"""
import jwt
import uuid
from datetime import datetime, timezone, timedelta
from functools import wraps

from flask import request, jsonify, current_app, g


# ─────────────────────────────────────────────────────────────────────────────
# Helpers internes
# ─────────────────────────────────────────────────────────────────────────────
def _secret():
    return current_app.config["JWT_SECRET_KEY"]


def _algorithm():
    return "HS256"


def _now():
    return datetime.now(timezone.utc)


def _extract_token_from_header():
    """Extrait le token du header Authorization: Bearer <token>."""
    auth = request.headers.get("Authorization", "")
    parts = auth.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None


def _decode_token(token: str) -> dict:
    """Décode et valide un token JWT. Lève jwt.PyJWTError si invalide."""
    return jwt.decode(token, _secret(), algorithms=[_algorithm()])


# ─────────────────────────────────────────────────────────────────────────────
# Création de tokens
# ─────────────────────────────────────────────────────────────────────────────
def create_access_token(identity: str, additional_claims: dict = None) -> str:
    """
    Crée un access token JWT.
    identity       : identifiant unique de l'utilisateur (user.id)
    additional_claims : données supplémentaires (ex. {"role": "admin"})
    """
    expires = current_app.config.get("JWT_ACCESS_TOKEN_EXPIRES", timedelta(minutes=15))
    payload = {
        "sub":  identity,
        "iat":  _now(),
        "exp":  _now() + expires,
        "jti":  str(uuid.uuid4()),
        "type": "access",
    }
    if additional_claims:
        payload.update(additional_claims)
    return jwt.encode(payload, _secret(), algorithm=_algorithm())


def create_refresh_token(identity: str) -> str:
    """Crée un refresh token JWT (longue durée)."""
    expires = current_app.config.get("JWT_REFRESH_TOKEN_EXPIRES", timedelta(days=7))
    payload = {
        "sub":  identity,
        "iat":  _now(),
        "exp":  _now() + expires,
        "jti":  str(uuid.uuid4()),
        "type": "refresh",
    }
    return jwt.encode(payload, _secret(), algorithm=_algorithm())


# ─────────────────────────────────────────────────────────────────────────────
# Lecture du contexte de requête
# ─────────────────────────────────────────────────────────────────────────────
def get_jwt_identity() -> str:
    """Retourne l'identifiant utilisateur du token courant (champ 'sub')."""
    payload = getattr(g, "_jwt_payload", None)
    if payload is None:
        raise RuntimeError("Aucun token JWT dans le contexte. Utilisez @jwt_required()")
    return payload.get("sub")


def get_jwt() -> dict:
    """Retourne le payload complet du token courant."""
    payload = getattr(g, "_jwt_payload", None)
    if payload is None:
        raise RuntimeError("Aucun token JWT dans le contexte. Utilisez @jwt_required()")
    return payload


def verify_jwt_in_request(refresh: bool = False):
    """
    Vérifie le token JWT dans le header de la requête courante.
    Stocke le payload dans flask.g._jwt_payload.
    Lève une exception HTTP 401/422 si invalide.
    """
    token = _extract_token_from_header()
    if not token:
        raise _jwt_error("Token manquant dans le header Authorization", 401)

    try:
        payload = _decode_token(token)
    except jwt.ExpiredSignatureError:
        raise _jwt_error("Token expiré", 401)
    except jwt.InvalidTokenError as e:
        raise _jwt_error(f"Token invalide : {e}", 422)

    # Vérifier le type de token
    expected_type = "refresh" if refresh else "access"
    if payload.get("type") != expected_type:
        raise _jwt_error(f"Type de token incorrect (attendu : {expected_type})", 422)

    # Vérifier la blacklist
    from app import BLACKLISTED_TOKENS
    if payload.get("jti") in BLACKLISTED_TOKENS:
        raise _jwt_error("Token révoqué", 401)

    # Stocker dans le contexte Flask
    g._jwt_payload = payload


class _jwt_error(Exception):
    """Exception interne portant un code HTTP et un message."""
    def __init__(self, message: str, status_code: int):
        self.message     = message
        self.status_code = status_code
        super().__init__(message)


# ─────────────────────────────────────────────────────────────────────────────
# Décorateur @jwt_required()
# ─────────────────────────────────────────────────────────────────────────────
def jwt_required(refresh: bool = False):
    """
    Décorateur Flask qui protège une route avec JWT.

    Usage :
        @app.route("/protected")
        @jwt_required()
        def protected():
            user_id = get_jwt_identity()
            ...

        @app.route("/refresh")
        @jwt_required(refresh=True)
        def refresh():
            ...
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                verify_jwt_in_request(refresh=refresh)
            except _jwt_error as e:
                return jsonify({
                    "status":  "error",
                    "code":    e.status_code,
                    "message": e.message,
                }), e.status_code
            return fn(*args, **kwargs)
        return wrapper
    return decorator
