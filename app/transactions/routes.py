"""
Module Transactions — Routes Flask.
Dépôts, retraits, virements, validation, annulation, historique.
"""
from flask import Blueprint, request
from app.common.jwt_utils import jwt_required
from app.transactions.service import TransactionService
from app.common.utils import success_response, error_response, get_current_user, roles_required, paginate
from app.models import Transaction, UserRole, TransactionStatus
from sqlalchemy import or_

transactions_bp = Blueprint("transactions", __name__)


@transactions_bp.route("/deposit", methods=["POST"])
@jwt_required()
def deposit():
    """
    Effectuer un dépôt
    ---
    tags:
      - Transactions
    summary: Créditer un compte bancaire
    description: |
      Crédite un montant sur un compte actif.
      Vérifie le plafond journalier. Les montants élevés passent en révision superviseur.
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
            - account_id
            - amount
          properties:
            account_id:
              type: string
              description: ID du compte à créditer
              example: "uuid-du-compte"
            amount:
              type: number
              description: Montant en XAF (doit être supérieur à 0)
              example: 150000
            description:
              type: string
              example: "Versement salaire"
            channel:
              type: string
              enum: [web, mobile, guichet, dab, api]
              default: api
    responses:
      201:
        description: Dépôt effectué ou en attente de validation
      400:
        description: Plafond dépassé ou compte inactif
      401:
        description: Non authentifié
      422:
        description: Champs requis manquants
    """
    data = request.get_json(silent=True)
    if not data or not data.get("account_id") or not data.get("amount"):
        return error_response("account_id et amount sont requis", 422)
    user = get_current_user()
    txn, err = TransactionService.deposit(data, user.id)
    if err:
        return error_response(err, 400)
    msg = ("Dépôt soumis — en attente de validation superviseur"
           if txn.status.value == "en_revision" else "Dépôt effectué avec succès")
    return success_response(txn.to_dict(), msg, 201)


@transactions_bp.route("/withdrawal", methods=["POST"])
@jwt_required()
def withdrawal():
    """
    Effectuer un retrait
    ---
    tags:
      - Transactions
    summary: Débiter un compte bancaire
    description: |
      Débite un montant d'un compte actif.
      Vérifie solde disponible et plafond journalier. Frais 0.5% pour retrait DAB.
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
            - account_id
            - amount
          properties:
            account_id:
              type: string
              example: "uuid-du-compte"
            amount:
              type: number
              example: 50000
            description:
              type: string
              example: "Retrait DAB Akwa"
            channel:
              type: string
              enum: [web, mobile, guichet, dab, api]
              default: guichet
    responses:
      201:
        description: Retrait effectué ou en attente de validation
      400:
        description: Solde insuffisant ou plafond dépassé
      401:
        description: Non authentifié
      422:
        description: Champs requis manquants
    """
    data = request.get_json(silent=True)
    if not data or not data.get("account_id") or not data.get("amount"):
        return error_response("account_id et amount sont requis", 422)
    user = get_current_user()
    txn, err = TransactionService.withdrawal(data, user.id)
    if err:
        return error_response(err, 400)
    msg = ("Retrait soumis — en attente de validation superviseur"
           if txn.status.value == "en_revision" else "Retrait effectué avec succès")
    return success_response(txn.to_dict(), msg, 201)


@transactions_bp.route("/transfer", methods=["POST"])
@jwt_required()
def transfer():
    """
    Effectuer un virement
    ---
    tags:
      - Transactions
    summary: Virement entre deux comptes
    description: |
      Transfère un montant d'un compte source vers un compte cible.
      Vérifie solde et plafond de virement. Notifications envoyées aux deux parties.
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
            - source_account_id
            - target_account_id
            - amount
          properties:
            source_account_id:
              type: string
              example: "uuid-compte-source"
            target_account_id:
              type: string
              example: "uuid-compte-cible"
            amount:
              type: number
              example: 100000
            description:
              type: string
              example: "Loyer Janvier 2025"
            channel:
              type: string
              enum: [web, mobile, guichet, dab, api]
              default: web
    responses:
      201:
        description: Virement effectué ou en attente de validation
      400:
        description: Solde insuffisant ou plafond dépassé
      401:
        description: Non authentifié
      422:
        description: Champs requis manquants
    """
    data = request.get_json(silent=True)
    required = ["source_account_id", "target_account_id", "amount"]
    missing  = [f for f in required if not data.get(f)] if data else required
    if missing:
        return error_response(f"Champs requis : {missing}", 422)
    user = get_current_user()
    txn, err = TransactionService.transfer(data, user.id)
    if err:
        return error_response(err, 400)
    msg = ("Virement soumis — en attente de validation superviseur"
           if txn.status.value == "en_revision" else "Virement effectué avec succès")
    return success_response(txn.to_dict(), msg, 201)


