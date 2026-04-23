"""
Utilitaires communs : helpers de réponse, décorateurs de rôles,
pagination, génération de références.
"""
import json
import uuid
import random
import string
from datetime import datetime
from functools import wraps

from flask import jsonify, request, current_app
from app.common.jwt_utils import get_jwt_identity, verify_jwt_in_request, get_jwt

from app.models import User, UserRole, AuditLog
from app import db


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de réponse standardisée
# ─────────────────────────────────────────────────────────────────────────────
def success_response(data=None, message="Succès", code=200, meta=None):
    payload = {
        "status":    "success",
        "code":      code,
        "message":   message,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
    if data is not None:
        payload["data"] = data
    if meta is not None:
        payload["meta"] = meta
    return jsonify(payload), code


def error_response(message="Erreur", code=400, errors=None):
    payload = {
        "status":    "error",
        "code":      code,
        "message":   message,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
    if errors:
        payload["errors"] = errors
    return jsonify(payload), code


# ─────────────────────────────────────────────────────────────────────────────
# Décorateur : rôles requis
# ─────────────────────────────────────────────────────────────────────────────
def roles_required(*roles):
    """
    Décorateur qui vérifie que l'utilisateur connecté possède un des rôles requis.
    Usage : @roles_required(UserRole.ADMIN, UserRole.SUPERVISOR)
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            user_id = get_jwt_identity()
            user    = db.session.get(User, user_id)
            if not user or not user.is_active:
                return error_response("Utilisateur inactif ou introuvable", 403)
            if user.role not in roles:
                return error_response(
                    f"Accès refusé. Rôle requis : {[r.value for r in roles]}",
                    403
                )
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def get_current_user():
    """Retourne l'objet User correspondant au JWT courant."""
    user_id = get_jwt_identity()
    return db.session.get(User, user_id)


# ─────────────────────────────────────────────────────────────────────────────
# Pagination
# ─────────────────────────────────────────────────────────────────────────────
def paginate(query, page=1, per_page=20, max_per_page=100):
    """
    Pagine une query SQLAlchemy et retourne (items, meta).
    """
    per_page = min(int(request.args.get("per_page", per_page)), max_per_page)
    page     = int(request.args.get("page", page))

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    meta = {
        "page":        pagination.page,
        "per_page":    pagination.per_page,
        "total_items": pagination.total,
        "total_pages": pagination.pages,
        "has_next":    pagination.has_next,
        "has_prev":    pagination.has_prev,
    }
    return pagination.items, meta


# ─────────────────────────────────────────────────────────────────────────────
# Génération de références de transaction
# ─────────────────────────────────────────────────────────────────────────────
def generate_transaction_ref(prefix="TXN"):
    """
    Génère une référence unique de transaction.
    Format : TXN-20250101-XXXXXXXX
    """
    date_str = datetime.utcnow().strftime("%Y%m%d")
    suffix   = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    return f"{prefix}-{date_str}-{suffix}"


def generate_account_number():
    """
    Génère un numéro de compte bancaire unique.
    Format : CM-XXXXXXXXXX (10 chiffres)
    """
    digits = "".join(random.choices(string.digits, k=10))
    return f"CM{digits}"


# ─────────────────────────────────────────────────────────────────────────────
# Audit logger
# ─────────────────────────────────────────────────────────────────────────────
def log_audit(action, resource=None, resource_id=None, details=None, success=True, user_id=None):
    """Enregistre une entrée dans le journal d'audit."""
    try:
        uid = user_id
        if uid is None:
            try:
                uid = get_jwt_identity()
            except Exception:
                pass

        entry = AuditLog(
            user_id     = uid,
            action      = action,
            resource    = resource,
            resource_id = resource_id,
            ip_address  = request.remote_addr,
            user_agent  = request.headers.get("User-Agent", "")[:300],
            details     = json.dumps(details, default=str) if details else None,
            success     = success,
        )
        db.session.add(entry)
        db.session.flush()
    except Exception as e:
        current_app.logger.warning(f"Audit log failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Validation de montant
# ─────────────────────────────────────────────────────────────────────────────
def validate_amount(amount):
    """Valide et retourne le montant sous forme de float, ou None si invalide."""
    try:
        val = float(amount)
        if val <= 0:
            return None
        return val
    except (TypeError, ValueError):
        return None
