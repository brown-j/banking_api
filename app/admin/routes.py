"""
Module Administration — Routes Flask.
Gestion des utilisateurs, tableau de bord, rapports.
"""
from datetime import datetime, timedelta
from flask import Blueprint, request
from app.common.jwt_utils import jwt_required
from sqlalchemy import func
from app import db, bcrypt
from app.models import (
    User, UserRole, Account, Transaction, TransactionStatus,
    TransactionType, KycStatus, NotificationPreference
)
from app.common.utils import success_response, error_response, get_current_user, roles_required, paginate, log_audit
from app.common.utils import generate_account_number

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/dashboard", methods=["GET"])
@jwt_required()
@roles_required(UserRole.ADMIN, UserRole.SUPERVISOR, UserRole.IT)
def dashboard():
    """
    Tableau de bord administrateur
    ---
    tags:
      - Administration
    summary: Statistiques en temps réel du système bancaire (Admin/Superviseur/IT)
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
        description: Métriques du tableau de bord
      403:
        description: Accès refusé
    """
    today_start = datetime.combine(datetime.utcnow().date(), datetime.min.time())
    total_users         = User.query.count()
    active_clients      = User.query.filter_by(role=UserRole.CLIENT, is_active=True).count()
    total_accounts      = Account.query.count()
    active_accounts     = Account.query.filter_by(status="actif").count()
    pending_kyc         = User.query.filter_by(kyc_status=KycStatus.PENDING).count()
    pending_validations = Transaction.query.filter_by(status=TransactionStatus.REVIEWING).count()
    today_count  = Transaction.query.filter(Transaction.created_at >= today_start).count()
    today_volume = db.session.query(func.sum(Transaction.amount)).filter(
        Transaction.created_at >= today_start,
        Transaction.status == TransactionStatus.COMPLETED,
    ).scalar() or 0
    today_deposits = db.session.query(func.sum(Transaction.amount)).filter(
        Transaction.created_at >= today_start,
        Transaction.transaction_type == TransactionType.DEPOSIT,
        Transaction.status == TransactionStatus.COMPLETED,
    ).scalar() or 0
    today_withdrawals = db.session.query(func.sum(Transaction.amount)).filter(
        Transaction.created_at >= today_start,
        Transaction.transaction_type == TransactionType.WITHDRAWAL,
        Transaction.status == TransactionStatus.COMPLETED,
    ).scalar() or 0
    return success_response({
        "users": {"total": total_users, "active_clients": active_clients, "pending_kyc": pending_kyc},
        "accounts": {"total": total_accounts, "active": active_accounts},
        "transactions_today": {
            "count": today_count,
            "total_volume": float(today_volume),
            "total_deposits": float(today_deposits),
            "total_withdrawals": float(today_withdrawals),
        },
        "pending_validations": pending_validations,
        "as_of": datetime.utcnow().isoformat() + "Z",
    })


@admin_bp.route("/users", methods=["GET"])
@jwt_required()
@roles_required(UserRole.ADMIN, UserRole.IT)
def list_users():
    """
    Lister tous les utilisateurs
    ---
    tags:
      - Administration
    summary: Récupérer la liste paginée de tous les utilisateurs (Admin/IT)
    produces:
      - application/json
    parameters:
      - in: header
        name: Authorization
        type: string
        required: true
        description: "Bearer <access_token>"
      - in: query
        name: role
        type: string
        enum: [client, agent, admin, supervisor, auditor, it]
      - in: query
        name: kyc_status
        type: string
        enum: [pending, verified, rejected]
      - in: query
        name: is_active
        type: boolean
      - in: query
        name: page
        type: integer
        default: 1
      - in: query
        name: per_page
        type: integer
        default: 20
    responses:
      200:
        description: Liste paginée des utilisateurs
      403:
        description: Accès refusé
    """
    query = User.query
    if request.args.get("role"):
        try:
            query = query.filter_by(role=UserRole(request.args["role"]))
        except ValueError:
            return error_response("Rôle invalide", 400)
    if request.args.get("kyc_status"):
        try:
            query = query.filter_by(kyc_status=KycStatus(request.args["kyc_status"]))
        except ValueError:
            return error_response("Statut KYC invalide", 400)
    if request.args.get("is_active") is not None:
        query = query.filter_by(is_active=request.args.get("is_active", "").lower() == "true")
    query = query.order_by(User.created_at.desc())
    items, meta = paginate(query)
    return success_response([u.to_dict() for u in items], f"{meta['total_items']} utilisateur(s)", meta=meta)