@transactions_bp.route("/pending", methods=["GET"])
@jwt_required()
@roles_required(UserRole.SUPERVISOR, UserRole.ADMIN)
def list_pending():
    """
    Transactions en attente de validation
    ---
    tags:
      - Transactions
    summary: Lister les transactions à montant élevé en attente (Superviseur/Admin)
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
        default: 20
    responses:
      200:
        description: Liste des transactions en révision
      403:
        description: Accès refusé
    """
    query = Transaction.query.filter_by(
        status=TransactionStatus.REVIEWING
    ).order_by(Transaction.created_at.asc())
    items, meta = paginate(query)
    return success_response([t.to_dict() for t in items],
                            f"{meta['total_items']} transaction(s) en attente", meta=meta)


@transactions_bp.route("", methods=["GET"])
@jwt_required()
def list_transactions():
    """
    Lister les transactions
    ---
    tags:
      - Transactions
    summary: Récupérer l'historique paginé de toutes les transactions
    description: Un client voit ses propres transactions. Admin/Superviseur voient tout.
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
      401:
        description: Non authentifié
    """
    user  = get_current_user()
    query = Transaction.query
    if user.role == UserRole.CLIENT:
        account_ids = [a.id for a in user.accounts.all()]
        query = query.filter(
            or_(
                Transaction.source_account_id.in_(account_ids),
                Transaction.target_account_id.in_(account_ids),
            )
        )
    if request.args.get("status"):
        query = query.filter(Transaction.status == request.args["status"])
    if request.args.get("type"):
        query = query.filter(Transaction.transaction_type == request.args["type"])
    query = query.order_by(Transaction.created_at.desc())
    items, meta = paginate(query)
    return success_response([t.to_dict() for t in items],
                            f"{meta['total_items']} transaction(s)", meta=meta)


@transactions_bp.route("/<txn_id>", methods=["GET"])
@jwt_required()
def get_transaction(txn_id):
    """
    Détail d'une transaction
    ---
    tags:
      - Transactions
    summary: Récupérer les détails complets d'une transaction
    produces:
      - application/json
    parameters:
      - in: header
        name: Authorization
        type: string
        required: true
        description: "Bearer <access_token>"
      - in: path
        name: txn_id
        type: string
        required: true
        description: ID de la transaction
    responses:
      200:
        description: Détails de la transaction
      403:
        description: Accès refusé
      404:
        description: Transaction introuvable
    """
    user = get_current_user()
    txn, err = TransactionService.get_transaction(txn_id, user)
    if err:
        code = 403 if "refusé" in err else 404
        return error_response(err, code)
    return success_response(txn.to_dict())


@transactions_bp.route("/<txn_id>/validate", methods=["POST"])
@jwt_required()
@roles_required(UserRole.SUPERVISOR, UserRole.ADMIN)
def validate_transaction(txn_id):
    """
    Valider une transaction à montant élevé
    ---
    tags:
      - Transactions
    summary: Approuver une transaction en attente de validation (Superviseur/Admin)
    produces:
      - application/json
    parameters:
      - in: header
        name: Authorization
        type: string
        required: true
        description: "Bearer <access_token>"
      - in: path
        name: txn_id
        type: string
        required: true
        description: ID de la transaction à valider
    responses:
      200:
        description: Transaction validée et exécutée
      400:
        description: Transaction non éligible à la validation
      403:
        description: Accès refusé
      404:
        description: Transaction introuvable
    """
    user = get_current_user()
    txn, err = TransactionService.validate_high_value(txn_id, user.id)
    if err:
        code = 404 if "introuvable" in err else 400
        return error_response(err, code)
    return success_response(txn.to_dict(), "Transaction validée et exécutée")


@transactions_bp.route("/<txn_id>/cancel", methods=["POST"])
@jwt_required()
def cancel_transaction(txn_id):
    """
    Annuler une transaction
    ---
    tags:
      - Transactions
    summary: Annuler une transaction en attente (pending ou en_revision)
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
        name: txn_id
        type: string
        required: true
      - in: body
        name: body
        required: false
        schema:
          type: object
          properties:
            reason:
              type: string
              example: "Erreur de saisie"
    responses:
      200:
        description: Transaction annulée
      400:
        description: Transaction non annulable
      404:
        description: Transaction introuvable
    """
    data   = request.get_json(silent=True) or {}
    reason = data.get("reason", "Annulation demandée")
    user   = get_current_user()
    txn, err = TransactionService.cancel_transaction(txn_id, reason, user.id)
    if err:
        code = 404 if "introuvable" in err else 400
        return error_response(err, code)
    return success_response(txn.to_dict(), "Transaction annulée")
