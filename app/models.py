"""
Modèles SQLAlchemy — Toutes les entités de la base de données.
"""
import uuid
from datetime import datetime, date
from enum import Enum as PyEnum

from app import db


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def gen_uuid():
    return str(uuid.uuid4())


# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────
class UserRole(PyEnum):
    CLIENT      = "client"
    AGENT       = "agent"
    ADMIN       = "admin"
    SUPERVISOR  = "supervisor"
    AUDITOR     = "auditor"
    IT          = "it"


class KycStatus(PyEnum):
    PENDING   = "pending"
    VERIFIED  = "verified"
    REJECTED  = "rejected"


class AccountType(PyEnum):
    CURRENT      = "courant"
    SAVINGS      = "epargne"
    PROFESSIONAL = "professionnel"


class AccountStatus(PyEnum):
    ACTIVE    = "actif"
    SUSPENDED = "suspendu"
    CLOSED    = "ferme"
    FROZEN    = "gele"


class TransactionType(PyEnum):
    DEPOSIT    = "depot"
    WITHDRAWAL = "retrait"
    TRANSFER   = "virement"
    FEE        = "frais"
    REVERSAL   = "annulation"


class TransactionStatus(PyEnum):
    PENDING   = "pending"
    COMPLETED = "completed"
    FAILED    = "failed"
    CANCELLED = "cancelled"
    REVIEWING = "en_revision"   # montant élevé — en attente superviseur


class TransactionChannel(PyEnum):
    WEB     = "web"
    MOBILE  = "mobile"
    COUNTER = "guichet"
    ATM     = "dab"
    API     = "api"


class NotifChannel(PyEnum):
    SMS   = "sms"
    EMAIL = "email"
    PUSH  = "push"


class NotifStatus(PyEnum):
    PENDING = "pending"
    SENT    = "sent"
    FAILED  = "failed"


# ─────────────────────────────────────────────────────────────────────────────
# Modèle : User (interne + client)
# ─────────────────────────────────────────────────────────────────────────────
class User(db.Model):
    __tablename__ = "users"

    id                = db.Column(db.String(36),  primary_key=True, default=gen_uuid)
    email             = db.Column(db.String(150), unique=True, nullable=False, index=True)
    password_hash     = db.Column(db.String(256), nullable=False)
    first_name        = db.Column(db.String(100), nullable=False)
    last_name         = db.Column(db.String(100), nullable=False)
    phone             = db.Column(db.String(20),  unique=True, nullable=True)
    date_of_birth     = db.Column(db.Date,        nullable=True)
    role              = db.Column(db.Enum(UserRole), nullable=False, default=UserRole.CLIENT)
    kyc_status        = db.Column(db.Enum(KycStatus), nullable=False, default=KycStatus.PENDING)
    is_active         = db.Column(db.Boolean,     nullable=False, default=True)
    login_attempts    = db.Column(db.Integer,     nullable=False, default=0)
    locked_until      = db.Column(db.DateTime,    nullable=True)
    last_login        = db.Column(db.DateTime,    nullable=True)
    created_at        = db.Column(db.DateTime,    nullable=False, default=datetime.utcnow)
    updated_at        = db.Column(db.DateTime,    nullable=False, default=datetime.utcnow,
                                  onupdate=datetime.utcnow)

    # Relations
    accounts          = db.relationship("Account",      back_populates="owner",      lazy="dynamic")
    notifications     = db.relationship("Notification", back_populates="user",       lazy="dynamic")
    audit_logs        = db.relationship("AuditLog",     back_populates="user",       lazy="dynamic")
    notif_preferences = db.relationship("NotificationPreference", back_populates="user",
                                        uselist=False, cascade="all, delete-orphan")

    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    def to_dict(self):
        return {
            "id":          self.id,
            "email":       self.email,
            "first_name":  self.first_name,
            "last_name":   self.last_name,
            "phone":       self.phone,
            "role":        self.role.value,
            "kyc_status":  self.kyc_status.value,
            "is_active":   self.is_active,
            "last_login":  self.last_login.isoformat() if self.last_login else None,
            "created_at":  self.created_at.isoformat(),
        }

    def __repr__(self):
        return f"<User {self.email} [{self.role.value}]>"


