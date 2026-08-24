"""多用户模式 — 用户管理控制器（admin 专属）"""

from __future__ import annotations

import json
from typing import Any

from flask import jsonify, request

from outlook_web.audit import log_audit
from outlook_web.errors import build_error_payload
from outlook_web.repositories import accounts as accounts_repo
from outlook_web.repositories import users as users_repo
from outlook_web.security.auth import admin_required, get_current_user, login_required


def _json_error(code: str, message: str, *, status: int = 400) -> Any:
    payload = build_error_payload(code, message, err_type="ValidationError", status=status)
    return jsonify({"success": False, "error": payload}), status


@login_required
def api_get_me() -> Any:
    """返回当前登录用户信息（前端角色化渲染用）。"""
    user = get_current_user()
    if not user:
        return _json_error("AUTH_REQUIRED", "请先登录", status=401)
    return jsonify(
        {
            "success": True,
            "user": {
                "id": user["id"],
                "username": user["username"],
                "role": user["role"],
                "display_name": user["display_name"],
            },
        }
    )


@login_required
@admin_required
def api_list_users() -> Any:
    """列出所有用户（含名下账号数）。"""
    users = users_repo.list_users()
    result = []
    for u in users:
        result.append(
            {
                "id": u["id"],
                "username": u["username"],
                "role": u["role"],
                "display_name": u["display_name"],
                "status": u["status"],
                "created_at": u["created_at"],
                "external_api_enabled": bool(u.get("external_api_enabled")),
                "external_api_rate_limit": u.get("external_api_rate_limit"),
                "account_count": users_repo.count_owned_accounts(u["id"]),
            }
        )
    return jsonify({"success": True, "users": result})


@login_required
@admin_required
def api_create_user() -> Any:
    """创建用户（member 或 admin）。"""
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = str(data.get("password") or "")
    role = (data.get("role") or "member").strip().lower()
    display_name = (data.get("display_name") or "").strip()

    if not username or len(username) < 2:
        return _json_error("USERNAME_INVALID", "用户名至少 2 个字符")
    if len(password) < 8:
        return _json_error("PASSWORD_TOO_SHORT", "密码长度至少为 8 位")
    if role not in ("admin", "member"):
        return _json_error("ROLE_INVALID", "角色只能是 admin 或 member")

    if users_repo.get_user_by_username(username):
        return _json_error("USERNAME_EXISTS", "用户名已存在")

    user = users_repo.create_user(username, password, role=role, display_name=display_name)
    if not user:
        return _json_error("USER_CREATE_FAILED", "创建用户失败", status=500)

    log_audit("create", "user", str(user["id"]), f"创建用户 {username}（{role}）")
    return jsonify({"success": True, "message": "用户创建成功", "user": user})


@login_required
@admin_required
def api_update_user(user_id: int) -> Any:
    """更新用户：重置密码 / 改角色 / 启用禁用 / 改昵称。"""
    data = request.get_json(silent=True) or {}
    target = users_repo.get_user_by_id(user_id)
    if not target:
        return _json_error("USER_NOT_FOUND", "用户不存在", status=404)

    current = get_current_user() or {}
    if int(user_id) == int(current.get("id") or 0):
        return _json_error("CANNOT_MODIFY_SELF", "不能修改自己的账号（请用系统设置修改密码）")

    updated_fields: list[str] = []

    if "password" in data and str(data.get("password") or "").strip():
        new_pw = str(data["password"]).strip()
        if len(new_pw) < 8:
            return _json_error("PASSWORD_TOO_SHORT", "密码长度至少为 8 位")
        users_repo.update_user(user_id, password=new_pw)
        updated_fields.append("password")

    if "role" in data:
        new_role = str(data["role"]).strip().lower()
        if new_role not in ("admin", "member"):
            return _json_error("ROLE_INVALID", "角色只能是 admin 或 member")
        users_repo.update_user(user_id, role=new_role)
        updated_fields.append("role")

    if "status" in data:
        new_status = str(data["status"]).strip().lower()
        if new_status not in ("active", "disabled"):
            return _json_error("STATUS_INVALID", "状态只能是 active 或 disabled")
        users_repo.update_user(user_id, status=new_status)
        updated_fields.append("status")

    if "display_name" in data:
        users_repo.update_user(user_id, display_name=str(data["display_name"] or "").strip())
        updated_fields.append("display_name")

    # 对外 API 权限（开关 + 每分钟限流，均由管理员设置）
    if "external_api_enabled" in data:
        enabled = bool(data.get("external_api_enabled"))
        users_repo.update_user(user_id, external_api_enabled=enabled)
        updated_fields.append("external_api_enabled=" + ("on" if enabled else "off"))

    if "external_api_rate_limit" in data:
        raw_limit = data.get("external_api_rate_limit")
        if raw_limit in (None, ""):
            # 置空恢复默认（NULL = 60/分钟）
            from outlook_web.db import get_db

            db = get_db()
            db.execute(
                "UPDATE users SET external_api_rate_limit = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (user_id,),
            )
            db.commit()
            updated_fields.append("external_api_rate_limit=default")
        else:
            try:
                limit = int(raw_limit)
            except (TypeError, ValueError):
                return _json_error("RATE_LIMIT_INVALID", "限流阈值必须是数字")
            if limit < 1 or limit > 10000:
                return _json_error("RATE_LIMIT_INVALID", "限流阈值必须在 1-10000 之间")
            users_repo.update_user(user_id, external_api_rate_limit=limit)
            updated_fields.append(f"external_api_rate_limit={limit}")

    log_audit("update", "user", str(user_id), f"更新用户字段：{','.join(updated_fields)}")
    return jsonify({"success": True, "message": "用户已更新", "updated": updated_fields})


