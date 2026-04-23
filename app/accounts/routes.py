"""
Module Comptes — Routes Flask.
CRUD complet sur les comptes bancaires.
"""
from flask import Blueprint, request
from app.common.jwt_utils import jwt_required
from app.accounts.service import AccountService
from app.common.utils import success_response, error_response, get_current_user, roles_required, paginate
from app.models import UserRole, Transaction
from sqlalchemy import or_

accounts_bp = Blueprint("accounts", __name__)


@accounts_bp.route("", methods=["GET"])
@jwt_required()
def list_accounts():
    """
    Lister les comptes
    ---
    tags:
      - Comptes
    summary: Récupérer tous les comptes de l'utilisateur connecté
    description: Un client voit ses propres comptes. Admin/Agent peuvent filtrer par owner_id.
    produces:
      - application/json
    parameters:
      - in: header
        name: Authorization
        type: string
        required: true
        description: "Bearer <access_token>"
      - in: query
        name: owner_id
        type: string
        required: false
        description: (Admin/Agent) Filtrer par ID client
    responses:
      200:
        description: Liste des comptes
      401:
        description: Non authentifié
    """
    user = get_current_user()
    if not user:
        return error_response("Utilisateur introuvable", 404)
    if user.role in (UserRole.ADMIN, UserRole.AGENT, UserRole.SUPERVISOR, UserRole.IT, UserRole.AUDITOR):
        owner_id = request.args.get("owner_id", user.id)
    else:
        owner_id = user.id
    accounts = AccountService.get_accounts_for_user(owner_id)
    return success_response([a.to_dict() for a in accounts], f"{len(accounts)} compte(s) trouvé(s)")


@accounts_bp.route("", methods=["POST"])
@jwt_required()
@roles_required(UserRole.ADMIN, UserRole.AGENT)
def create_account():
    """
    Créer un compte bancaire
    ---
    tags:
      - Comptes
    summary: Ouvrir un nouveau compte pour un client (Admin/Agent)
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
            - owner_id
          properties:
            owner_id:
              type: string
              description: ID du client propriétaire
              example: "uuid-du-client"
            account_type:
              type: string
              enum: [courant, epargne, professionnel]
              default: courant
              example: courant
            currency:
              type: string
              default: XAF
              example: XAF
            daily_withdrawal_limit:
              type: number
              example: 500000
            daily_deposit_limit:
              type: number
              example: 5000000
            transfer_limit:
              type: number
              example: 2000000
    responses:
      201:
        description: Compte créé
      400:
        description: Données invalides
      403:
        description: Accès refusé (Admin/Agent requis)
    """
    data = request.get_json(silent=True)
    if not data or not data.get("owner_id"):
        return error_response("owner_id est requis", 422)
    admin = get_current_user()
    account, err = AccountService.create_account(data["owner_id"], data, admin.id)
    if err:
        return error_response(err, 400)
    return success_response(account.to_dict(), "Compte créé avec succès", 201)


@accounts_bp.route("/<account_id>", methods=["GET"])
@jwt_required()
def get_account(account_id):
    """
    Détail d'un compte
    ---
    tags:
      - Comptes
    summary: Récupérer les informations d'un compte spécifique
    produces:
      - application/json
    parameters:
      - in: header
        name: Authorization
        type: string
        required: true
        description: "Bearer <access_token>"
      - in: path
        name: account_id
        type: string
        required: true
        description: Identifiant UUID du compte
    responses:
      200:
        description: Détails du compte
      403:
        description: Accès refusé
      404:
        description: Compte introuvable
    """
    user = get_current_user()
    account, err = AccountService.get_account(account_id, user)
    if err:
        code = 403 if "refusé" in err else 404
        return error_response(err, code)
    return success_response(account.to_dict())


@accounts_bp.route("/<account_id>/balance", methods=["GET"])
@jwt_required()
def get_balance(account_id):
    """
    Consulter le solde
    ---
    tags:
      - Comptes
    summary: Obtenir le solde en temps réel d'un compte
    produces:
      - application/json
    parameters:
      - in: header
        name: Authorization
        type: string
        required: true
        description: "Bearer <access_token>"
      - in: path
        name: account_id
        type: string
        required: true
        description: Identifiant UUID du compte
    responses:
      200:
        description: Solde du compte avec horodatage
      403:
        description: Accès refusé
      404:
        description: Compte introuvable
    """
    user = get_current_user()
    balance_data, err = AccountService.get_balance(account_id, user)
    if err:
        code = 403 if "refusé" in err else 404
        return error_response(err, code)
    return success_response(balance_data)