@admin_bp.route("/users", methods=["POST"])
@jwt_required()
@roles_required(UserRole.ADMIN)
def create_internal_user():
    """
    Créer un utilisateur interne
    ---
    tags:
      - Administration
    summary: Créer un agent, superviseur, auditeur ou IT (Admin uniquement)
    consumes:
      - application/json
    produces:
      - application/json
    parameters:
      - in: header
        name: Authorization
        type: string
        required: true
        description: "Bearer <access_token>"
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - email
            - password
            - first_name
            - last_name
            - role
          properties:
            email:
              type: string
              example: agent.dupont@banque.cm
            password:
              type: string
              example: MotDePasse123!
            first_name:
              type: string
              example: Marie
            last_name:
              type: string
              example: Dupont
            phone:
              type: string
              example: "+237699000010"
            role:
              type: string
              enum: [agent, admin, supervisor, auditor, it]
              example: agent
    responses:
      201:
        description: Utilisateur interne créé
      400:
        description: Email déjà utilisé ou rôle invalide
      403:
        description: Accès refusé (Admin requis)
    """
    data = request.get_json(silent=True)
    if not data:
        return error_response("Corps JSON requis", 422)
    required = ["email", "password", "first_name", "last_name", "role"]
    missing  = [f for f in required if not data.get(f)]
    if missing:
        return error_response(f"Champs requis : {missing}", 422)
    try:
        role = UserRole(data["role"])
        if role == UserRole.CLIENT:
            return error_response("Utilisez /auth/register pour créer un client", 400)
    except ValueError:
        return error_response(f"Rôle invalide. Valeurs acceptées : {[r.value for r in UserRole]}", 400)
    if User.query.filter_by(email=data["email"].lower()).first():
        return error_response("Email déjà utilisé", 400)
    admin    = get_current_user()
    pwd_hash = bcrypt.generate_password_hash(data["password"]).decode("utf-8")
    user = User(
        email         = data["email"].lower().strip(),
        password_hash = pwd_hash,
        first_name    = data["first_name"].strip(),
        last_name     = data["last_name"].strip(),
        phone         = data.get("phone"),
        role          = role,
        kyc_status    = KycStatus.VERIFIED,
    )
    db.session.add(user)
    db.session.commit()
    log_audit("ADMIN_USER_CREATE", "users", user.id, {"email": user.email, "role": role.value}, user_id=admin.id)
    return success_response(user.to_dict(), "Utilisateur interne créé", 201)


@admin_bp.route("/users/<user_id>", methods=["GET"])
@jwt_required()
@roles_required(UserRole.ADMIN, UserRole.IT, UserRole.AUDITOR)
def get_user(user_id):
    """
    Détail d'un utilisateur
    ---
    tags:
      - Administration
    summary: Récupérer les informations complètes d'un utilisateur avec ses comptes
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
    responses:
      200:
        description: Informations de l'utilisateur avec ses comptes
      404:
        description: Utilisateur introuvable
    """
    user = db.session.get(User, user_id)
    if not user:
        return error_response("Utilisateur introuvable", 404)
    data = user.to_dict()
    data["accounts"] = [a.to_dict() for a in user.accounts.all()]
    return success_response(data)


