from __future__ import annotations

import json
import secrets
import sqlite3
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any

# 成员级 Key：owner_user_id 非空；管理员全局 Key：owner_user_id IS NULL

from outlook_web.db import get_db
from outlook_web.security.crypto import decrypt_data, encrypt_data


class ExternalApiKeyNameConflictError(RuntimeError):
    """Raised when the database rejects a duplicate API Key name."""


def _execute_key_write(db: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> sqlite3.Cursor:
    try:
        return db.execute(sql, params)
    except sqlite3.IntegrityError as exc:
        if "idx_external_api_keys_name_unique" in str(exc):
            raise ExternalApiKeyNameConflictError("external_api_key_name_conflict") from exc
        raise


def _normalize_expires_at(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _is_expired(value: Any) -> bool:
    expires_at = _normalize_expires_at(value)
    if not expires_at:
        return False
    try:
        parsed = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed <= datetime.now(timezone.utc)


def _mask_secret_value(value: str, head: int = 4, tail: int = 4) -> str:
    if not value:
        return ""
    safe_value = str(value)
    if len(safe_value) <= head + tail:
        return "*" * len(safe_value)
    return safe_value[:head] + ("*" * (len(safe_value) - head - tail)) + safe_value[-tail:]


def _parse_allowed_emails(raw: Any) -> list[str]:
    if raw in (None, "", []):
        return []
    values = raw
    if isinstance(raw, str):
        try:
            values = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            values = [item.strip() for item in raw.replace("\r", "\n").replace(",", "\n").split("\n")]

    if not isinstance(values, list):
        return []

    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        email_addr = str(item or "").strip().lower()
        if not email_addr or "@" not in email_addr or email_addr in seen:
            continue
        seen.add(email_addr)
        result.append(email_addr)
    return result


def _allowed_emails_json(allowed_emails: Iterable[str] | None) -> str:
    return json.dumps(_parse_allowed_emails(list(allowed_emails or [])), ensure_ascii=False)


def _coerce_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "on"}:
        return True
    if text in {"false", "0", "no", "off"}:
        return False
    return default


def _coerce_int(value: Any, default: int) -> int:
    """安全 int 转换：失败返回 default（替代裸 int() 的统入口）。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _build_consumer_key(key_id: int | str) -> str:
    return f"key:{key_id}"


def _decrypt_api_key(value: str) -> str:
    if not value:
        return ""
    try:
        return decrypt_data(value)
    except Exception:
        return ""


def _serialize_row(row: Any) -> dict[str, Any]:
    api_key_plain = _decrypt_api_key(row["api_key_encrypted"] or "")
    allowed_emails = _parse_allowed_emails(row["allowed_emails_json"] or "[]")
    return {
        "id": row["id"],
        "consumer_key": _build_consumer_key(row["id"]),
        "name": row["name"] or "",
        "enabled": bool(row["enabled"]),
        "allowed_emails": allowed_emails,
        "pool_access": bool(row["pool_access"]),
        "owner_user_id": row["owner_user_id"] if "owner_user_id" in row.keys() else None,
        "expires_at": (row["expires_at"] or "") if "expires_at" in row.keys() else "",
        "expired": _is_expired(row["expires_at"]) if "expires_at" in row.keys() else False,
        "api_key_masked": _mask_secret_value(api_key_plain) if api_key_plain else "",
        "last_used_at": row["last_used_at"] or "",
        "created_at": row["created_at"] or "",
        "updated_at": row["updated_at"] or "",
    }


_EXTERNAL_API_KEY_COLUMNS = (
    "id, name, api_key_encrypted, allowed_emails_json, pool_access, enabled, owner_user_id, "
    "expires_at, last_used_at, created_at, updated_at"
)


def list_external_api_keys(
    *, include_disabled: bool = True, owner_user_id: int | None = None, unowned_only: bool = False
) -> list[dict[str, Any]]:
    db = get_db()
    sql = f"""
        SELECT {_EXTERNAL_API_KEY_COLUMNS}
        FROM external_api_keys
    """
    params: list[Any] = []
    conditions: list[str] = []
    if not include_disabled:
        conditions.append("enabled = 1")
    if owner_user_id is not None:
        conditions.append("owner_user_id = ?")
        params.append(_coerce_int(owner_user_id, 0))
    if unowned_only:
        conditions.append("owner_user_id IS NULL")
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY id ASC"
    rows = db.execute(sql, params).fetchall()
    return [_serialize_row(row) for row in rows]


def get_external_api_key_by_id(key_id: int) -> dict[str, Any] | None:
    db = get_db()
    row = db.execute(
        f"""
        SELECT {_EXTERNAL_API_KEY_COLUMNS}
        FROM external_api_keys
        WHERE id = ?
        """,
        (_coerce_int(key_id, 0),),
    ).fetchone()
    return _serialize_row(row) if row else None


def create_external_api_key(
    *,
    name: str,
    api_key: str,
    allowed_emails: Iterable[str] | None = None,
    pool_access: bool = False,
    enabled: bool = True,
    owner_user_id: int | None = None,
    expires_at: str | None = None,
    commit: bool = True,
) -> dict[str, Any]:
    db = get_db()
    _execute_key_write(
        db,
        """
        INSERT INTO external_api_keys (name, api_key_encrypted, allowed_emails_json, pool_access, enabled, owner_user_id, expires_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (
            str(name or "").strip(),
            encrypt_data(str(api_key or "").strip()),
            _allowed_emails_json(allowed_emails),
            1 if _coerce_bool(pool_access, False) else 0,
            1 if _coerce_bool(enabled, True) else 0,
            _coerce_int(owner_user_id, 0) if owner_user_id is not None else None,
            _normalize_expires_at(expires_at),
        ),
    )
    if commit:
        db.commit()
    row_id = db.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    return get_external_api_key_by_id(row_id) or {}


def update_external_api_key(
    key_id: int,
    *,
    name: str | None = None,
    api_key: str | None = None,
    allowed_emails: Iterable[str] | None = None,
    pool_access: bool | None = None,
    enabled: bool | None = None,
    expires_at: str | None = None,
    commit: bool = True,
) -> dict[str, Any] | None:
    existing = get_external_api_key_by_id(_coerce_int(key_id, 0))
    if not existing:
        return None

    db = get_db()
    _execute_key_write(
        db,
        """
        UPDATE external_api_keys
        SET name = ?,
            api_key_encrypted = ?,
            allowed_emails_json = ?,
            pool_access = ?,
            enabled = ?,
            expires_at = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            str(existing["name"] if name is None else name).strip(),
            (
                encrypt_data(str(api_key).strip())
                if api_key is not None
                else db.execute(
                    "SELECT api_key_encrypted FROM external_api_keys WHERE id = ?",
                    (_coerce_int(key_id, 0),),
                ).fetchone()["api_key_encrypted"]
            ),
            _allowed_emails_json(existing["allowed_emails"] if allowed_emails is None else allowed_emails),
            _coerce_int(_coerce_bool(
                existing["pool_access"] if pool_access is None else pool_access,
                bool(existing["pool_access"]),
            ), 0),
            _coerce_int(_coerce_bool(
                existing["enabled"] if enabled is None else enabled,
                bool(existing["enabled"]),
            ), 1),
            _normalize_expires_at(existing["expires_at"] if expires_at is None else expires_at),
            _coerce_int(key_id, 0),
        ),
    )
    if commit:
        db.commit()
    return get_external_api_key_by_id(_coerce_int(key_id, 0))


def delete_external_api_key(key_id: int, *, commit: bool = True) -> bool:
    db = get_db()
    cursor = db.execute("DELETE FROM external_api_keys WHERE id = ?", (_coerce_int(key_id, 0),))
    if commit:
        db.commit()
    return cursor.rowcount > 0


def replace_external_api_keys(items: list[dict[str, Any]], *, commit: bool = True) -> list[dict[str, Any]]:
    # 仅替换管理员全局 Key；成员自建 Key（owner_user_id 非空）不受管理员全量替换影响
    existing_rows = list_external_api_keys(include_disabled=True, unowned_only=True)
    existing_ids = {_coerce_int(item["id"], -1): item for item in existing_rows}
    seen_ids: set[int] = set()

    for raw_item in items:
        item_id = raw_item.get("id")
        name = str(raw_item.get("name") or "").strip()
        api_key = raw_item.get("api_key")
        allowed_emails = raw_item.get("allowed_emails")
        pool_access = _coerce_bool(raw_item.get("pool_access", False), False)
        enabled = _coerce_bool(raw_item.get("enabled", True), True)
        expires_at = _normalize_expires_at(raw_item.get("expires_at"))

        if item_id in (None, ""):
            create_external_api_key(
                name=name,
                api_key=str(api_key or "").strip(),
                allowed_emails=_parse_allowed_emails(allowed_emails),
                pool_access=pool_access,
                enabled=enabled,
                expires_at=expires_at,
                commit=False,
            )
            continue

        key_id = _coerce_int(item_id, -1)
        existing = existing_ids.get(key_id)
        if not existing:
            continue
        seen_ids.add(key_id)
        if api_key == existing.get("api_key_masked"):
            api_key = None
        update_external_api_key(
            key_id,
            name=name,
            api_key=None if api_key in (None, "") and existing.get("api_key_masked") else api_key,
            allowed_emails=_parse_allowed_emails(allowed_emails) if allowed_emails is not None else existing["allowed_emails"],
            pool_access=pool_access,
            enabled=enabled,
            expires_at=_normalize_expires_at(existing["expires_at"]) if raw_item.get("expires_at") in (None, "") else expires_at,
            commit=False,
        )

    for key_id in existing_ids:
        if key_id not in seen_ids and existing_ids[key_id].get("owner_user_id") is None:
            delete_external_api_key(key_id, commit=False)

    if commit:
        get_db().commit()

    return list_external_api_keys(include_disabled=True)


def get_external_api_key_plaintext_by_id(key_id: int) -> str:
    """按 id 返回 Key 明文（仅服务端内部/归属校验后使用）。"""
    db = get_db()
    row = db.execute(
        "SELECT api_key_encrypted FROM external_api_keys WHERE id = ?",
        (_coerce_int(key_id, 0),),
    ).fetchone()
    if not row:
        return ""
    return _decrypt_api_key(row["api_key_encrypted"] or "")


def has_any_external_api_key_configured(*, enabled_only: bool = False) -> bool:
    db = get_db()
    sql = "SELECT COUNT(*) AS c FROM external_api_keys"
    params: list[Any] = []
    if enabled_only:
        sql += " WHERE enabled = 1"
    row = db.execute(sql, params).fetchone()
    return bool(row and _coerce_int(row["c"], 0) > 0)


def find_external_api_key_by_plaintext(provided_key: str) -> dict[str, Any] | None:
    provided = str(provided_key or "").strip()
    if not provided:
        return None

    db = get_db()
    rows = db.execute(f"""
        SELECT {_EXTERNAL_API_KEY_COLUMNS}
        FROM external_api_keys
        WHERE enabled = 1
        ORDER BY id ASC
        """).fetchall()

    for row in rows:
        plain = _decrypt_api_key(row["api_key_encrypted"] or "")
        if plain and secrets.compare_digest(plain, provided):
            return _serialize_row(row)
    return None


def mark_external_api_key_used(key_id: int) -> None:
    db = get_db()
    used_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    db.execute(
        """
        UPDATE external_api_keys
        SET last_used_at = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (used_at, _coerce_int(key_id, 0)),
    )
    db.commit()


def record_external_api_consumer_usage(
    *,
    consumer_key: str,
    consumer_name: str,
    endpoint: str,
    status: str,
) -> None:
    if not consumer_key or not endpoint:
        return
    db = get_db()
    usage_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    last_used_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    success_inc = 1 if str(status or "").lower() == "ok" else 0
    error_inc = 0 if success_inc else 1
    db.execute(
        """
        INSERT INTO external_api_consumer_usage_daily (
            consumer_key, consumer_name, caller_id, usage_date, date, endpoint,
            total_count, call_count, success_count, error_count, last_status, last_used_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, 1, 1, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(consumer_key, usage_date, endpoint)
        DO UPDATE SET
            consumer_name = excluded.consumer_name,
            caller_id = excluded.caller_id,
            date = excluded.date,
            total_count = external_api_consumer_usage_daily.total_count + 1,
            call_count = external_api_consumer_usage_daily.call_count + 1,
            success_count = external_api_consumer_usage_daily.success_count + excluded.success_count,
            error_count = external_api_consumer_usage_daily.error_count + excluded.error_count,
            last_status = excluded.last_status,
            last_used_at = excluded.last_used_at,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            consumer_key,
            str(consumer_name or "")[:120],
            str(consumer_name or consumer_key or "")[:120],
            usage_date,
            usage_date,
            str(endpoint or "")[:200],
            success_inc,
            error_inc,
            str(status or "")[:40],
            last_used_at,
        ),
    )
    db.commit()


def get_external_api_usage_summary(
    consumer_keys: list[str],
) -> dict[str, dict[str, Any]]:
    clean_keys = [str(item or "").strip() for item in consumer_keys if str(item or "").strip()]
    if not clean_keys:
        return {}

    db = get_db()
    usage_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    placeholders = ", ".join(["?"] * len(clean_keys))
    rows = db.execute(
        f"""
        SELECT consumer_key,
               SUM(total_count) AS total_count,
               SUM(success_count) AS success_count,
               SUM(error_count) AS error_count,
               MAX(last_used_at) AS last_used_at
        FROM external_api_consumer_usage_daily
        WHERE usage_date = ? AND consumer_key IN ({placeholders})
        GROUP BY consumer_key
        """,
        [usage_date] + clean_keys,
    ).fetchall()
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        result[row["consumer_key"]] = {
            "today_total_count": _coerce_int(row["total_count"], 0),
            "today_success_count": _coerce_int(row["success_count"], 0),
            "today_error_count": _coerce_int(row["error_count"], 0),
            "today_last_used_at": row["last_used_at"] or "",
        }
    return result