# ─────────────────────────────────────────────────────────────────────────────
# Modèle : Account
# ─────────────────────────────────────────────────────────────────────────────
class Account(db.Model):
    __tablename__ = "accounts"

    id                      = db.Column(db.String(36),  primary_key=True, default=gen_uuid)
    owner_id                = db.Column(db.String(36),  db.ForeignKey("users.id"), nullable=False, index=True)
    account_number          = db.Column(db.String(30),  unique=True, nullable=False, index=True)
    account_type            = db.Column(db.Enum(AccountType),   nullable=False, default=AccountType.CURRENT)
    status                  = db.Column(db.Enum(AccountStatus), nullable=False, default=AccountStatus.ACTIVE)
    balance                 = db.Column(db.Numeric(18, 2), nullable=False, default=0.00)
    currency                = db.Column(db.String(3),   nullable=False, default="XAF")
    daily_withdrawal_limit  = db.Column(db.Numeric(18, 2), nullable=True)
    daily_deposit_limit     = db.Column(db.Numeric(18, 2), nullable=True)
    transfer_limit          = db.Column(db.Numeric(18, 2), nullable=True)
    opened_at               = db.Column(db.Date,        nullable=False, default=date.today)
    closed_at               = db.Column(db.Date,        nullable=True)
    created_at              = db.Column(db.DateTime,    nullable=False, default=datetime.utcnow)
    updated_at              = db.Column(db.DateTime,    nullable=False, default=datetime.utcnow,
                                        onupdate=datetime.utcnow)

    # Relations
    owner                   = db.relationship("User",        back_populates="accounts")
    outgoing_transactions   = db.relationship("Transaction", foreign_keys="Transaction.source_account_id",
                                              back_populates="source_account", lazy="dynamic")
    incoming_transactions   = db.relationship("Transaction", foreign_keys="Transaction.target_account_id",
                                              back_populates="target_account", lazy="dynamic")

    def to_dict(self):
        return {
            "id":             self.id,
            "account_number": self.account_number,
            "account_type":   self.account_type.value,
            "status":         self.status.value,
            "balance":        float(self.balance),
            "currency":       self.currency,
            "daily_withdrawal_limit": float(self.daily_withdrawal_limit) if self.daily_withdrawal_limit else None,
            "daily_deposit_limit":    float(self.daily_deposit_limit)    if self.daily_deposit_limit    else None,
            "transfer_limit":         float(self.transfer_limit)         if self.transfer_limit         else None,
            "owner_id":       self.owner_id,
            "opened_at":      self.opened_at.isoformat(),
            "created_at":     self.created_at.isoformat(),
        }

    def __repr__(self):
        return f"<Account {self.account_number} [{self.account_type.value}]>"


# ─────────────────────────────────────────────────────────────────────────────
# Modèle : Transaction
# ─────────────────────────────────────────────────────────────────────────────
class Transaction(db.Model):
    __tablename__ = "transactions"

    id                  = db.Column(db.String(36),  primary_key=True, default=gen_uuid)
    reference           = db.Column(db.String(50),  unique=True, nullable=False, index=True)
    transaction_type    = db.Column(db.Enum(TransactionType),   nullable=False)
    status              = db.Column(db.Enum(TransactionStatus), nullable=False, default=TransactionStatus.PENDING)
    amount              = db.Column(db.Numeric(18, 2), nullable=False)
    currency            = db.Column(db.String(3),   nullable=False, default="XAF")
    fee                 = db.Column(db.Numeric(18, 2), nullable=False, default=0.00)
    description         = db.Column(db.Text,        nullable=True)
    channel             = db.Column(db.Enum(TransactionChannel), nullable=False, default=TransactionChannel.API)

    source_account_id   = db.Column(db.String(36), db.ForeignKey("accounts.id"), nullable=True)
    target_account_id   = db.Column(db.String(36), db.ForeignKey("accounts.id"), nullable=True)
    initiated_by        = db.Column(db.String(36), db.ForeignKey("users.id"),    nullable=False)

    # Montant élevé : ID du superviseur qui a validé
    validated_by        = db.Column(db.String(36), db.ForeignKey("users.id"),    nullable=True)
    validated_at        = db.Column(db.DateTime,   nullable=True)

    # Horodatage
    created_at          = db.Column(db.DateTime,   nullable=False, default=datetime.utcnow)
    executed_at         = db.Column(db.DateTime,   nullable=True)
    failure_reason      = db.Column(db.Text,       nullable=True)

    # Relations
    source_account  = db.relationship("Account", foreign_keys=[source_account_id],
                                       back_populates="outgoing_transactions")
    target_account  = db.relationship("Account", foreign_keys=[target_account_id],
                                       back_populates="incoming_transactions")
    initiator       = db.relationship("User", foreign_keys=[initiated_by])
    validator       = db.relationship("User", foreign_keys=[validated_by])
    notifications   = db.relationship("Notification", back_populates="transaction", lazy="dynamic")

    def to_dict(self):
        return {
            "id":               self.id,
            "reference":        self.reference,
            "transaction_type": self.transaction_type.value,
            "status":           self.status.value,
            "amount":           float(self.amount),
            "fee":              float(self.fee),
            "currency":         self.currency,
            "description":      self.description,
            "channel":          self.channel.value,
            "source_account_id": self.source_account_id,
            "target_account_id": self.target_account_id,
            "initiated_by":     self.initiated_by,
            "validated_by":     self.validated_by,
            "created_at":       self.created_at.isoformat(),
            "executed_at":      self.executed_at.isoformat() if self.executed_at else None,
            "failure_reason":   self.failure_reason,
        }

    def __repr__(self):
        return f"<Transaction {self.reference} [{self.transaction_type.value}] {self.amount} {self.currency}>"