@admin_bp.route("/users/<user_id>", methods=["PATCH"])
@jwt_required()
@roles_required(UserRole.ADMIN)
def update_user(user_id):
    """
    Modifier un utilisateur
    ---
    tags:
      - Administration
    summary: Mettre à jour les informations ou le statut d'un utilisateur (Admin)
    consumes:
      - application/json
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
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            is_active:
              type: boolean
              example: true
            kyc_status:
              type: string
              enum: [pending, verified, rejected]
              example: verified
            phone:
              type: string
              example: "+237699000099"
            role:
              type: string
              enum: [client, agent, admin, supervisor, auditor, it]
    responses:
      200:
        description: Utilisateur mis à jour
      404:
        description: Utilisateur introuvable
    """
    user = db.session.get(User, user_id)
    if not user:
        return error_response("Utilisateur introuvable", 404)
    data  = request.get_json(silent=True) or {}
    admin = get_current_user()
    if "is_active"  in data: user.is_active  = bool(data["is_active"])
    if "phone"      in data: user.phone       = data["phone"]
    if "kyc_status" in data:
        try:
            user.kyc_status = KycStatus(data["kyc_status"])
        except ValueError:
            return error_response("kyc_status invalide", 400)
    if "role" in data:
        try:
            user.role = UserRole(data["role"])
        except ValueError:
            return error_response("Rôle invalide", 400)
    db.session.commit()
    log_audit("ADMIN_USER_UPDATE", "users", user_id, data, user_id=admin.id)
    return success_response(user.to_dict(), "Utilisateur mis à jour")


@admin_bp.route("/users/<user_id>", methods=["DELETE"])
@jwt_required()
@roles_required(UserRole.ADMIN)
def deactivate_user(user_id):
    """
    Désactiver un utilisateur
    ---
    tags:
      - Administration
    summary: Désactiver définitivement un compte utilisateur — soft delete (Admin)
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
    responses:
      200:
        description: Utilisateur désactivé
      400:
        description: Impossible de se désactiver soi-même
      404:
        description: Utilisateur introuvable
    """
    user  = db.session.get(User, user_id)
    if not user:
        return error_response("Utilisateur introuvable", 404)
    admin = get_current_user()
    if user.id == admin.id:
        return error_response("Impossible de désactiver son propre compte", 400)
    user.is_active = False
    db.session.commit()
    log_audit("ADMIN_USER_DEACTIVATE", "users", user_id, user_id=admin.id)
    return success_response(message=f"Utilisateur {user.email} désactivé")


@admin_bp.route("/reports", methods=["GET"])
@jwt_required()
@roles_required(UserRole.ADMIN, UserRole.AUDITOR, UserRole.SUPERVISOR)
def generate_report():
    """
    Générer un rapport de transactions
    ---
    tags:
      - Administration
    summary: Rapport de synthèse des transactions sur une période (Admin/Auditeur/Superviseur)
    produces:
      - application/json
    parameters:
      - in: header
        name: Authorization
        type: string
        required: true
        description: "Bearer <access_token>"
      - in: query
        name: start_date
        type: string
        required: true
        description: "Date de début (YYYY-MM-DD)"
        example: "2025-01-01"
      - in: query
        name: end_date
        type: string
        required: true
        description: "Date de fin (YYYY-MM-DD)"
        example: "2025-01-31"
      - in: query
        name: type
        type: string
        enum: [depot, retrait, virement, frais]
        description: Filtrer par type de transaction (optionnel)
    responses:
      200:
        description: Rapport généré
      400:
        description: Dates invalides ou manquantes
    """
    start_str = request.args.get("start_date")
    end_str   = request.args.get("end_date")
    if not start_str or not end_str:
        return error_response("start_date et end_date sont requis (format YYYY-MM-DD)", 400)
    try:
        start = datetime.strptime(start_str, "%Y-%m-%d")
        end   = datetime.strptime(end_str,   "%Y-%m-%d") + timedelta(days=1)
    except ValueError:
        return error_response("Format de date invalide. Utilisez YYYY-MM-DD", 400)
    query = Transaction.query.filter(
        Transaction.created_at >= start,
        Transaction.created_at <  end,
        Transaction.status     == TransactionStatus.COMPLETED,
    )
    if request.args.get("type"):
        query = query.filter(Transaction.transaction_type == request.args["type"])
    transactions = query.all()
    by_type = {}
    for txn in transactions:
        t = txn.transaction_type.value
        if t not in by_type:
            by_type[t] = {"count": 0, "total_amount": 0.0}
        by_type[t]["count"]        += 1
        by_type[t]["total_amount"] += float(txn.amount)
    return success_response({
        "period":             {"start": start_str, "end": end_str},
        "total_transactions": len(transactions),
        "total_volume":       sum(float(t.amount) for t in transactions),
        "by_type":            by_type,
        "transactions":       [t.to_dict() for t in transactions[:500]],
    }, f"Rapport généré : {len(transactions)} transaction(s)")
