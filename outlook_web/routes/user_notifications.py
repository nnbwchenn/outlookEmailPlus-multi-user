"""多用户模式 — 成员通知设置路由"""

from flask import Blueprint

from outlook_web.controllers import user_notifications as notifications_controller

bp = Blueprint("user_notifications", __name__, url_prefix="/api/me")


bp.add_url_rule("/notifications", view_func=notifications_controller.api_get_my_notifications, methods=["GET"])
bp.add_url_rule("/notifications", view_func=notifications_controller.api_update_my_notifications, methods=["PUT"])
bp.add_url_rule("/accounts", view_func=notifications_controller.api_list_my_accounts, methods=["GET"])


def create_blueprint():
    return bp