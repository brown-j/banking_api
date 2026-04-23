# 🏦 Système de Transaction Bancaire — API REST

API REST complète construite avec **Flask**, **SQLAlchemy**, **JWT** et **Swagger (Flasgger)**.

---

## 📁 Structure du projet

```
banking_api/
├── run.py                          # Point d'entrée & commandes CLI
├── config.py                       # Configuration (dev / prod / test)
├── requirements.txt                # Dépendances Python
├── Dockerfile                      # Image Docker
├── docker-compose.yml              # Stack complète (API + DB + Redis)
├── .env.example                    # Variables d'environnement (à copier en .env)
│
└── app/
    ├── __init__.py                 # Factory Flask + init extensions + blueprints
    ├── models.py                   # Tous les modèles SQLAlchemy
    │
    ├── common/
    │   ├── __init__.py
    │   └── utils.py                # Helpers : réponses, décorateurs rôles, pagination, audit
    │
    ├── auth/
    │   ├── __init__.py
    │   ├── service.py              # Logique métier : register, login, refresh, logout
    │   └── routes.py               # Endpoints : /api/v1/auth/*
    │
    ├── accounts/
    │   ├── __init__.py
    │   ├── service.py              # Logique métier : CRUD comptes, solde, plafonds
    │   └── routes.py               # Endpoints : /api/v1/accounts/*
    │
    ├── transactions/
    │   ├── __init__.py
    │   ├── service.py              # Logique métier : dépôt, retrait, virement, validation
    │   └── routes.py               # Endpoints : /api/v1/transactions/*
    │
    ├── notifications/
    │   ├── __init__.py
    │   └── routes.py               # Endpoints : /api/v1/notifications/*
    │
    ├── admin/
    │   ├── __init__.py
    │   └── routes.py               # Endpoints : /api/v1/admin/*
    │
    └── audit/
        ├── __init__.py
        └── routes.py               # Endpoints : /api/v1/audit/*
```

---

## ⚙️ Installation

### 1. Cloner et configurer l'environnement

```bash
git clone <repo>
cd banking_api

# Créer l'environnement virtuel
python -m venv venv
source venv/bin/activate        # Linux/Mac
venv\Scripts\activate           # Windows

# Installer les dépendances
pip install -r requirements.txt

# Copier le fichier d'environnement
cp .env.example .env
# → Éditer .env avec vos valeurs (DATABASE_URL, JWT_SECRET_KEY, etc.)
```

### 2. Initialiser la base de données

```bash
# Avec SQLite (développement rapide)
export DATABASE_URL=sqlite:///banking_dev.db

# Créer les tables
flask create-tables

# OU avec les migrations Flask-Migrate
flask db init
flask db migrate -m "initial migration"
flask db upgrade

# Insérer les données de démonstration
flask seed
```

### 3. Démarrer le serveur

```bash
python run.py
# ou
flask run --host=0.0.0.0 --port=5000 --debug
```

---

## 🐳 Démarrage avec Docker

```bash
# Construire et démarrer toute la stack
docker-compose up --build

# En arrière-plan
docker-compose up -d --build

# Voir les logs de l'API
docker-compose logs -f api

# Arrêter
docker-compose down
```

Services disponibles :
| Service   | URL                            |
|-----------|-------------------------------|
| API       | http://localhost:5000          |
| Swagger   | http://localhost:5000/api/docs |
| Adminer   | http://localhost:8080          |
| PostgreSQL| localhost:5432                 |

---

## 📖 Documentation Swagger

Accessible à **http://localhost:5000/api/docs/**

La documentation interactive permet de :
- Visualiser tous les endpoints groupés par module
- Tester les requêtes directement depuis le navigateur
- Voir les schémas de requête et de réponse

Pour s'authentifier dans Swagger :
1. Appeler `POST /api/v1/auth/login`
2. Copier le `access_token` retourné
3. Cliquer sur **Authorize** (cadenas) en haut de la page
4. Saisir : `Bearer <votre_token>`

---

## 🔐 Authentification JWT

Toutes les routes protégées nécessitent un header :
```
Authorization: Bearer <access_token>
```

| Token         | Durée       | Utilisation                    |
|---------------|-------------|-------------------------------|
| access_token  | 15 minutes  | Appels API normaux             |
| refresh_token | 7 jours     | Renouveler l'access_token      |

---

## 👥 Rôles et permissions

| Rôle        | Description                                               |
|-------------|-----------------------------------------------------------|
| `client`    | Consulter/gérer ses propres comptes et transactions       |
| `agent`     | Opérations de caisse pour les clients                     |
| `admin`     | Accès complet : utilisateurs, comptes, paramètres         |
| `supervisor`| Valider les transactions à montant élevé, alertes fraude  |
| `auditor`   | Lecture seule : journaux d'audit, rapports                |
| `it`        | Surveillance technique, accès infrastructure              |

---

## 📡 Endpoints API

### 🔑 Authentification `/api/v1/auth`
| Méthode | Endpoint              | Description                        | Auth |
|---------|-----------------------|------------------------------------|------|
| POST    | /register             | Inscription d'un nouveau client    | Non  |
| POST    | /login                | Connexion (retourne JWT)           | Non  |
| POST    | /refresh              | Renouveler l'access token          | Oui  |
| POST    | /logout               | Déconnexion (révocation token)     | Oui  |
| GET     | /me                   | Profil de l'utilisateur connecté   | Oui  |
| PATCH   | /change-password      | Modifier le mot de passe           | Oui  |

