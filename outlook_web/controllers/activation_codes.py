"""激活码控制器：管理员生成/管理 + 用户兑换（分层约束：禁止导入 routes/services）"""

from __future__ import annotations

import time
from typing import Any

from flask import jsonify, request

from outlook_web.audit import log_audit
from outlook_web.controllers.accounts import build_error_response
from outlook_web.repositories import activation_codes as codes_repo
from outlook_web.security.auth import admin_required, get_current_user, login_required

# 兑换失败限速：每会话每分钟最多 10 次（防暴力猜码）
_redeem_attempts: dict[str, list[float]] = {}
_REDEEM_WINDOW = 60.0
_REDEEM_MAX_ATTEMPTS = 10


def _redeem_throttle_key() -> str:
    user = get_current_user()
    return f"user:{user['id'] if user else 'anon'}"


def _redeem_throttled() -> bool:
    key = _redeem_throttle_key()
    now = time.monotonic()
    attempts = [t for t in _redeem_attempts.get(key, []) if now - t < _REDEEM_WINDOW]
    _redeem_attempts[key] = attempts
    return len(attempts) >= _REDEEM_MAX_ATTEMPTS


def _record_redeem_attempt() -> None:
    _redeem_attempts.setdefault(_redeem_throttle_key(), []).append(time.monotonic())


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@login_required
@admin_required
def api_generate_codes() -> Any:
    """POST /api/admin/activation-codes/generate {count, max_bindings, note?}"""
    data = request.get_json(silent=True) or {}
    count = _safe_int(data.get("count"))
    max_bindings = _safe_int(data.get("max_bindings"))
    if count is None or max_bindings is None:
        return build_error_response("INVALID_PARAM", "数量参数无效", status=400)

    if not (1 <= count <= 200):
        return build_error_response("INVALID_PARAM", "生成数量需在 1-200 之间", status=400)
    if not (1 <= max_bindings <= 100):
        return build_error_response("INVALID_PARAM", "绑定邮箱数量需在 1-100 之间", status=400)

    # 防超开：未兑换激活码占用额度 + 本次签发 ≤ 当前未分配邮箱数（一一对应）
    summary = codes_repo.get_activation_summary()
    remaining = summary["remaining_capacity"]
    requested = count * max_bindings
    if requested > remaining:
        max_codes = remaining // max_bindings if max_bindings else 0
        return build_error_response(
            "ACTIVATION_CAPACITY_EXCEEDED",
            f"超出可绑定额度：当前未分配邮箱 {summary['available_mailboxes']} 个，"
            f"未兑换激活码已占额度 {summary['outstanding_quota']}，仅剩 {remaining} 个名额"
            f"（每码绑 {max_bindings} 时最多还能生成 {max_codes} 个）",
            status=400,
        )

    user = get_current_user()
    if not user:
        return build_error_response("UNAUTHORIZED", "请先登录", status=401)
    codes = codes_repo.create_codes(
        count=count, max_bindings=max_bindings, created_by=user["id"], note=str(data.get("note") or "")[:100]
    )
    log_audit("create", "activation_code", f"batch:{count}", f"生成 {count} 个激活码（每个可绑 {max_bindings} 个邮箱）")
    return jsonify({"success": True, "codes": codes, "max_bindings": max_bindings})


@login_required
@admin_required
def api_activation_summary() -> Any:
    """GET /api/admin/activation-codes/summary — 额度台账"""
    return jsonify({"success": True, **codes_repo.get_activation_summary()})


@login_required
@admin_required
def api_list_codes() -> Any:
    """GET /api/admin/activation-codes"""
    return jsonify({"success": True, "codes": codes_repo.list_codes()})


@login_required
@admin_required
def api_update_code_status(code_id: int) -> Any:
    """POST /api/admin/activation-codes/<id>/status {status: active|disabled}"""
    code_id_int = _safe_int(code_id)
    if code_id_int is None:
        return build_error_response("INVALID_PARAM", "参数无效", status=400)
    data = request.get_json(silent=True) or {}
    status = str(data.get("status") or "").strip().lower()
    if not codes_repo.set_status(code_id_int, status):
        return build_error_response("INVALID_PARAM", "状态值无效", status=400)
    log_audit("update", "activation_code", str(code_id_int), f"状态变更为 {status}")
    return jsonify({"success": True})


@login_required
@admin_required
def api_delete_code(code_id: int) -> Any:
    """DELETE /api/admin/activation-codes/<id>"""
    code_id_int = _safe_int(code_id)
    if code_id_int is None or not codes_repo.delete_code(code_id_int):
        return build_error_response("ACTIVATION_CODE_NOT_FOUND", "激活码不存在", status=404)
    log_audit("delete", "activation_code", str(code_id_int), "删除激活码")
    return jsonify({"success": True})


@login_required
def api_my_activations() -> Any:
    """GET /api/activation/my — 当前用户经激活码绑定的邮箱"""
    user = get_current_user()
    if not user:
        return build_error_response("UNAUTHORIZED", "请先登录", status=401)
    return jsonify({"success": True, "bindings": codes_repo.list_bindings_for_user(user["id"])})


@login_required
def api_redeem_code() -> Any:
    """POST /api/activation/redeem {code} — 用户端激活入口"""
    if _redeem_throttled():
        return build_error_response("TOO_MANY_ATTEMPTS", "尝试过于频繁，请稍后再试", status=429)
    _record_redeem_attempt()

    data = request.get_json(silent=True) or {}
    code_text = str(data.get("code") or "").strip().upper()
    if not code_text:
        return build_error_response("ACTIVATION_CODE_REQUIRED", "请输入激活码", status=400)

    code_row = codes_repo.get_code_by_text(code_text)
    if not code_row:
        return build_error_response("ACTIVATION_CODE_INVALID", "激活码不存在，请核对后重试", status=404)
    if code_row.get("status") != "active":
        return build_error_response("ACTIVATION_CODE_DISABLED", "该激活码已被停用", status=400)

    user = get_current_user()
    if not user:
        return build_error_response("UNAUTHORIZED", "请先登录", status=401)
    result = codes_repo.redeem_code(code_row, user["id"])
    if not result.get("success"):
        log_audit("activate", "activation_code", code_text[:24], f"失败：{result.get('message')}")
        return build_error_response(
            result.get("error", "REDEEM_FAILED"),
            result.get("message", "激活失败"),
            status=400,
        )

    bound = result.get("bound") or []
    log_audit(
        "activate",
        "activation_code",
        code_text[:24],
        f"用户 {user['username']} 激活成功，绑定 {len(bound)} 个邮箱",
    )
    return jsonify(
        {
            "success": True,
            "bound_count": len(bound),
            "bound": bound,
            "message": f"激活成功，已绑定 {len(bound)} 个邮箱",
        }
    )
