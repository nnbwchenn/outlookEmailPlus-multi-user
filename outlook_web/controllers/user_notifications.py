"""多用户模式 — 成员通知设置（member 独立于管理员全局通知）"""

from __future__ import annotations

from typing import Any

from flask import jsonify, request

from outlook_web.audit import log_audit
from outlook_web.errors import build_error_payload
from outlook_web.repositories import users as users_repo
from outlook_web.security.auth import get_current_user, login_required


def _json_error(code: str, message: str, *, status: int = 400) -> Any:
    payload = build_error_payload(code, message, err_type="ValidationError", status=status)
    return jsonify({"success": False, "error": payload}), status


def _coerce_int(raw: Any, default: int) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


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


@login_required
def api_change_my_password() -> Any:
    """当前用户修改自己的登录密码（需验证旧密码）。"""
    user = get_current_user()
    if not user:
        return _json_error("AUTH_REQUIRED", "请先登录", status=401)

    data = request.get_json(silent=True) or {}
    old_password = str(data.get("old_password") or "")
    new_password = str(data.get("new_password") or "").strip()

    if not users_repo.verify_user_credentials(user["username"], old_password):
        return _json_error("OLD_PASSWORD_INVALID", "旧密码不正确", status=400)
    if len(new_password) < 8:
        return _json_error("PASSWORD_TOO_SHORT", "新密码长度至少为 8 位")

    if not users_repo.update_user(user["id"], password=new_password):
        return _json_error("PASSWORD_UPDATE_FAILED", "密码修改失败，请重试", status=500)

    log_audit("change_own_password", "user", user["id"], f"user={user['username']} 修改自身登录密码")
    return jsonify({"success": True, "message": "密码已更新，下次登录请使用新密码"})


@login_required
def api_get_my_polling() -> Any:
    """读取当前用户的自动轮询偏好（未设置时返回默认值）。"""
    user = get_current_user()
    if not user:
        return _json_error("AUTH_REQUIRED", "请先登录", status=401)

    config = users_repo.get_notification_setting(user["id"], "polling")
    interval = _coerce_int(config.get("interval"), 10)
    max_count = _coerce_int(config.get("max_count"), 5)
    return jsonify(
        {
            "success": True,
            "polling": {
                "enabled": bool(config.get("enabled")),
                "interval": interval,
                "max_count": max_count,
            },
        }
    )


@login_required
def api_update_my_polling() -> Any:
    """写入当前用户的自动轮询偏好（仅影响本人客户端轮询行为）。"""
    user = get_current_user()
    if not user:
        return _json_error("AUTH_REQUIRED", "请先登录", status=401)

    data = request.get_json(silent=True) or {}
    interval = _coerce_int(data.get("interval"), 0)
    if interval < 3 or interval > 300:
        return _json_error("POLLING_INTERVAL_INVALID", "轮询间隔必须是 3-300 秒之间的数字")
    if interval < 3 or interval > 300:
        return _json_error("POLLING_INTERVAL_INVALID", "轮询间隔必须在 3-300 秒之间")

    max_count = _coerce_int(data.get("max_count"), -1)
    if max_count < 0 or max_count > 100:
        return _json_error("POLLING_COUNT_INVALID", "轮询次数必须是 0-100 之间的数字（0 表示持续轮询）")

    users_repo.set_notification_setting(
        user["id"],
        "polling",
        {"enabled": bool(data.get("enabled")), "interval": interval, "max_count": max_count},
    )
    return jsonify({"success": True, "message": "轮询设置已保存"})


@login_required
def api_test_my_telegram() -> Any:
    """用当前用户已保存的 Telegram 配置发送测试消息（先保存，再测试）。"""
    user = get_current_user()
    if not user:
        return _json_error("AUTH_REQUIRED", "请先登录", status=401)

    from outlook_web.services.telegram_push import _send_telegram_message

    config = users_repo.get_notification_setting(user["id"], "telegram")
    bot_token = str(config.get("bot_token") or "").strip()
    chat_id = str(config.get("chat_id") or "").strip()
    if not bot_token or not chat_id:
        return _json_error("TELEGRAM_NOT_CONFIGURED", "请先配置并保存 Telegram Bot Token 和 Chat ID")

    ok = _send_telegram_message(bot_token, chat_id, "✅ Outlook Email Plus 测试消息：配置正确！")
    if ok:
        log_audit("member_telegram_test", "user", user["id"], f"user={user['username']} 测试消息发送成功")
        return jsonify({"success": True, "message": "测试消息已发送，请检查 Telegram"})
    return _json_error("TELEGRAM_TEST_SEND_FAILED", "发送失败，请检查 Bot Token 和 Chat ID 是否正确")


# ==================== 成员级对外 API Key ====================
# 成员可自建 API Key 查询自己名下邮箱；邮箱范围强制锁定为本人账号，
# pool_access 强制关闭，与管理员全局 Key（owner_user_id IS NULL）相互隔离。


def _get_my_external_key_or_none(user_id: int, key_id: Any) -> dict[str, Any] | None:
    from outlook_web.repositories import external_api_keys as external_api_keys_repo

    key = external_api_keys_repo.get_external_api_key_by_id(_coerce_int(key_id, 0))
    if not key or key.get("owner_user_id") != int(user_id):
        return None
    return key


