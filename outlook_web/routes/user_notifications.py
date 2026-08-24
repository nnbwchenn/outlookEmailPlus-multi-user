"""多用户模式 — 成员通知设置路由"""

from flask import Blueprint

from outlook_web.controllers import user_notifications as notifications_controller

bp = Blueprint("user_notifications", __name__, url_prefix="/api/me")


bp.add_url_rule("/notifications", view_func=notifications_controller.api_get_my_notifications, methods=["GET"])
bp.add_url_rule("/notifications", view_func=notifications_controller.api_update_my_notifications, methods=["PUT"])
bp.add_url_rule("/notifications/telegram-test", view_func=notifications_controller.api_test_my_telegram, methods=["POST"])
bp.add_url_rule("/accounts", view_func=notifications_controller.api_list_my_accounts, methods=["GET"])
bp.add_url_rule("/password", view_func=notifications_controller.api_change_my_password, methods=["PUT"])
bp.add_url_rule("/polling", view_func=notifications_controller.api_get_my_polling, methods=["GET"])
bp.add_url_rule("/polling", view_func=notifications_controller.api_update_my_polling, methods=["PUT"])
bp.add_url_rule("/external-keys", view_func=notifications_controller.api_list_my_external_keys, methods=["GET"])
bp.add_url_rule("/external-keys", view_func=notifications_controller.api_create_my_external_key, methods=["POST"])
bp.add_url_rule("/external-keys/<int:key_id>", view_func=notifications_controller.api_update_my_external_key, methods=["PUT"])
bp.add_url_rule(
    "/external-keys/<int:key_id>", view_func=notifications_controller.api_delete_my_external_key, methods=["DELETE"]
)
bp.add_url_rule(
    "/external-keys/<int:key_id>/plaintext",
    view_func=notifications_controller.api_get_my_external_key_plaintext,
    methods=["GET"],
)


def create_blueprint():
    return bp