### 🏦 Comptes `/api/v1/accounts`
| Méthode | Endpoint                       | Description                         | Rôle requis     |
|---------|--------------------------------|-------------------------------------|-----------------|
| GET     | /                              | Lister ses comptes                  | Tous            |
| POST    | /                              | Créer un compte                     | admin, agent    |
| GET     | /{id}                          | Détail d'un compte                  | Tous            |
| GET     | /{id}/balance                  | Solde en temps réel                 | Tous            |
| PATCH   | /{id}/status                   | Changer le statut                   | admin, supervisor |
| PATCH   | /{id}/limits                   | Modifier les plafonds               | admin           |
| DELETE  | /{id}                          | Fermer un compte                    | admin           |
| GET     | /{id}/transactions             | Historique paginé                   | Tous            |

### 💸 Transactions `/api/v1/transactions`
| Méthode | Endpoint              | Description                               | Rôle requis         |
|---------|-----------------------|-------------------------------------------|---------------------|
| GET     | /                     | Historique de toutes les transactions     | Tous                |
| POST    | /deposit              | Effectuer un dépôt                        | Tous                |
| POST    | /withdrawal           | Effectuer un retrait                      | Tous                |
| POST    | /transfer             | Effectuer un virement                     | Tous                |
| GET     | /pending              | Transactions en attente de validation     | admin, supervisor   |
| GET     | /{id}                 | Détail d'une transaction                  | Tous                |
| POST    | /{id}/validate        | Valider un montant élevé                  | admin, supervisor   |
| POST    | /{id}/cancel          | Annuler une transaction                   | Tous                |

### 🔔 Notifications `/api/v1/notifications`
| Méthode | Endpoint              | Description                               |
|---------|-----------------------|-------------------------------------------|
| GET     | /                     | Lister les notifications                  |
| GET     | /unread-count         | Nombre de non-lues                        |
| GET     | /preferences          | Préférences de notification               |
| PATCH   | /preferences          | Mettre à jour les préférences             |
| PATCH   | /{id}/read            | Marquer une notification comme lue        |
| PATCH   | /read-all             | Tout marquer comme lu                     |
| DELETE  | /{id}                 | Supprimer une notification                |

### ⚙️ Administration `/api/v1/admin`
| Méthode | Endpoint              | Description                               | Rôle requis         |
|---------|-----------------------|-------------------------------------------|---------------------|
| GET     | /dashboard            | Tableau de bord en temps réel             | admin, supervisor   |
| GET     | /users                | Lister tous les utilisateurs              | admin, it           |
| POST    | /users                | Créer un utilisateur interne              | admin               |
| GET     | /users/{id}           | Détail d'un utilisateur                   | admin, it, auditor  |
| PATCH   | /users/{id}           | Modifier un utilisateur                   | admin               |
| DELETE  | /users/{id}           | Désactiver un utilisateur                 | admin               |
| GET     | /reports              | Rapport de transactions                   | admin, auditor      |

### 📋 Audit `/api/v1/audit`
| Méthode | Endpoint              | Description                               | Rôle requis         |
|---------|-----------------------|-------------------------------------------|---------------------|
| GET     | /logs                 | Journal d'audit paginé et filtrable       | admin, auditor, it  |
| GET     | /logs/{id}            | Détail d'une entrée d'audit               | admin, auditor, it  |
| GET     | /logs/user/{user_id}  | Audit d'un utilisateur spécifique         | admin, auditor      |
| GET     | /stats                | Statistiques du journal d'audit           | admin, auditor      |

---

## 🧪 Données de démonstration (`flask seed`)

| Rôle        | Email                        | Mot de passe  |
|-------------|------------------------------|---------------|
| Admin       | admin@banque.cm              | Admin123!     |
| Superviseur | superviseur@banque.cm        | Super123!     |
| Agent       | agent@banque.cm              | Agent123!     |
| Auditeur    | auditeur@banque.cm           | Audit123!     |
| Client 1    | alice@client.cm              | Client123!    |
| Client 2    | bob@client.cm                | Client123!    |

---

## 🔒 Sécurité

- **Mots de passe** : hashés avec Bcrypt (12 rounds)
- **JWT** : access token (15 min) + refresh token (7 jours)
- **Blacklist** : tokens révoqués à la déconnexion
- **Brute force** : blocage après 5 tentatives (30 min)
- **Transactions élevées** : validation superviseur si > seuil configuré
- **Audit trail** : chaque action est journalisée avec IP, user-agent

---

## 🌐 Format de réponse standard

```json
{
  "status": "success | error",
  "code": 200,
  "message": "Description de la réponse",
  "data": { ... },
  "meta": {
    "page": 1,
    "per_page": 20,
    "total_items": 150,
    "total_pages": 8
  },
  "timestamp": "2025-01-15T10:30:00Z"
}
```

---

## 📦 Technologies

| Technologie        | Version  | Rôle                              |
|--------------------|----------|-----------------------------------|
| Flask              | 3.1.x    | Framework web                     |
| Flask-SQLAlchemy   | 3.1.x    | ORM base de données               |
| Flask-Migrate      | 4.x      | Migrations de schéma              |
| Flask-JWT-Extended | 4.6.x    | Authentification JWT              |
| Flask-Bcrypt       | 1.0.x    | Hashage des mots de passe         |
| Flasgger           | 0.9.x    | Documentation Swagger / OpenAPI   |
| PostgreSQL         | 16       | Base de données principale        |
| Redis              | 7        | Cache + blacklist JWT             |
| Docker             | latest   | Conteneurisation                  |
