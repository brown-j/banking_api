"""
Service de gestion des comptes bancaires.
"""
from datetime import date, datetime

from flask import current_app

from app import db
from app.models import Account, AccountType, AccountStatus, User, UserRole
from app.common.utils import generate_account_number, log_audit, paginate


class AccountService:

    # ── Créer un compte ───────────────────────────────────────────────────────
    @staticmethod
    def create_account(owner_id: str, data: dict, created_by_id: str):
        """Crée un nouveau compte pour un client existant."""
        owner = db.session.get(User, owner_id)
        if not owner:
            return None, "Client introuvable"
        if owner.role != UserRole.CLIENT:
            return None, "Un compte ne peut être créé que pour un client"

        try:
            account_type = AccountType(data.get("account_type", "courant"))
        except ValueError:
            return None, f"Type de compte invalide. Valeurs : {[t.value for t in AccountType]}"

        account = Account(
            owner_id       = owner_id,
            account_number = generate_account_number(),
            account_type   = account_type,
            currency       = data.get("currency", "XAF").upper(),
            daily_withdrawal_limit = data.get("daily_withdrawal_limit",
                                               current_app.config["DEFAULT_DAILY_WITHDRAWAL_LIMIT"]),
            daily_deposit_limit    = data.get("daily_deposit_limit",
                                               current_app.config["DEFAULT_DAILY_DEPOSIT_LIMIT"]),
            transfer_limit         = data.get("transfer_limit",
                                               current_app.config["DEFAULT_TRANSFER_LIMIT"]),
        )
        db.session.add(account)
        db.session.commit()
        log_audit("ACCOUNT_CREATE", "accounts", account.id,
                  {"owner_id": owner_id, "type": account_type.value},
                  user_id=created_by_id)
        return account, None

    # ── Lister les comptes d'un client ────────────────────────────────────────
    @staticmethod
    def get_accounts_for_user(user_id: str):
        """Retourne tous les comptes actifs d'un client."""
        accounts = Account.query.filter_by(owner_id=user_id).all()
        return accounts

    # ── Détail d'un compte ────────────────────────────────────────────────────
    @staticmethod
    def get_account(account_id: str, requesting_user: User):
        """
        Retourne un compte.
        Un client ne peut voir que ses propres comptes.
        Les agents/admin peuvent voir tous les comptes.
        """
        account = db.session.get(Account, account_id)
        if not account:
            return None, "Compte introuvable"

        if requesting_user.role == UserRole.CLIENT and account.owner_id != requesting_user.id:
            return None, "Accès refusé"

        return account, None

    # ── Solde en temps réel ───────────────────────────────────────────────────
    @staticmethod
    def get_balance(account_id: str, requesting_user: User):
        account, err = AccountService.get_account(account_id, requesting_user)
        if err:
            return None, err
        return {
            "account_id":     account.id,
            "account_number": account.account_number,
            "balance":        float(account.balance),
            "currency":       account.currency,
            "status":         account.status.value,
            "as_of":          datetime.utcnow().isoformat() + "Z",
        }, None

    # ── Mettre à jour le statut ───────────────────────────────────────────────
    @staticmethod
    def update_status(account_id: str, new_status: str, reason: str, admin_id: str):
        account = db.session.get(Account, account_id)
        if not account:
            return None, "Compte introuvable"

        try:
            status = AccountStatus(new_status)
        except ValueError:
            return None, f"Statut invalide. Valeurs : {[s.value for s in AccountStatus]}"

        old_status = account.status.value
        account.status = status
        if status == AccountStatus.CLOSED:
            account.closed_at = date.today()

        db.session.commit()
        log_audit("ACCOUNT_STATUS_UPDATE", "accounts", account_id,
                  {"old": old_status, "new": new_status, "reason": reason},
                  user_id=admin_id)
        return account, None

    # ── Mettre à jour les plafonds ────────────────────────────────────────────
    @staticmethod
    def update_limits(account_id: str, data: dict, admin_id: str):
        account = db.session.get(Account, account_id)
        if not account:
            return None, "Compte introuvable"

        if "daily_withdrawal_limit" in data:
            account.daily_withdrawal_limit = float(data["daily_withdrawal_limit"])
        if "daily_deposit_limit" in data:
            account.daily_deposit_limit = float(data["daily_deposit_limit"])
        if "transfer_limit" in data:
            account.transfer_limit = float(data["transfer_limit"])

        db.session.commit()
        log_audit("ACCOUNT_LIMITS_UPDATE", "accounts", account_id, data, user_id=admin_id)
        return account, None

    # ── Supprimer / fermer définitivement ─────────────────────────────────────
    @staticmethod
    def close_account(account_id: str, admin_id: str):
        account = db.session.get(Account, account_id)
        if not account:
            return False, "Compte introuvable"
        if float(account.balance) != 0:
            return False, "Impossible de fermer un compte avec un solde non nul"

        account.status    = AccountStatus.CLOSED
        account.closed_at = date.today()
        db.session.commit()
        log_audit("ACCOUNT_CLOSE", "accounts", account_id, user_id=admin_id)
        return True, None
