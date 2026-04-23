"""
Module Notifications — Routes Flask.
"""
from flask import Blueprint, request
from app.common.jwt_utils import jwt_required
from app import db
from app.models import Notification, NotificationPreference
from app.common.utils import success_response, error_response, get_current_user, paginate

notifications_bp = Blueprint("notifications", __name__)


@notifications_bp.route("", methods=["GET"])
@jwt_required()
def list_notifications():
    """
    Lister les notifications
    ---
    tags:
      - Notifications
    summary: Récupérer les notifications de l'utilisateur connecté
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
        name: unread_only
        type: boolean
        default: false
        description: Retourner uniquement les non lues
    responses:
      200:
        description: Liste paginée des notifications
      401:
        description: Non authentifié
    """
    user = get_current_user()
    query = Notification.query.filter_by(user_id=user.id)
    if request.args.get("unread_only", "false").lower() == "true":
        query = query.filter_by(is_read=False)
    query = query.order_by(Notification.created_at.desc())
    items, meta = paginate(query)
    return success_response([n.to_dict() for n in items], f"{meta['total_items']} notification(s)", meta=meta)


@notifications_bp.route("/unread-count", methods=["GET"])
@jwt_required()
def unread_count():
    """
    Nombre de notifications non lues
    ---
    tags:
      - Notifications
    summary: Obtenir le nombre de notifications non lues
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
        description: Compteur de notifications non lues
    """
    user  = get_current_user()
    count = Notification.query.filter_by(user_id=user.id, is_read=False).count()
    return success_response({"unread_count": count})


@notifications_bp.route("/read-all", methods=["PATCH"])
@jwt_required()
def mark_all_read():
    """
    Marquer toutes les notifications comme lues
    ---
    tags:
      - Notifications
    summary: Marquer toutes les notifications de l'utilisateur comme lues
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
        description: Toutes les notifications marquées comme lues
    """
    user  = get_current_user()
    count = Notification.query.filter_by(user_id=user.id, is_read=False).update({"is_read": True})
    db.session.commit()
    return success_response({"updated_count": count}, f"{count} notification(s) marquée(s) comme lue(s)")


@notifications_bp.route("/preferences", methods=["GET"])
@jwt_required()
def get_preferences():
    """
    Récupérer les préférences de notification
    ---
    tags:
      - Notifications
    summary: Obtenir les préférences de notification de l'utilisateur connecté
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
        description: Préférences de notification
    """
    user  = get_current_user()
    prefs = NotificationPreference.query.filter_by(user_id=user.id).first()
    if not prefs:
        prefs = NotificationPreference(user_id=user.id)
        db.session.add(prefs)
        db.session.commit()
    return success_response(prefs.to_dict())


@notifications_bp.route("/preferences", methods=["PATCH"])
@jwt_required()
def update_preferences():
    """
    Mettre à jour les préférences de notification
    ---
    tags:
      - Notifications
    summary: Modifier les préférences de notification (canaux, seuils, résumé)
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
          properties:
            sms_enabled:
              type: boolean
              example: true
            email_enabled:
              type: boolean
              example: true
            push_enabled:
              type: boolean
              example: false
            low_balance_threshold:
              type: number
              description: Alerte si solde inférieur à ce seuil
              example: 10000
            daily_summary:
              type: boolean
              description: Recevoir un résumé quotidien
              example: false
    responses:
      200:
        description: Préférences mises à jour
      422:
        description: Corps JSON requis
    """
    data  = request.get_json(silent=True)
    if not data:
        return error_response("Corps JSON requis", 422)
    user  = get_current_user()
    prefs = NotificationPreference.query.filter_by(user_id=user.id).first()
    if not prefs:
        prefs = NotificationPreference(user_id=user.id)
        db.session.add(prefs)
    if "sms_enabled"           in data: prefs.sms_enabled           = bool(data["sms_enabled"])
    if "email_enabled"         in data: prefs.email_enabled         = bool(data["email_enabled"])
    if "push_enabled"          in data: prefs.push_enabled          = bool(data["push_enabled"])
    if "daily_summary"         in data: prefs.daily_summary         = bool(data["daily_summary"])
    if "low_balance_threshold" in data:
        prefs.low_balance_threshold = float(data["low_balance_threshold"]) if data["low_balance_threshold"] else None
    db.session.commit()
    return success_response(prefs.to_dict(), "Préférences mises à jour")


@notifications_bp.route("/<notif_id>/read", methods=["PATCH"])
@jwt_required()
def mark_read(notif_id):
    """
    Marquer une notification comme lue
    ---
    tags:
      - Notifications
    summary: Marquer une notification spécifique comme lue
    produces:
      - application/json
    parameters:
      - in: header
        name: Authorization
        type: string
        required: true
        description: "Bearer <access_token>"
      - in: path
        name: notif_id
        type: string
        required: true
    responses:
      200:
        description: Notification marquée comme lue
      403:
        description: Accès refusé
      404:
        description: Notification introuvable
    """
    user  = get_current_user()
    notif = db.session.get(Notification, notif_id)
    if not notif:
        return error_response("Notification introuvable", 404)
    if notif.user_id != user.id:
        return error_response("Accès refusé", 403)
    notif.is_read = True
    db.session.commit()
    return success_response(notif.to_dict(), "Notification marquée comme lue")


@notifications_bp.route("/<notif_id>", methods=["DELETE"])
@jwt_required()
def delete_notification(notif_id):
    """
    Supprimer une notification
    ---
    tags:
      - Notifications
    summary: Supprimer une notification de l'utilisateur
    produces:
      - application/json
    parameters:
      - in: header
        name: Authorization
        type: string
        required: true
        description: "Bearer <access_token>"
      - in: path
        name: notif_id
        type: string
        required: true
    responses:
      200:
        description: Notification supprimée
      403:
        description: Accès refusé
      404:
        description: Notification introuvable
    """
    user  = get_current_user()
    notif = db.session.get(Notification, notif_id)
    if not notif:
        return error_response("Notification introuvable", 404)
    if notif.user_id != user.id:
        return error_response("Accès refusé", 403)
    db.session.delete(notif)
    db.session.commit()
    return success_response(message="Notification supprimée")
