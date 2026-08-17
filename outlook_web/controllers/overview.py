from __future__ import annotations

import time
from typing import Any

from flask import jsonify

from outlook_web.repositories import overview as overview_repo
from outlook_web.security.auth import get_current_user, login_required


# ==================== 概览 summary 进程级 TTL 缓存 ====================
# summary 是 dashboard 首屏加载的聚合查询（6 条 SQL），
# 在单 sync worker 下频繁刷新会加重排队。30 秒 TTL 兼顾数据实时性与请求降频。
def _get_owner_scope() -> int | None:
    """当前用户可见范围：admin=None（全部），member=自己的 user_id。"""
    user = get_current_user()
    if not user:
        return None
    if user.get("role") == "admin":
        return None
    return int(user.get("id") or 0) or None


# member 的 summary 缓存键：按 user_id 隔离
_OVERVIEW_SUMMARY_CACHE: dict | None = None
_OVERVIEW_SUMMARY_CACHE_AT: float = 0.0
_OVERVIEW_SUMMARY_CACHE_TTL: int = 30  # 秒


@login_required
def api_get_overview_summary() -> Any:
    global _OVERVIEW_SUMMARY_CACHE, _OVERVIEW_SUMMARY_CACHE_AT
    owner_scope = _get_owner_scope()
    cache_key = f"owner:{owner_scope if owner_scope is not None else 'all'}"
    now = time.time()
    cached = _OVERVIEW_SUMMARY_CACHE or {}
    if cache_key in cached and (now - _OVERVIEW_SUMMARY_CACHE_AT) < _OVERVIEW_SUMMARY_CACHE_TTL:
        return jsonify(cached[cache_key])
    result = overview_repo.get_overview_summary(owner_user_id=owner_scope)
    cached[cache_key] = result
    _OVERVIEW_SUMMARY_CACHE = cached
    _OVERVIEW_SUMMARY_CACHE_AT = now
    return jsonify(result)


@login_required
def api_get_overview_verification() -> Any:
    return jsonify(overview_repo.get_verification_stats(owner_user_id=_get_owner_scope()))


@login_required
def api_get_overview_external_api() -> Any:
    return jsonify(overview_repo.get_external_api_stats())


@login_required
def api_get_overview_pool() -> Any:
    # 邮箱池为管理员专属能力；member 返回空统计
    if _get_owner_scope() is not None:
        return jsonify(
            {
                "kpi": {
                    "available": 0,
                    "in_use": 0,
                    "cooldown": 0,
                    "used": 0,
                    "max_claimed_duration_s": 0,
                    "claim_count_7d": 0,
                    "complete_success_rate": 0,
                },
                "operation_distribution": {
                    "claim": 0,
                    "complete": 0,
                    "complete_success": 0,
                    "complete_fail": 0,
                    "release": 0,
                    "expire": 0,
                },
                "project_top5": [],
                "recent_operations": [],
            }
        )
    return jsonify(overview_repo.get_pool_stats())


@login_required
def api_get_overview_activity() -> Any:
    return jsonify(overview_repo.get_activity_stats())