# ─────────────────────────────────────────────────────────────────────────────
# Modèle : Notification
# ─────────────────────────────────────────────────────────────────────────────
class Notification(db.Model):
    __tablename__ = "notifications"

    id             = db.Column(db.String(36),  primary_key=True, default=gen_uuid)
    user_id        = db.Column(db.String(36),  db.ForeignKey("users.id"),        nullable=False, index=True)
    transaction_id = db.Column(db.String(36),  db.ForeignKey("transactions.id"), nullable=True)
    channel        = db.Column(db.Enum(NotifChannel),  nullable=False)
    status         = db.Column(db.Enum(NotifStatus),   nullable=False, default=NotifStatus.PENDING)
    subject        = db.Column(db.String(200), nullable=True)
    body           = db.Column(db.Text,        nullable=False)
    is_read        = db.Column(db.Boolean,     nullable=False, default=False)
    sent_at        = db.Column(db.DateTime,    nullable=True)
    created_at     = db.Column(db.DateTime,    nullable=False, default=datetime.utcnow)

    # Relations
    user        = db.relationship("User",        back_populates="notifications")
    transaction = db.relationship("Transaction", back_populates="notifications")

    def to_dict(self):
        return {
            "id":             self.id,
            "user_id":        self.user_id,
            "transaction_id": self.transaction_id,
            "channel":        self.channel.value,
            "status":         self.status.value,
            "subject":        self.subject,
            "body":           self.body,
            "is_read":        self.is_read,
            "sent_at":        self.sent_at.isoformat() if self.sent_at else None,
            "created_at":     self.created_at.isoformat(),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Modèle : NotificationPreference
# ─────────────────────────────────────────────────────────────────────────────
class NotificationPreference(db.Model):
    __tablename__ = "notification_preferences"

    id             = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    user_id        = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False, unique=True)
    sms_enabled    = db.Column(db.Boolean, nullable=False, default=True)
    email_enabled  = db.Column(db.Boolean, nullable=False, default=True)
    push_enabled   = db.Column(db.Boolean, nullable=False, default=True)
    low_balance_threshold = db.Column(db.Numeric(18, 2), nullable=True)
    daily_summary  = db.Column(db.Boolean, nullable=False, default=False)
    updated_at     = db.Column(db.DateTime, nullable=False, default=datetime.utcnow,
                               onupdate=datetime.utcnow)

    user = db.relationship("User", back_populates="notif_preferences")

    def to_dict(self):
        return {
            "user_id":               self.user_id,
            "sms_enabled":           self.sms_enabled,
            "email_enabled":         self.email_enabled,
            "push_enabled":          self.push_enabled,
            "low_balance_threshold": float(self.low_balance_threshold) if self.low_balance_threshold else None,
            "daily_summary":         self.daily_summary,
            "updated_at":            self.updated_at.isoformat(),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Modèle : AuditLog
# ─────────────────────────────────────────────────────────────────────────────
class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id          = db.Column(db.String(36),  primary_key=True, default=gen_uuid)
    user_id     = db.Column(db.String(36),  db.ForeignKey("users.id"), nullable=True, index=True)
    action      = db.Column(db.String(100), nullable=False)
    resource    = db.Column(db.String(100), nullable=True)
    resource_id = db.Column(db.String(36),  nullable=True)
    ip_address  = db.Column(db.String(45),  nullable=True)
    user_agent  = db.Column(db.String(300), nullable=True)
    details     = db.Column(db.Text,        nullable=True)   # JSON sérialisé
    success     = db.Column(db.Boolean,     nullable=False, default=True)
    created_at  = db.Column(db.DateTime,    nullable=False, default=datetime.utcnow, index=True)

    # Relations
    user = db.relationship("User", back_populates="audit_logs")

    def to_dict(self):
        return {
            "id":          self.id,
            "user_id":     self.user_id,
            "action":      self.action,
            "resource":    self.resource,
            "resource_id": self.resource_id,
            "ip_address":  self.ip_address,
            "details":     self.details,
            "success":     self.success,
            "created_at":  self.created_at.isoformat(),
        }

    def __repr__(self):
        return f"<AuditLog {self.action} by {self.user_id}>"
