"""
Service de transactions bancaires.
Gère les dépôts, retraits, virements avec vérification des plafonds,
du solde et la journalisation complète.
"""
from datetime import datetime, date

from flask import current_app
from sqlalchemy import func

from app import db
from app.models import (
    Account, AccountStatus, Transaction, TransactionType,
    TransactionStatus, TransactionChannel, Notification, NotifChannel, NotifStatus
)
from app.common.utils import generate_transaction_ref, log_audit


class TransactionService:

    # ─── Helpers privés ───────────────────────────────────────────────────────
    @staticmethod
    def _get_active_account(account_id: str):
        account = db.session.get(Account, account_id)
        if not account:
            return None, "Compte introuvable"
        if account.status != AccountStatus.ACTIVE:
            return None, f"Compte {account.status.value} — opération impossible"
        return account, None

    @staticmethod
    def _daily_total(account_id: str, txn_type: TransactionType) -> float:
        """Calcule le total des transactions d'un type donné pour la journée."""
        today_start = datetime.combine(date.today(), datetime.min.time())
        result = db.session.query(func.sum(Transaction.amount)).filter(
            Transaction.source_account_id == account_id,
            Transaction.transaction_type  == txn_type,
            Transaction.status            == TransactionStatus.COMPLETED,
            Transaction.created_at        >= today_start,
        ).scalar()
        return float(result or 0)

    @staticmethod
    def _create_notification(user_id: str, transaction: Transaction, message: str, subject: str):
        notif = Notification(
            user_id        = user_id,
            transaction_id = transaction.id,
            channel        = NotifChannel.EMAIL,
            status         = NotifStatus.SENT,
            subject        = subject,
            body           = message,
            sent_at        = datetime.utcnow(),
        )
        db.session.add(notif)

    # ─── Dépôt ────────────────────────────────────────────────────────────────
    @staticmethod
    def deposit(data: dict, initiated_by_id: str):
        """
        Crédite un compte.
        Vérifie le plafond journalier de dépôt.
        """
        account, err = TransactionService._get_active_account(data["account_id"])
        if err:
            return None, err

        amount = float(data["amount"])
        if amount <= 0:
            return None, "Le montant doit être positif"

        # Vérification plafond journalier dépôt
        if account.daily_deposit_limit:
            daily_total = TransactionService._daily_total(account.id, TransactionType.DEPOSIT)
            if daily_total + amount > float(account.daily_deposit_limit):
                return None, (f"Plafond journalier de dépôt atteint "
                              f"({float(account.daily_deposit_limit):,.0f} {account.currency})")

        # Vérification montant élevé
        high_value = current_app.config["HIGH_VALUE_THRESHOLD"]
        status = (TransactionStatus.REVIEWING
                  if amount >= high_value else TransactionStatus.COMPLETED)

        txn = Transaction(
            reference        = generate_transaction_ref("DEP"),
            transaction_type = TransactionType.DEPOSIT,
            status           = status,
            amount           = amount,
            currency         = account.currency,
            fee              = 0.00,
            description      = data.get("description", "Dépôt"),
            channel          = TransactionChannel(data.get("channel", "api")),
            target_account_id = account.id,
            initiated_by     = initiated_by_id,
        )
        db.session.add(txn)

        # Créditer immédiatement si pas en révision
        if status == TransactionStatus.COMPLETED:
            account.balance = float(account.balance) + amount
            txn.executed_at = datetime.utcnow()
            TransactionService._create_notification(
                account.owner_id, txn,
                f"Votre compte {account.account_number} a été crédité de "
                f"{amount:,.0f} {account.currency}. Référence : {txn.reference}",
                "Confirmation de dépôt"
            )

        db.session.commit()
        log_audit("DEPOSIT", "transactions", txn.id,
                  {"amount": amount, "account": account.account_number, "status": status.value},
                  user_id=initiated_by_id)
        return txn, None

    # ─── Retrait ──────────────────────────────────────────────────────────────
    @staticmethod
    def withdrawal(data: dict, initiated_by_id: str):
        """
        Débite un compte.
        Vérifie le solde disponible et le plafond journalier de retrait.
        """
        account, err = TransactionService._get_active_account(data["account_id"])
        if err:
            return None, err

        amount = float(data["amount"])
        if amount <= 0:
            return None, "Le montant doit être positif"

        # Vérification du solde
        if float(account.balance) < amount:
            return None, (f"Solde insuffisant. Disponible : "
                          f"{float(account.balance):,.0f} {account.currency}")

        # Vérification plafond journalier retrait
        if account.daily_withdrawal_limit:
            daily_total = TransactionService._daily_total(account.id, TransactionType.WITHDRAWAL)
            if daily_total + amount > float(account.daily_withdrawal_limit):
                return None, (f"Plafond journalier de retrait atteint "
                              f"({float(account.daily_withdrawal_limit):,.0f} {account.currency})")

        # Montant élevé → révision superviseur
        high_value = current_app.config["HIGH_VALUE_THRESHOLD"]
        status     = (TransactionStatus.REVIEWING
                      if amount >= high_value else TransactionStatus.COMPLETED)

        # Frais de retrait DAB (exemple : 0.5%)
        channel = TransactionChannel(data.get("channel", "api"))
        fee = round(amount * 0.005, 2) if channel == TransactionChannel.ATM else 0.00

        txn = Transaction(
            reference        = generate_transaction_ref("RET"),
            transaction_type = TransactionType.WITHDRAWAL,
            status           = status,
            amount           = amount,
            currency         = account.currency,
            fee              = fee,
            description      = data.get("description", "Retrait"),
            channel          = channel,
            source_account_id = account.id,
            initiated_by     = initiated_by_id,
        )
        db.session.add(txn)

        if status == TransactionStatus.COMPLETED:
            account.balance = float(account.balance) - amount - fee
            txn.executed_at = datetime.utcnow()
            TransactionService._create_notification(
                account.owner_id, txn,
                f"Retrait de {amount:,.0f} {account.currency} effectué sur "
                f"votre compte {account.account_number}. "
                f"Nouveau solde : {float(account.balance):,.0f} {account.currency}.",
                "Confirmation de retrait"
            )

        db.session.commit()
        log_audit("WITHDRAWAL", "transactions", txn.id,
                  {"amount": amount, "fee": fee, "account": account.account_number},
                  user_id=initiated_by_id)
        return txn, None

    # ─── Virement ─────────────────────────────────────────────────────────────
    @staticmethod
    def transfer(data: dict, initiated_by_id: str):
        """
        Virement entre deux comptes.
        Vérifie solde, plafond de virement et statut des deux comptes.
        """
        source_account, err = TransactionService._get_active_account(data["source_account_id"])
        if err:
            return None, f"Compte source : {err}"

        target_account, err = TransactionService._get_active_account(data["target_account_id"])
        if err:
            return None, f"Compte cible : {err}"

        if source_account.id == target_account.id:
            return None, "Les comptes source et cible doivent être différents"

        amount = float(data["amount"])
        if amount <= 0:
            return None, "Le montant doit être positif"

        # Vérification solde
        if float(source_account.balance) < amount:
            return None, (f"Solde insuffisant. Disponible : "
                          f"{float(source_account.balance):,.0f} {source_account.currency}")

        # Vérification plafond de virement
        if source_account.transfer_limit and amount > float(source_account.transfer_limit):
            return None, (f"Montant supérieur au plafond de virement "
                          f"({float(source_account.transfer_limit):,.0f} {source_account.currency})")

        # Montant élevé → révision
        high_value = current_app.config["HIGH_VALUE_THRESHOLD"]
        status     = (TransactionStatus.REVIEWING
                      if amount >= high_value else TransactionStatus.COMPLETED)

        txn = Transaction(
            reference         = generate_transaction_ref("VIR"),
            transaction_type  = TransactionType.TRANSFER,
            status            = status,
            amount            = amount,
            currency          = source_account.currency,
            fee               = 0.00,
            description       = data.get("description", "Virement"),
            channel           = TransactionChannel(data.get("channel", "api")),
            source_account_id = source_account.id,
            target_account_id = target_account.id,
            initiated_by      = initiated_by_id,
        )
        db.session.add(txn)

        if status == TransactionStatus.COMPLETED:
            source_account.balance = float(source_account.balance) - amount
            target_account.balance = float(target_account.balance) + amount
            txn.executed_at = datetime.utcnow()

            TransactionService._create_notification(
                source_account.owner_id, txn,
                f"Virement de {amount:,.0f} {source_account.currency} vers "
                f"{target_account.account_number} effectué. Réf : {txn.reference}",
                "Confirmation de virement"
            )
            TransactionService._create_notification(
                target_account.owner_id, txn,
                f"Votre compte {target_account.account_number} a reçu "
                f"{amount:,.0f} {source_account.currency}. Réf : {txn.reference}",
                "Réception de virement"
            )

        db.session.commit()
        log_audit("TRANSFER", "transactions", txn.id,
                  {"amount": amount, "from": source_account.account_number,
                   "to": target_account.account_number},
                  user_id=initiated_by_id)
        return txn, None

    # ─── Valider un montant élevé (superviseur) ───────────────────────────────
    @staticmethod
    def validate_high_value(txn_id: str, supervisor_id: str):
        txn = db.session.get(Transaction, txn_id)
        if not txn:
            return None, "Transaction introuvable"
        if txn.status != TransactionStatus.REVIEWING:
            return None, "Cette transaction n'est pas en attente de validation"

        # Exécuter la transaction
        if txn.transaction_type == TransactionType.DEPOSIT and txn.target_account_id:
            account = db.session.get(Account, txn.target_account_id)
            account.balance = float(account.balance) + float(txn.amount)

        elif txn.transaction_type == TransactionType.WITHDRAWAL and txn.source_account_id:
            account = db.session.get(Account, txn.source_account_id)
            if float(account.balance) < float(txn.amount):
                return None, "Solde insuffisant pour exécuter le retrait"
            account.balance = float(account.balance) - float(txn.amount) - float(txn.fee)

        elif txn.transaction_type == TransactionType.TRANSFER:
            src = db.session.get(Account, txn.source_account_id)
            tgt = db.session.get(Account, txn.target_account_id)
            if float(src.balance) < float(txn.amount):
                return None, "Solde insuffisant pour exécuter le virement"
            src.balance = float(src.balance) - float(txn.amount)
            tgt.balance = float(tgt.balance) + float(txn.amount)

        txn.status       = TransactionStatus.COMPLETED
        txn.validated_by = supervisor_id
        txn.validated_at = datetime.utcnow()
        txn.executed_at  = datetime.utcnow()
        db.session.commit()

        log_audit("TRANSACTION_VALIDATED", "transactions", txn_id, user_id=supervisor_id)
        return txn, None

    # ─── Annuler une transaction ──────────────────────────────────────────────
    @staticmethod
    def cancel_transaction(txn_id: str, reason: str, user_id: str):
        txn = db.session.get(Transaction, txn_id)
        if not txn:
            return None, "Transaction introuvable"
        if txn.status not in (TransactionStatus.PENDING, TransactionStatus.REVIEWING):
            return None, "Seules les transactions en attente peuvent être annulées"

        txn.status         = TransactionStatus.CANCELLED
        txn.failure_reason = reason
        db.session.commit()

        log_audit("TRANSACTION_CANCELLED", "transactions", txn_id,
                  {"reason": reason}, user_id=user_id)
        return txn, None

    # ─── Détail d'une transaction ─────────────────────────────────────────────
    @staticmethod
    def get_transaction(txn_id: str, requesting_user):
        from app.models import UserRole
        txn = db.session.get(Transaction, txn_id)
        if not txn:
            return None, "Transaction introuvable"

        # Un client ne peut voir que ses propres transactions
        if requesting_user.role == UserRole.CLIENT:
            user_account_ids = [a.id for a in requesting_user.accounts.all()]
            if (txn.source_account_id not in user_account_ids and
                    txn.target_account_id not in user_account_ids):
                return None, "Accès refusé"

        return txn, None
