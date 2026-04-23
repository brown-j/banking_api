"""
Module Audit — Routes Flask.
Journaux d'audit immuables. Accès réservé aux auditeurs, admins et IT.
"""
from datetime import datetime, timedelta
from flask import Blueprint, request
from app.common.jwt_utils import jwt_required
from app import db
from app.models import AuditLog, User, UserRole
from app.common.utils import success_response, error_response, roles_required, paginate, get_current_user

audit_bp = Blueprint("audit", __name__)


@audit_bp.route("/logs", methods=["GET"])
@jwt_required()
@roles_required(UserRole.ADMIN, UserRole.AUDITOR, UserRole.IT)
def list_logs():
    """
    Consulter les journaux d'audit
    ---
    tags:
      - Audit
    summary: Récupérer les journaux d'audit paginés avec filtres (Admin/Auditeur/IT)
    description: Journaux immuables — aucune modification possible.
    produces:
      - application/json
    parameters:
      - in: header
        name: Authorization
        type: string
        required: true
        description: "Bearer <access_token>"
      - in: query
        name: page
        type: integer
        default: 1
      - in: query
        name: per_page
        type: integer
        default: 50
      - in: query
        name: user_id
        type: string
        description: Filtrer par utilisateur
      - in: query
        name: action
        type: string
        description: "Filtrer par action (ex: DEPOSIT, USER_LOGIN)"
      - in: query
        name: resource
        type: string
        description: "Filtrer par ressource (ex: transactions, users)"
      - in: query
        name: start_date
        type: string
        description: "Date de début (YYYY-MM-DD)"
      - in: query
        name: end_date
        type: string
        description: "Date de fin (YYYY-MM-DD)"
      - in: query
        name: success
        type: boolean
        description: Filtrer par succès ou échec
    responses:
      200:
        description: Liste paginée des journaux d'audit
      403:
        description: Accès refusé
    """
    query = AuditLog.query
    if request.args.get("user_id"):
        query = query.filter_by(user_id=request.args["user_id"])
    if request.args.get("action"):
        query = query.filter(AuditLog.action.ilike(f"%{request.args['action']}%"))
    if request.args.get("resource"):
        query = query.filter_by(resource=request.args["resource"])
    if request.args.get("success") is not None:
        query = query.filter_by(success=request.args.get("success", "").lower() == "true")
    if request.args.get("start_date"):
        try:
            query = query.filter(AuditLog.created_at >= datetime.strptime(request.args["start_date"], "%Y-%m-%d"))
        except ValueError:
            return error_response("Format start_date invalide (YYYY-MM-DD)", 400)
    if request.args.get("end_date"):
        try:
            end = datetime.strptime(request.args["end_date"], "%Y-%m-%d") + timedelta(days=1)
            query = query.filter(AuditLog.created_at < end)
        except ValueError:
            return error_response("Format end_date invalide (YYYY-MM-DD)", 400)
    query = query.order_by(AuditLog.created_at.desc())
    items, meta = paginate(query, per_page=50)
    return success_response([log.to_dict() for log in items], f"{meta['total_items']} entrée(s) d'audit", meta=meta)


@audit_bp.route("/logs/<log_id>", methods=["GET"])
@jwt_required()
@roles_required(UserRole.ADMIN, UserRole.AUDITOR, UserRole.IT)
def get_log(log_id):
    """
    Détail d'une entrée d'audit
    ---
    tags:
      - Audit
    summary: Récupérer le détail complet d'une entrée du journal d'audit
    produces:
      - application/json
    parameters:
      - in: header
        name: Authorization
        type: string
        required: true
        description: "Bearer <access_token>"
      - in: path
        name: log_id
        type: string
        required: true
        description: Identifiant UUID de l'entrée d'audit
    responses:
      200:
        description: Détail de l'entrée d'audit
      404:
        description: Entrée introuvable
    """
    log = db.session.get(AuditLog, log_id)
    if not log:
        return error_response("Entrée d'audit introuvable", 404)
    return success_response(log.to_dict())


@audit_bp.route("/logs/user/<user_id>", methods=["GET"])
@jwt_required()
@roles_required(UserRole.ADMIN, UserRole.AUDITOR)
def get_user_audit(user_id):
    """
    Journal d'audit d'un utilisateur
    ---
    tags:
      - Audit
    summary: Récupérer toutes les actions d'un utilisateur spécifique
    produces:
      - application/json
    parameters:
      - in: header
        name: Authorization
        type: string
        required: true
        description: "Bearer <access_token>"
      - in: path
        name: user_id
        type: string
        required: true
      - in: query
        name: page
        type: integer
        default: 1
      - in: query
        name: per_page
        type: integer
        default: 30
    responses:
      200:
        description: Journal d'audit de l'utilisateur
      404:
        description: Utilisateur introuvable
    """
    user = db.session.get(User, user_id)
    if not user:
        return error_response("Utilisateur introuvable", 404)
    query = AuditLog.query.filter_by(user_id=user_id).order_by(AuditLog.created_at.desc())
    items, meta = paginate(query, per_page=30)
    return success_response(
        {"user": user.to_dict(), "logs": [log.to_dict() for log in items]},
        f"{meta['total_items']} action(s) enregistrée(s)",
        meta=meta
    )


@audit_bp.route("/stats", methods=["GET"])
@jwt_required()
@roles_required(UserRole.ADMIN, UserRole.AUDITOR)
def audit_stats():
    """
    Statistiques du journal d'audit
    ---
    tags:
      - Audit
    summary: Statistiques d'activité et top actions du journal d'audit
    produces:
      - application/json
    parameters:
      - in: header
        name: Authorization
        type: string
        required: true
        description: "Bearer <access_token>"
    responses:
      200:
        description: Statistiques d'audit (top actions, activité 7 jours, échecs)
      403:
        description: Accès refusé
    """
    last_24h = datetime.utcnow() - timedelta(hours=24)
    last_7d  = datetime.utcnow() - timedelta(days=7)
    total_logs    = AuditLog.query.count()
    last_24h_cnt  = AuditLog.query.filter(AuditLog.created_at >= last_24h).count()
    failed_cnt    = AuditLog.query.filter_by(success=False).count()
    failed_24h    = AuditLog.query.filter(AuditLog.created_at >= last_24h, AuditLog.success == False).count()  # noqa
    from sqlalchemy import func
    top_actions = db.session.query(
        AuditLog.action,
        func.count(AuditLog.id).label("count")
    ).group_by(AuditLog.action).order_by(func.count(AuditLog.id).desc()).limit(10).all()
    daily_activity = db.session.query(
        func.date(AuditLog.created_at).label("date"),
        func.count(AuditLog.id).label("count")
    ).filter(AuditLog.created_at >= last_7d).group_by(func.date(AuditLog.created_at)).order_by("date").all()
    return success_response({
        "total_logs":      total_logs,
        "last_24h":        last_24h_cnt,
        "total_failures":  failed_cnt,
        "failures_24h":    failed_24h,
        "top_actions":     [{"action": a.action, "count": a.count} for a in top_actions],
        "daily_activity":  [{"date": str(d.date), "count": d.count} for d in daily_activity],
    })
