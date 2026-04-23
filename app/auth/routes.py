"""
Module Authentification — Routes Flask.
"""
from flask import Blueprint, request
from app.common.jwt_utils import jwt_required
from app.auth.service import AuthService
from app.common.utils import success_response, error_response, get_current_user

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/register", methods=["POST"])
def register():
    """
    Inscription d'un nouveau client
    ---
    tags:
      - Authentification
    summary: Créer un nouveau compte client
    description: Inscrit un nouveau client. Un compte courant XAF est créé automatiquement.
    consumes:
      - application/json
    produces:
      - application/json
    parameters:
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
          properties:
            email:
              type: string
              example: jean.dupont@email.cm
            password:
              type: string
              example: MonMotDePasse123!
            first_name:
              type: string
              example: Jean
            last_name:
              type: string
              example: Dupont
            phone:
              type: string
              example: "+237699123456"
            date_of_birth:
              type: string
              example: "1990-05-15"
    responses:
      201:
        description: Compte créé avec succès
      400:
        description: Email déjà utilisé
      422:
        description: Champs requis manquants
    """
    data = request.get_json(silent=True)
    if not data:
        return error_response("Corps JSON requis", 422)
    required = ["email", "password", "first_name", "last_name"]
    missing  = [f for f in required if not data.get(f)]
    if missing:
        return error_response(f"Champs requis manquants : {missing}", 422)
    if len(data["password"]) < 8:
        return error_response("Le mot de passe doit contenir au moins 8 caractères", 400)
    user, err = AuthService.register(data)
    if err:
        return error_response(err, 400)
    return success_response(user.to_dict(), "Compte créé avec succès", 201)


@auth_bp.route("/login", methods=["POST"])
def login():
    """
    Connexion utilisateur
    ---
    tags:
      - Authentification
    summary: Authentifier un utilisateur — retourne access_token et refresh_token
    description: Retourne un access_token (15 min) et un refresh_token (7 jours). Blocage après 5 tentatives échouées.
    consumes:
      - application/json
    produces:
      - application/json
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - email
            - password
          properties:
            email:
              type: string
              example: alice@client.cm
            password:
              type: string
              example: Client123!
    responses:
      200:
        description: Connexion réussie
      401:
        description: Identifiants invalides ou compte verrouillé
      422:
        description: Champs requis manquants
    """
    data = request.get_json(silent=True)
    if not data:
        return error_response("Corps JSON requis", 422)
    email    = data.get("email")
    password = data.get("password")
    if not email or not password:
        return error_response("Email et mot de passe requis", 422)
    access_token, refresh_token, user, err = AuthService.login(email, password)
    if err:
        return error_response(err, 401)
    return success_response({
        "access_token":  access_token,
        "refresh_token": refresh_token,
        "token_type":    "Bearer",
        "user":          user.to_dict(),
    }, "Connexion réussie")


@auth_bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    """
    Rafraîchir le token d'accès
    ---
    tags:
      - Authentification
    summary: Générer un nouveau access_token depuis le refresh_token
    description: Passer le refresh_token dans Authorization header.
    produces:
      - application/json
    parameters:
      - in: header
        name: Authorization
        type: string
        required: true
        description: "Bearer <refresh_token>"
    responses:
      200:
        description: Nouveau access_token généré
      401:
        description: Refresh token invalide ou expiré
    """
    access_token, err = AuthService.refresh()
    if err:
        return error_response(err, 401)
    return success_response({"access_token": access_token, "token_type": "Bearer"})


@auth_bp.route("/logout", methods=["POST"])
@jwt_required()
def logout():
    """
    Déconnexion
    ---
    tags:
      - Authentification
    summary: Révoquer le token JWT courant
    description: Invalide le token d'accès courant.
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
        description: Déconnexion réussie
      401:
        description: Token manquant ou invalide
    """
    AuthService.logout()
    return success_response(message="Déconnexion réussie")


@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    """
    Profil de l'utilisateur connecté
    ---
    tags:
      - Authentification
    summary: Récupérer les informations de l'utilisateur connecté
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
        description: Informations du profil
      401:
        description: Token manquant ou invalide
    """
    user = get_current_user()
    if not user:
        return error_response("Utilisateur introuvable", 404)
    return success_response(user.to_dict())


@auth_bp.route("/change-password", methods=["PATCH"])
@jwt_required()
def change_password():
    """
    Changer le mot de passe
    ---
    tags:
      - Authentification
    summary: Modifier le mot de passe de l'utilisateur connecté
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
            - old_password
            - new_password
          properties:
            old_password:
              type: string
              example: AncienMotDePasse123!
            new_password:
              type: string
              example: NouveauMotDePasse456!
    responses:
      200:
        description: Mot de passe modifié avec succès
      400:
        description: Ancien mot de passe incorrect
      401:
        description: Non authentifié
    """
    data = request.get_json(silent=True)
    if not data:
        return error_response("Corps JSON requis", 422)
    old_pwd = data.get("old_password")
    new_pwd = data.get("new_password")
    if not old_pwd or not new_pwd:
        return error_response("old_password et new_password requis", 422)
    user = get_current_user()
    ok, err = AuthService.change_password(user.id, old_pwd, new_pwd)
    if not ok:
        return error_response(err, 400)
    return success_response(message="Mot de passe modifié avec succès")
