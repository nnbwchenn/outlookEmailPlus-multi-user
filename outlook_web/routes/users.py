"""多用户模式 — 用户管理路由"""

from flask import Blueprint

from outlook_web.controllers import users as users_controller

bp = Blueprint("users", __name__, url_prefix="/api")


bp.add_url_rule("/me", view_func=users_controller.api_get_me, methods=["GET"])
bp.add_url_rule("/users", view_func=users_controller.api_list_users, methods=["GET"])
bp.add_url_rule("/users", view_func=users_controller.api_create_user, methods=["POST"])
bp.add_url_rule("/users/<int:user_id>", view_func=users_controller.api_update_user, methods=["PUT"])
bp.add_url_rule("/users/<int:user_id>", view_func=users_controller.api_delete_user, methods=["DELETE"])
bp.add_url_rule("/users/<int:user_id>/accounts", view_func=users_controller.api_list_user_accounts, methods=["GET"])
bp.add_url_rule("/users/assign", view_func=users_controller.api_assign_accounts, methods=["POST"])
bp.add_url_rule("/users/unassign", view_func=users_controller.api_unassign_accounts, methods=["POST"])
bp.add_url_rule("/users/unassigned-accounts", view_func=users_controller.api_list_unassigned_accounts, methods=["GET"])


def create_blueprint():
    return bp