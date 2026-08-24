"""激活码路由：管理员管理 + 用户兑换"""

from flask import Blueprint

from outlook_web.controllers import activation_codes as activation_codes_controller

bp = Blueprint("activation_codes", __name__, url_prefix="/api")

bp.add_url_rule(
    "/admin/activation-codes/generate",
    view_func=activation_codes_controller.api_generate_codes,
    methods=["POST"],
)
bp.add_url_rule(
    "/admin/activation-codes/summary",
    view_func=activation_codes_controller.api_activation_summary,
    methods=["GET"],
)
bp.add_url_rule(
    "/admin/activation-codes",
    view_func=activation_codes_controller.api_list_codes,
    methods=["GET"],
)
bp.add_url_rule(
    "/admin/activation-codes/<int:code_id>/status",
    view_func=activation_codes_controller.api_update_code_status,
    methods=["POST"],
)
bp.add_url_rule(
    "/admin/activation-codes/<int:code_id>",
    view_func=activation_codes_controller.api_delete_code,
    methods=["DELETE"],
)
bp.add_url_rule(
    "/activation/my",
    view_func=activation_codes_controller.api_my_activations,
    methods=["GET"],
)
bp.add_url_rule(
    "/activation/redeem",
    view_func=activation_codes_controller.api_redeem_code,
    methods=["POST"],
)


def create_blueprint():
    return bp
