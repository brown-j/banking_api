"""
Service d'authentification.
Contient toute la logique métier : login, register, refresh, logout, OTP.
"""
from datetime import datetime, timedelta

from flask import current_app
from app.common.jwt_utils import (
    create_access_token, create_refresh_token,
    get_jwt_identity, get_jwt
)

from app import db, bcrypt, BLACKLISTED_TOKENS
from app.models import User, UserRole, KycStatus, NotificationPreference
from app.common.utils import log_audit, generate_account_number
from app.models import Account, AccountType


class AuthService:

    # ── Inscription ───────────────────────────────────────────────────────────
    @staticmethod
    def register(data: dict):
        """
        Crée un nouveau client.
        Retourne (user, error_message).
        """
        # Vérification unicité email
        if User.query.filter_by(email=data["email"].lower()).first():
            return None, "Un compte avec cet e-mail existe déjà"

        # Vérification unicité téléphone
        if data.get("phone") and User.query.filter_by(phone=data["phone"]).first():
            return None, "Ce numéro de téléphone est déjà utilisé"

        # Hash du mot de passe
        pwd_hash = bcrypt.generate_password_hash(data["password"]).decode("utf-8")

        user = User(
            email         = data["email"].lower().strip(),
            password_hash = pwd_hash,
            first_name    = data["first_name"].strip(),
            last_name     = data["last_name"].strip(),
            phone         = data.get("phone"),
            date_of_birth = data.get("date_of_birth"),
            role          = UserRole.CLIENT,
            kyc_status    = KycStatus.PENDING,
        )
        db.session.add(user)
        db.session.flush()  # obtenir l'id avant commit

        # Créer les préférences de notification par défaut
        prefs = NotificationPreference(user_id=user.id)
        db.session.add(prefs)

        # Créer un compte courant par défaut
        account = Account(
            owner_id       = user.id,
            account_number = generate_account_number(),
            account_type   = AccountType.CURRENT,
            currency       = "XAF",
            daily_withdrawal_limit = current_app.config["DEFAULT_DAILY_WITHDRAWAL_LIMIT"],
            daily_deposit_limit    = current_app.config["DEFAULT_DAILY_DEPOSIT_LIMIT"],
            transfer_limit         = current_app.config["DEFAULT_TRANSFER_LIMIT"],
        )
        db.session.add(account)
        db.session.commit()

        log_audit("USER_REGISTER", "users", user.id, {"email": user.email}, user_id=user.id)
        return user, None

    # ── Connexion ─────────────────────────────────────────────────────────────
    @staticmethod
    def login(email: str, password: str):
        """
        Authentifie un utilisateur.
        Retourne (access_token, refresh_token, user, error_message).
        """
        user = User.query.filter_by(email=email.lower().strip()).first()

        if not user:
            return None, None, None, "Identifiants invalides"

        if not user.is_active:
            return None, None, None, "Compte désactivé. Contactez le support"

        # Vérification verrou
        if user.locked_until and user.locked_until > datetime.utcnow():
            remaining = int((user.locked_until - datetime.utcnow()).total_seconds() / 60)
            return None, None, None, f"Compte verrouillé. Réessayez dans {remaining} minutes"

        # Vérification mot de passe
        if not bcrypt.check_password_hash(user.password_hash, password):
            user.login_attempts += 1
            max_attempts = current_app.config["MAX_LOGIN_ATTEMPTS"]

            if user.login_attempts >= max_attempts:
                lockout = current_app.config["LOCKOUT_DURATION"]
                user.locked_until = datetime.utcnow() + timedelta(seconds=lockout)
                user.login_attempts = 0
                db.session.commit()
                log_audit("USER_LOCKED", "users", user.id, success=False)
                return None, None, None, f"Compte verrouillé après {max_attempts} tentatives"

            db.session.commit()
            remaining_attempts = max_attempts - user.login_attempts
            return None, None, None, f"Mot de passe incorrect. {remaining_attempts} tentative(s) restante(s)"

        # Succès
        user.login_attempts = 0
        user.locked_until   = None
        user.last_login     = datetime.utcnow()
        db.session.commit()

        access_token  = create_access_token(identity=user.id,
                                            additional_claims={"role": user.role.value})
        refresh_token = create_refresh_token(identity=user.id)

        log_audit("USER_LOGIN", "users", user.id, {"email": user.email}, user_id=user.id)
        return access_token, refresh_token, user, None

    # ── Refresh token ─────────────────────────────────────────────────────────
    @staticmethod
    def refresh():
        """Génère un nouveau access token depuis un refresh token valide."""
        user_id      = get_jwt_identity()
        user         = db.session.get(User, user_id)
        if not user or not user.is_active:
            return None, "Utilisateur introuvable ou inactif"

        access_token = create_access_token(identity=user_id,
                                           additional_claims={"role": user.role.value})
        log_audit("TOKEN_REFRESH", "users", user_id, user_id=user_id)
        return access_token, None

    # ── Déconnexion ───────────────────────────────────────────────────────────
    @staticmethod
    def logout():
        """Révoque le token JWT courant."""
        jti = get_jwt()["jti"]
        BLACKLISTED_TOKENS.add(jti)
        user_id = get_jwt_identity()
        log_audit("USER_LOGOUT", "users", user_id, user_id=user_id)

    # ── Changement de mot de passe ────────────────────────────────────────────
    @staticmethod
    def change_password(user_id: str, old_password: str, new_password: str):
        user = db.session.get(User, user_id)
        if not user:
            return False, "Utilisateur introuvable"
        if not bcrypt.check_password_hash(user.password_hash, old_password):
            return False, "Ancien mot de passe incorrect"
        if len(new_password) < 8:
            return False, "Le nouveau mot de passe doit contenir au moins 8 caractères"

        user.password_hash = bcrypt.generate_password_hash(new_password).decode("utf-8")
        db.session.commit()
        log_audit("PASSWORD_CHANGE", "users", user_id, user_id=user_id)
        return True, None