@login_required
@admin_required
def api_delete_user(user_id: int) -> Any:
    """删除用户（名下账号自动归还管理员）。"""
    target = users_repo.get_user_by_id(user_id)
    if not target:
        return _json_error("USER_NOT_FOUND", "用户不存在", status=404)

    current = get_current_user() or {}
    if int(user_id) == int(current.get("id") or 0):
        return _json_error("CANNOT_DELETE_SELF", "不能删除当前登录的管理员账号")

    if target.get("role") == "admin":
        admin_count = len([u for u in users_repo.list_users() if u.get("role") == "admin"])
        if admin_count <= 1:
            return _json_error("LAST_ADMIN", "至少保留一个管理员账号")

    users_repo.delete_user(user_id)
    log_audit("delete", "user", str(user_id), f"删除用户 {target.get('username')}")
    return jsonify({"success": True, "message": "用户已删除，名下邮箱已归还管理员"})


@login_required
@admin_required
def api_list_user_accounts(user_id: int) -> Any:
    """列出某用户名下已分配的账号。"""
    target = users_repo.get_user_by_id(user_id)
    if not target:
        return _json_error("USER_NOT_FOUND", "用户不存在", status=404)
    accounts = accounts_repo.load_accounts(owner_user_id=user_id)
    result = [
        {
            "id": a["id"],
            "email": a["email"],
            "group_id": a.get("group_id"),
            "status": a.get("status", "active"),
        }
        for a in accounts
    ]
    return jsonify({"success": True, "accounts": result})


@login_required
@admin_required
def api_assign_accounts() -> Any:
    """分配/回收邮箱：body = { owner_user_id, account_ids }（account_ids 为空 = 全部回收）。"""
    data = request.get_json(silent=True) or {}
    owner_user_id = data.get("owner_user_id")
    account_ids = data.get("account_ids", [])

    if owner_user_id is None:
        return _json_error("OWNER_REQUIRED", "请指定目标用户")
    try:
        owner_user_id = int(owner_user_id)
    except (TypeError, ValueError):
        return _json_error("OWNER_INVALID", "目标用户无效")

    target = users_repo.get_user_by_id(owner_user_id)
    if not target:
        return _json_error("USER_NOT_FOUND", "目标用户不存在", status=404)

    if not isinstance(account_ids, list):
        return _json_error("ACCOUNT_IDS_INVALID", "account_ids 必须是数组")

    try:
        parsed_ids = [int(aid) for aid in account_ids]
    except (TypeError, ValueError):
        return _json_error("ACCOUNT_IDS_INVALID", "account_ids 必须是整数数组")

    # 校验账号存在；标记从其他用户转移的邮箱（用于前端醒目区分）
    assigned = 0
    missing = []
    transferred = []
    for aid in parsed_ids:
        account = accounts_repo.get_account_by_id(aid)
        if not account:
            missing.append(aid)
            continue
        prev_owner = account.get("owner_user_id")
        if accounts_repo.assign_account_owner(aid, owner_user_id):
            assigned += 1
            if prev_owner is not None and int(prev_owner) != int(owner_user_id):
                transferred.append(
                    {"id": aid, "email": account.get("email") or ""}
                )

    transferred_note = (
        f"，其中 {len(transferred)} 个从其他用户转移" if transferred else ""
    )
    log_audit(
        "assign",
        "user",
        str(owner_user_id),
        f"分配邮箱给 {target.get('username')}：成功={assigned}，缺失={len(missing)}"
        + (
            "，转移=" + ",".join(t["email"] for t in transferred)
            if transferred
            else ""
        ),
    )
    return jsonify(
        {
            "success": True,
            "message": f"已分配 {assigned} 个邮箱给 {target.get('username')}{transferred_note}",
            "assigned": assigned,
            "missing_ids": missing,
            "transferred": transferred,
        }
    )


@login_required
@admin_required
def api_unassign_accounts() -> Any:
    """回收邮箱：body = { account_ids }（归还管理员全局）。"""
    data = request.get_json(silent=True) or {}
    account_ids = data.get("account_ids", [])
    if not isinstance(account_ids, list) or not account_ids:
        return _json_error("ACCOUNT_IDS_REQUIRED", "请选择要回收的邮箱")

    try:
        parsed_ids = [int(aid) for aid in account_ids]
    except (TypeError, ValueError):
        return _json_error("ACCOUNT_IDS_INVALID", "account_ids 必须是整数数组")

    released = 0
    for aid in parsed_ids:
        if accounts_repo.assign_account_owner(aid, None):
            released += 1

    log_audit("unassign", "user", None, f"回收邮箱：成功={released}")
    return jsonify({"success": True, "message": f"已回收 {released} 个邮箱（归还管理员）", "released": released})


@login_required
@admin_required
def api_list_unassigned_accounts() -> Any:
    """分配选择器：返回全部账号并标注当前归属用户（修复已分配混入未分配的问题）。"""
    accounts = accounts_repo.list_accounts_with_owner()
    result = [
        {
            "id": a["id"],
            "email": a["email"],
            "group_id": a.get("group_id"),
            "status": a.get("status", "active"),
            "owner_user_id": a.get("owner_user_id"),
            "owner_username": a.get("owner_username"),
        }
        for a in accounts
    ]
    return jsonify({"success": True, "accounts": result})
