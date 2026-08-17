"""多用户模式 — 成员通知设置（member 独立于管理员全局通知）"""

from __future__ import annotations

from typing import Any

from flask import jsonify, request

from outlook_web.errors import build_error_payload
from outlook_web.repositories import users as users_repo
from outlook_web.security.auth import get_current_user, login_required


def _json_error(code: str, message: str, *, status: int = 400) -> Any:
    payload = build_error_payload(code, message, err_type="ValidationError", status=status)
    return jsonify({"success": False, "error": payload}), status


@login_required
def api_get_my_notifications() -> Any:
    """读取当前用户的成员级通知配置（Telegram / Webhook）。"""
    user = get_current_user()
    if not user:
        return _json_error("AUTH_REQUIRED", "请先登录", status=401)

    telegram = users_repo.get_notification_setting(user["id"], "telegram")
    webhook = users_repo.get_notification_setting(user["id"], "webhook")

    # 账号级 telegram 参与开关（自己名下启用的账号数）
    from outlook_web.repositories import accounts as accounts_repo

    owned = accounts_repo.load_accounts(owner_user_id=user["id"])
    enabled_count = sum(1 for a in owned if a.get("telegram_push_enabled"))

    return jsonify(
        {
            "success": True,
            "notifications": {
                "telegram": telegram or {},
                "webhook": webhook or {},
                "owned_account_count": len(owned),
                "telegram_enabled_account_count": enabled_count,
            },
        }
    )


@login_required
def api_update_my_notifications() -> Any:
    """写入当前用户的成员级通知配置。

    body: { "channel": "webhook|telegram", "enabled": bool, "config": {...} }
    """
    user = get_current_user()
    if not user:
        return _json_error("AUTH_REQUIRED", "请先登录", status=401)

    data = request.get_json(silent=True) or {}
    channel = (data.get("channel") or "").strip().lower()
    if channel not in ("telegram", "webhook"):
        return _json_error("CHANNEL_INVALID", "channel 只能是 telegram 或 webhook")

    config = data.get("config") or {}
    if not isinstance(config, dict):
        return _json_error("CONFIG_INVALID", "config 必须是对象")

    if channel == "webhook":
        url = str(config.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            return _json_error("WEBHOOK_URL_INVALID", "Webhook URL 格式无效")
        config["url"] = url

    users_repo.set_notification_setting(user["id"], channel, config)
    return jsonify({"success": True, "message": "通知配置已保存"})


@login_required
def api_list_my_accounts() -> Any:
    """当前用户可见账号（member 只列自己名下，admin 列出全部）。"""
    user = get_current_user()
    if not user:
        return _json_error("AUTH_REQUIRED", "请先登录", status=401)

    from outlook_web.repositories import accounts as accounts_repo

    owner_scope = None if user.get("role") == "admin" else user["id"]
    accounts = accounts_repo.load_accounts(owner_user_id=owner_scope)
    result = [
        {
            "id": a["id"],
            "email": a["email"],
            "group_id": a.get("group_id"),
            "status": a.get("status", "active"),
            "telegram_push_enabled": bool(a.get("telegram_push_enabled")),
        }
        for a in accounts
    ]
    return jsonify({"success": True, "accounts": result})
