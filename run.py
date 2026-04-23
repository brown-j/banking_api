"""
Point d'entrée principal de l'application Flask.
Initialise la base de données et démarre le serveur.

Usage :
    python run.py                        # Démarrage standard
    flask db init                        # Initialiser les migrations
    flask db migrate -m "init"           # Générer une migration
    flask db upgrade                     # Appliquer les migrations
    flask seed                           # Insérer des données de test
"""
import click
from flask.cli import with_appcontext

from app import create_app, db
from app.models import (
    User, UserRole, KycStatus, Account, AccountType,
    NotificationPreference
)
from app.common.utils import generate_account_number
from config import get_config

app = create_app()


# ─────────────────────────────────────────────────────────────────────────────
# Commande CLI : seed — données de démonstration
# ─────────────────────────────────────────────────────────────────────────────
@app.cli.command("seed")
@with_appcontext
def seed_db():
    """Insère des données de démonstration dans la base de données."""
    from app import bcrypt

    click.echo("🌱  Création des données de démonstration...")

    # Suppression des données existantes (dev uniquement)
    db.drop_all()
    db.create_all()

    # ── Admin ─────────────────────────────────────────────────────────────────
    admin = User(
        email         = "admin@banque.cm",
        password_hash = bcrypt.generate_password_hash("Admin123!").decode("utf-8"),
        first_name    = "Super",
        last_name     = "Admin",
        phone         = "+237699000001",
        role          = UserRole.ADMIN,
        kyc_status    = KycStatus.VERIFIED,
    )
    db.session.add(admin)

    # ── Superviseur ───────────────────────────────────────────────────────────
    supervisor = User(
        email         = "superviseur@banque.cm",
        password_hash = bcrypt.generate_password_hash("Super123!").decode("utf-8"),
        first_name    = "Paul",
        last_name     = "Superviseur",
        phone         = "+237699000002",
        role          = UserRole.SUPERVISOR,
        kyc_status    = KycStatus.VERIFIED,
    )
    db.session.add(supervisor)

    # ── Agent guichet ─────────────────────────────────────────────────────────
    agent = User(
        email         = "agent@banque.cm",
        password_hash = bcrypt.generate_password_hash("Agent123!").decode("utf-8"),
        first_name    = "Marie",
        last_name     = "Agent",
        phone         = "+237699000003",
        role          = UserRole.AGENT,
        kyc_status    = KycStatus.VERIFIED,
    )
    db.session.add(agent)

    # ── Auditeur ──────────────────────────────────────────────────────────────
    auditor = User(
        email         = "auditeur@banque.cm",
        password_hash = bcrypt.generate_password_hash("Audit123!").decode("utf-8"),
        first_name    = "Jean",
        last_name     = "Auditeur",
        phone         = "+237699000004",
        role          = UserRole.AUDITOR,
        kyc_status    = KycStatus.VERIFIED,
    )
    db.session.add(auditor)

    db.session.flush()

    # ── Client 1 ──────────────────────────────────────────────────────────────
    client1 = User(
        email         = "alice@client.cm",
        password_hash = bcrypt.generate_password_hash("Client123!").decode("utf-8"),
        first_name    = "Alice",
        last_name     = "Ngono",
        phone         = "+237690123456",
        role          = UserRole.CLIENT,
        kyc_status    = KycStatus.VERIFIED,
    )
    db.session.add(client1)
    db.session.flush()

    account1 = Account(
        owner_id               = client1.id,
        account_number         = "CM1234567890",
        account_type           = AccountType.CURRENT,
        balance                = 500000.00,
        currency               = "XAF",
        daily_withdrawal_limit = 500000,
        daily_deposit_limit    = 5000000,
        transfer_limit         = 2000000,
    )
    prefs1 = NotificationPreference(user_id=client1.id)
    db.session.add(account1)
    db.session.add(prefs1)

    # ── Client 2 ──────────────────────────────────────────────────────────────
    client2 = User(
        email         = "bob@client.cm",
        password_hash = bcrypt.generate_password_hash("Client123!").decode("utf-8"),
        first_name    = "Bob",
        last_name     = "Mbarga",
        phone         = "+237690654321",
        role          = UserRole.CLIENT,
        kyc_status    = KycStatus.PENDING,
    )
    db.session.add(client2)
    db.session.flush()

    account2 = Account(
        owner_id               = client2.id,
        account_number         = "CM0987654321",
        account_type           = AccountType.SAVINGS,
        balance                = 1200000.00,
        currency               = "XAF",
        daily_withdrawal_limit = 300000,
        daily_deposit_limit    = 3000000,
        transfer_limit         = 1000000,
    )
    prefs2 = NotificationPreference(user_id=client2.id)
    db.session.add(account2)
    db.session.add(prefs2)

    db.session.commit()

    click.echo("✅  Données insérées avec succès !\n")
    click.echo("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    click.echo("  Comptes de démonstration :")
    click.echo("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    click.echo("  👑 Admin       : admin@banque.cm        / Admin123!")
    click.echo("  🔍 Superviseur : superviseur@banque.cm  / Super123!")
    click.echo("  🏦 Agent       : agent@banque.cm        / Agent123!")
    click.echo("  📋 Auditeur    : auditeur@banque.cm     / Audit123!")
    click.echo("  👤 Client 1    : alice@client.cm        / Client123!")
    click.echo("  👤 Client 2    : bob@client.cm          / Client123!")
    click.echo("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


# ─────────────────────────────────────────────────────────────────────────────
# Commande CLI : create-tables
# ─────────────────────────────────────────────────────────────────────────────
@app.cli.command("create-tables")
@with_appcontext
def create_tables():
    """Crée toutes les tables sans migrations."""
    db.create_all()
    click.echo("✅  Tables créées avec succès")


# ─────────────────────────────────────────────────────────────────────────────
# Démarrage
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(
        host  = "0.0.0.0",
        port  = 5000,
        debug = app.config.get("DEBUG", False),
    )