@login_required
def api_list_my_external_keys() -> Any:
    """列出当前用户的对外 API Key（脱敏）+ 今日用量。"""
    user = get_current_user()
    if not user:
        return _json_error("AUTH_REQUIRED", "请先登录", status=401)

    from outlook_web.repositories import accounts as accounts_repo
    from outlook_web.repositories import external_api_keys as external_api_keys_repo

    keys = external_api_keys_repo.list_external_api_keys(include_disabled=True, owner_user_id=int(user["id"]))
    usage_summary = external_api_keys_repo.get_external_api_usage_summary([k.get("consumer_key") or "" for k in keys])
    for item in keys:
        item.update(
            usage_summary.get(
                item.get("consumer_key") or "",
                {"today_total_count": 0, "today_success_count": 0, "today_error_count": 0, "today_last_used_at": ""},
            )
        )
    owned = accounts_repo.load_accounts(owner_user_id=int(user["id"]))
    fresh_user = users_repo.get_user_by_id(int(user["id"])) or {}
    return jsonify(
        {
            "success": True,
            "keys": keys,
            "owned_account_count": len(owned),
            "external_api_enabled": bool(fresh_user.get("external_api_enabled")),
            "external_api_rate_limit": _coerce_int(fresh_user.get("external_api_rate_limit"), 60),
        }
    )


@login_required
def api_create_my_external_key() -> Any:
    """创建成员自己的对外 API Key（邮箱范围 = 本人名下全部启用账号）。"""
    user = get_current_user()
    if not user:
        return _json_error("AUTH_REQUIRED", "请先登录", status=401)

    import secrets

    from outlook_web.repositories import accounts as accounts_repo
    from outlook_web.repositories import external_api_keys as external_api_keys_repo

    fresh_user = users_repo.get_user_by_id(int(user["id"])) or {}
    if not fresh_user.get("external_api_enabled"):
        return _json_error("MEMBER_EXTERNAL_API_DISABLED", "对外 API 功能未开通，请联系管理员开通", status=403)

    data = request.get_json(silent=True) or {}
    name = str(data.get("name") or "").strip()
    if not name:
        return _json_error("NAME_REQUIRED", "请填写 Key 名称")
    if len(name) > 50:
        return _json_error("NAME_TOO_LONG", "Key 名称不能超过 50 个字符")

    owned = accounts_repo.load_accounts(owner_user_id=int(user["id"]))
    allowed_emails = sorted({str(a.get("email") or "").strip().lower() for a in owned if a.get("email")})
    if not allowed_emails:
        return _json_error("NO_ASSIGNED_ACCOUNTS", "你名下暂无邮箱，请联系管理员分配后再创建 API Key")

    plain_key = f"m_{secrets.token_urlsafe(24)}"
    key = external_api_keys_repo.create_external_api_key(
        name=name,
        api_key=plain_key,
        allowed_emails=allowed_emails,
        pool_access=False,
        enabled=True,
        owner_user_id=int(user["id"]),
    )
    log_audit("member_external_key_create", "user", user["id"], f"user={user['username']} name={name}")
    # 仅创建响应返回一次明文，之后只提供脱敏值 + 明文查询接口
    return jsonify({"success": True, "key": {**key, "api_key_plain": plain_key}, "message": "API Key 已创建，请立即保存明文"})


@login_required
def api_update_my_external_key(key_id: int) -> Any:
    """更新成员自己的对外 API Key（启停 / 重命名）。"""
    user = get_current_user()
    if not user:
        return _json_error("AUTH_REQUIRED", "请先登录", status=401)

    from outlook_web.repositories import external_api_keys as external_api_keys_repo

    key = _get_my_external_key_or_none(user["id"], key_id)
    if not key:
        return _json_error("KEY_NOT_FOUND", "API Key 不存在", status=404)

    data = request.get_json(silent=True) or {}
    name = str(data.get("name") or "").strip() if "name" in data else None
    if name is not None and not name:
        return _json_error("NAME_REQUIRED", "Key 名称不能为空")
    enabled = bool(data.get("enabled")) if "enabled" in data else None

    updated = external_api_keys_repo.update_external_api_key(
        int(key["id"]),
        name=name,
        enabled=enabled,
    )
    log_audit("member_external_key_update", "user", user["id"], f"user={user['username']} key_id={key['id']}")
    return jsonify({"success": True, "key": updated})


@login_required
def api_delete_my_external_key(key_id: int) -> Any:
    """删除成员自己的对外 API Key。"""
    user = get_current_user()
    if not user:
        return _json_error("AUTH_REQUIRED", "请先登录", status=401)

    from outlook_web.repositories import external_api_keys as external_api_keys_repo

    key = _get_my_external_key_or_none(user["id"], key_id)
    if not key:
        return _json_error("KEY_NOT_FOUND", "API Key 不存在", status=404)

    external_api_keys_repo.delete_external_api_key(int(key["id"]))
    log_audit("member_external_key_delete", "user", user["id"], f"user={user['username']} key_id={key['id']}")
    return jsonify({"success": True, "message": "API Key 已删除"})


@login_required
def api_get_my_external_key_plaintext(key_id: int) -> Any:
    """查看成员自己 API Key 的明文（审计留痕）。"""
    user = get_current_user()
    if not user:
        return _json_error("AUTH_REQUIRED", "请先登录", status=401)

    from outlook_web.repositories import external_api_keys as external_api_keys_repo

    key = _get_my_external_key_or_none(user["id"], key_id)
    if not key:
        return _json_error("KEY_NOT_FOUND", "API Key 不存在", status=404)

    plain = external_api_keys_repo.get_external_api_key_plaintext_by_id(int(key["id"]))
    log_audit("member_external_key_reveal", "user", user["id"], f"user={user['username']} key_id={key['id']}")
    return jsonify({"success": True, "api_key": plain})