@accounts_bp.route("/<account_id>/status", methods=["PATCH"])
@jwt_required()
@roles_required(UserRole.ADMIN, UserRole.SUPERVISOR)
def update_status(account_id):
    """
    Modifier le statut d'un compte
    ---
    tags:
      - Comptes
    summary: Activer, suspendre, geler ou fermer un compte (Admin/Superviseur)
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
        name: account_id
        type: string
        required: true
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - status
          properties:
            status:
              type: string
              enum: [actif, suspendu, gele, ferme]
              example: suspendu
            reason:
              type: string
              example: "Activité suspecte détectée"
    responses:
      200:
        description: Statut mis à jour
      400:
        description: Statut invalide
      403:
        description: Accès refusé
      404:
        description: Compte introuvable
    """
    data   = request.get_json(silent=True) or {}
    status = data.get("status")
    reason = data.get("reason", "")
    if not status:
        return error_response("Le champ 'status' est requis", 422)
    admin = get_current_user()
    account, err = AccountService.update_status(account_id, status, reason, admin.id)
    if err:
        return error_response(err, 400)
    return success_response(account.to_dict(), "Statut mis à jour")


@accounts_bp.route("/<account_id>/limits", methods=["PATCH"])
@jwt_required()
@roles_required(UserRole.ADMIN)
def update_limits(account_id):
    """
    Modifier les plafonds d'un compte
    ---
    tags:
      - Comptes
    summary: Mettre à jour les plafonds de transaction d'un compte (Admin)
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
        name: account_id
        type: string
        required: true
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            daily_withdrawal_limit:
              type: number
              example: 1000000
            daily_deposit_limit:
              type: number
              example: 10000000
            transfer_limit:
              type: number
              example: 5000000
    responses:
      200:
        description: Plafonds mis à jour
      403:
        description: Accès refusé (Admin requis)
      404:
        description: Compte introuvable
    """
    data  = request.get_json(silent=True) or {}
    admin = get_current_user()
    account, err = AccountService.update_limits(account_id, data, admin.id)
    if err:
        return error_response(err, 400)
    return success_response(account.to_dict(), "Plafonds mis à jour")


@accounts_bp.route("/<account_id>", methods=["DELETE"])
@jwt_required()
@roles_required(UserRole.ADMIN)
def close_account(account_id):
    """
    Fermer un compte
    ---
    tags:
      - Comptes
    summary: Fermer définitivement un compte bancaire (Admin)
    description: Ferme définitivement un compte. Le solde doit être nul.
    produces:
      - application/json
    parameters:
      - in: header
        name: Authorization
        type: string
        required: true
        description: "Bearer <access_token>"
      - in: path
        name: account_id
        type: string
        required: true
    responses:
      200:
        description: Compte fermé avec succès
      400:
        description: Solde non nul — fermeture impossible
      403:
        description: Accès refusé (Admin requis)
      404:
        description: Compte introuvable
    """
    admin = get_current_user()
    ok, err = AccountService.close_account(account_id, admin.id)
    if not ok:
        code = 404 if "introuvable" in err else 400
        return error_response(err, code)
    return success_response(message="Compte fermé avec succès")


@accounts_bp.route("/<account_id>/transactions", methods=["GET"])
@jwt_required()
def get_account_transactions(account_id):
    """
    Historique des transactions d'un compte
    ---
    tags:
      - Comptes
    summary: Récupérer l'historique paginé des transactions d'un compte
    produces:
      - application/json
    parameters:
      - in: header
        name: Authorization
        type: string
        required: true
        description: "Bearer <access_token>"
      - in: path
        name: account_id
        type: string
        required: true
      - in: query
        name: page
        type: integer
        default: 1
      - in: query
        name: per_page
        type: integer
        default: 20
      - in: query
        name: status
        type: string
        enum: [pending, completed, failed, cancelled, en_revision]
      - in: query
        name: type
        type: string
        enum: [depot, retrait, virement, frais]
    responses:
      200:
        description: Liste paginée des transactions
      403:
        description: Accès refusé
      404:
        description: Compte introuvable
    """
    from app import db
    user = get_current_user()
    account, err = AccountService.get_account(account_id, user)
    if err:
        code = 403 if "refusé" in err else 404
        return error_response(err, code)

    query = Transaction.query.filter(
        or_(
            Transaction.source_account_id == account_id,
            Transaction.target_account_id == account_id
        )
    )
    if request.args.get("status"):
        query = query.filter(Transaction.status == request.args["status"])
    if request.args.get("type"):
        query = query.filter(Transaction.transaction_type == request.args["type"])

    query = query.order_by(Transaction.created_at.desc())
    items, meta = paginate(query)
    return success_response([t.to_dict() for t in items], f"{meta['total_items']} transaction(s)", meta=meta)
