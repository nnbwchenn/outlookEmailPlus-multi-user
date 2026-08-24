"""激活码仓储层：管理员批量生成 / 用户兑换绑定邮箱（原子性靠 UNIQUE(code_id, account_id) 兑底）"""

from __future__ import annotations

import secrets
import sqlite3
from typing import Any

from outlook_web.db import get_db

# 去除易混淆字符（0/O/1/I/L）的 32 字符集，12 位分 3 段
_CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
_CODE_CHUNK = 4
_CODE_CHUNKS = 3


def generate_code() -> str:
    """生成形如 XXXX-XXXX-XXXX 的激活码（约 45 bit 熵）。"""
    rng = secrets.SystemRandom()
    parts = ["".join(rng.choice(_CODE_ALPHABET) for _ in range(_CODE_CHUNK)) for _ in range(_CODE_CHUNKS)]
    return "-".join(parts)


def create_codes(count: int, max_bindings: int, created_by: int | None, note: str = "") -> list[str]:
    """批量生成激活码，返回码列表。码冲突时自动重试。"""
    conn = get_db()
    codes: list[str] = []
    for _ in range(count):
        for _attempt in range(10):
            code = generate_code()
            try:
                conn.execute(
                    "INSERT INTO activation_codes (code, max_bindings, status, created_by, note) VALUES (?, ?, 'active', ?, ?)",
                    (code, int(max_bindings), created_by, note),
                )
                codes.append(code)
                break
            except sqlite3.IntegrityError:
                continue
    conn.commit()
    return codes


def get_activation_summary() -> dict[str, int]:
    """激活码额度台账：可用邮箱数 / 未兑换码占用额度 / 还可签发额度。

    规则：不能超开 —— 全部未兑换激活码的可绑总数不得超过当前未分配邮箱数。
    """
    conn = get_db()
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM accounts WHERE owner_user_id IS NULL) AS available_mailboxes,
            COALESCE((
                SELECT SUM(max_bindings) FROM activation_codes
                WHERE status = 'active' AND redeemed_by IS NULL
            ), 0) AS outstanding_quota
        """
    ).fetchone()
    available = int(row["available_mailboxes"])
    outstanding = int(row["outstanding_quota"])
    return {
        "available_mailboxes": available,
        "outstanding_quota": outstanding,
        "remaining_capacity": max(0, available - outstanding),
    }


def get_code_by_text(code: str) -> dict[str, Any] | None:
    conn = get_db()
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM activation_codes WHERE code = ?", (str(code or "").strip().upper(),)
    ).fetchone()
    return dict(row) if row else None


def list_codes() -> list[dict[str, Any]]:
    conn = get_db()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT c.*,
               COALESCE(u.username, '') AS redeemed_by_username,
               (SELECT COUNT(*) FROM activation_code_bindings b WHERE b.code_id = c.id) AS bound_count
        FROM activation_codes c
        LEFT JOIN users u ON u.id = c.redeemed_by
        ORDER BY c.id DESC
        """
    ).fetchall()
    return [dict(r) for r in rows]


def set_status(code_id: int, status: str) -> bool:
    if status not in ("active", "disabled"):
        return False
    try:
        conn = get_db()
        cur = conn.execute(
            "UPDATE activation_codes SET status = ? WHERE id = ?", (status, int(code_id))
        )
        conn.commit()
        return cur.rowcount > 0
    except sqlite3.Error:
        return False


def delete_code(code_id: int) -> bool:
    try:
        conn = get_db()
        cur = conn.execute("DELETE FROM activation_codes WHERE id = ?", (int(code_id),))
        conn.commit()
        return cur.rowcount > 0
    except sqlite3.Error:
        return False


def redeem_code(code_row: dict[str, Any], user_id: int) -> dict[str, Any]:
    """原子兑换：把最多 max_bindings 个未分配邮箱绑定到 user 名下。

    返回 {"success": True, "bound": [...]} 或 {"success": False, "error": ...}。
    UNIQUE(code_id, account_id) 兜底防同一邮箱重复绑定同一激活码。
    """
    conn = get_db()
    conn.row_factory = sqlite3.Row
    try:
        code_id = int(code_row["id"])
        max_bindings = int(code_row["max_bindings"])
    except (TypeError, ValueError):
        return {"success": False, "error": "INVALID_CODE", "message": "激活码数据异常"}
    try:
        # 已被兑换过（含并发重复提交）：直接拒绝
        row = conn.execute(
            "SELECT redeemed_by FROM activation_codes WHERE id = ? AND redeemed_by IS NOT NULL",
            (code_id,),
        ).fetchone()
        if row:
            username = conn.execute("SELECT username FROM users WHERE id = ?", (row["redeemed_by"],)).fetchone()
            who = username["username"] if username else "其他用户"
            return {"success": False, "error": "ACTIVATION_CODE_USED", "message": f"该激活码已被 {who} 使用"}

        # 未分配（owner IS NULL）且未绑过此码的账号，取前 N 个
        candidates = conn.execute(
            """
            SELECT a.id, a.email FROM accounts a
            WHERE a.owner_user_id IS NULL
              AND NOT EXISTS (
                  SELECT 1 FROM activation_code_bindings b WHERE b.code_id = ? AND b.account_id = a.id
              )
            ORDER BY a.id ASC LIMIT ?
            """,
            (code_id, max_bindings),
        ).fetchall()

        if not candidates:
            return {"success": False, "error": "NO_AVAILABLE_MAILBOX", "message": "当前没有可绑定的未分配邮箱"}

        conn.execute("BEGIN")
        bound: list[dict[str, Any]] = []
        for acc in candidates:
            updated = conn.execute(
                "UPDATE accounts SET owner_user_id = ?, updated_at = datetime('now') WHERE id = ? AND owner_user_id IS NULL",
                (int(user_id), acc["id"]),
            )
            if updated.rowcount != 1:
                conn.execute("ROLLBACK")
                return redeem_code(code_row, user_id)  # 并发抢占：重试一轮
            conn.execute(
                "INSERT INTO activation_code_bindings (code_id, account_id, user_id) VALUES (?, ?, ?)",
                (code_id, acc["id"], int(user_id)),
            )
            bound.append({"id": acc["id"], "email": acc["email"]})

        conn.execute(
            "UPDATE activation_codes SET redeemed_by = ?, redeemed_at = datetime('now') WHERE id = ? AND redeemed_by IS NULL",
            (int(user_id), code_id),
        )
        conn.commit()
        return {"success": True, "bound": bound}
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise


def list_bindings_for_user(user_id: int) -> list[dict[str, Any]]:
    """用户已通过激活码绑定的邮箱（用于前端展示）。"""
    try:
        conn = get_db()
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT b.account_id, a.email, c.code, b.created_at
            FROM activation_code_bindings b
            JOIN accounts a ON a.id = b.account_id
            JOIN activation_codes c ON c.id = b.code_id
            WHERE b.user_id = ?
            ORDER BY b.id DESC
            """,
            (int(user_id),),
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.Error:
        return []
