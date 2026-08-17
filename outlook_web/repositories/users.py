"""多用户模式 — 用户仓储层

提供 users 表 CRUD 与账号归属辅助查询。
"""

from __future__ import annotations

from typing import Any

from outlook_web.db import create_sqlite_connection, get_db
from outlook_web.security.crypto import hash_password, verify_password


def _conn():
    """获取数据库连接；若 Flask g 连接已关闭（跨 test_client 场景），回退新建连接。"""
    try:
        db = get_db()
        try:
            db.execute("SELECT 1").fetchone()
            return db
        except Exception:
            return create_sqlite_connection()
    except RuntimeError:
        return create_sqlite_connection()


def get_user_by_username(username: str) -> dict[str, Any] | None:
    """按用户名查询用户（含密码哈希）。"""
    db = _conn()
    row = db.execute(
        "SELECT * FROM users WHERE username = ? LIMIT 1",
        (username.strip(),),
    ).fetchone()
    return dict(row) if row else None


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    """按 ID 查询用户（不含密码哈希）。"""
    db = _conn()
    row = db.execute(
        "SELECT id, username, role, display_name, status, created_at FROM users WHERE id = ? LIMIT 1",
        (user_id,),
    ).fetchone()
    return dict(row) if row else None


def verify_user_credentials(username: str, password: str) -> dict[str, Any] | None:
    """校验用户名 + 密码，成功返回用户信息（不含密码哈希），失败返回 None。"""
    user = get_user_by_username(username)
    if not user:
        return None
    if user.get("status") != "active":
        return None
    if not verify_password(password, user.get("password_hash", "")):
        return None
    return {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "display_name": user.get("display_name", ""),
    }


def list_users() -> list[dict[str, Any]]:
    """列出所有用户（不含密码哈希）。"""
    db = _conn()
    rows = db.execute("""
        SELECT id, username, role, display_name, status, created_at
        FROM users ORDER BY id ASC
        """).fetchall()
    return [dict(r) for r in rows]


def create_user(username: str, password: str, role: str = "member", display_name: str = "") -> dict[str, Any] | None:
    """创建用户。用户名重复返回 None。"""
    db = _conn()
    username = (username or "").strip()
    if not username:
        return None
    try:
        cursor = db.execute(
            """
            INSERT INTO users (username, password_hash, role, display_name, status)
            VALUES (?, ?, ?, ?, 'active')
            """,
            (username, hash_password(password), role, display_name),
        )
        db.commit()
        return get_user_by_id(cursor.lastrowid)
    except Exception:
        return None


def update_user(
    user_id: int,
    *,
    password: str | None = None,
    role: str | None = None,
    display_name: str | None = None,
    status: str | None = None,
) -> bool:
    """更新用户信息。"""
    db = _conn()
    fields = []
    params: list[Any] = []
    if password is not None:
        fields.append("password_hash = ?")
        params.append(hash_password(password))
    if role is not None:
        fields.append("role = ?")
        params.append(role)
    if display_name is not None:
        fields.append("display_name = ?")
        params.append(display_name)
    if status is not None:
        fields.append("status = ?")
        params.append(status)
    if not fields:
        return False
    fields.append("updated_at = CURRENT_TIMESTAMP")
    params.append(user_id)
    try:
        db.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", params)
        db.commit()
        return True
    except Exception:
        return False


def delete_user(user_id: int) -> bool:
    """删除用户（其名下的账号 owner_user_id 置空，归还管理员）。"""
    db = _conn()
    try:
        db.execute("UPDATE accounts SET owner_user_id = NULL WHERE owner_user_id = ?", (user_id,))
        db.execute("DELETE FROM user_notification_settings WHERE user_id = ?", (user_id,))
        db.execute("DELETE FROM users WHERE id = ?", (user_id,))
        db.commit()
        return True
    except Exception:
        return False


def count_owned_accounts(user_id: int) -> int:
    """统计某用户名下账号数。"""
    db = _conn()
    row = db.execute(
        "SELECT COUNT(*) AS c FROM accounts WHERE owner_user_id = ?",
        (user_id,),
    ).fetchone()
    return int(row["c"] or 0) if row else 0


def get_notification_setting(user_id: int, channel: str) -> dict[str, Any]:
    """读取用户通知配置。"""
    db = _conn()
    row = db.execute(
        "SELECT config_json FROM user_notification_settings WHERE user_id = ? AND channel = ?",
        (user_id, channel),
    ).fetchone()
    if not row:
        return {}
    import json

    try:
        return json.loads(row["config_json"] or "{}")
    except Exception:
        return {}


def set_notification_setting(user_id: int, channel: str, config: dict[str, Any]) -> bool:
    """写入用户通知配置。"""
    import json

    db = _conn()
    try:
        db.execute(
            """
            INSERT OR REPLACE INTO user_notification_settings (user_id, channel, config_json, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (user_id, channel, json.dumps(config, ensure_ascii=False)),
        )
        db.commit()
        return True
    except Exception:
        return False
