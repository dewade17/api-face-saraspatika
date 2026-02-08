"""
rbac_utils.py
=================

This module provides a simple role-based access control (RBAC) helper for the
Flask application.  It mirrors the RBAC implementation used in the Next.js
backend (`saraspatika`) so that authorization logic lives on the server side
rather than purely in the client.  Permissions are granted to roles on a
``resource:action`` basis.  Users inherit permissions from the roles
associated with their account and may have per‑permission overrides via the
``user_permission_overrides`` table.

When a route is decorated with ``@require_permission(resource, action)``, the
current user's permissions are looked up.  If the user lacks the specified
permission a 403 Forbidden response is triggered.  A lightweight in‑memory
cache with a configurable TTL is used to avoid hitting the database on every
request.

The RBAC logic is separate from authentication; routes should still be
decorated with ``@token_required`` to ensure a valid JWT is present.
"""

from __future__ import annotations

import time
from functools import wraps
from typing import Callable

from flask import abort

from .auth_utils import get_user_id_from_auth
from ..db import get_session
from ..db.models import UserRole, RolePermission, UserPermissionOverride, Permission

__all__ = ["require_permission", "can", "clear_perm_cache"]

# A small TTL cache (in seconds) to store computed permission sets.  Adjust
# TTL as needed; a longer TTL reduces database queries but delays changes
# propagating.  60 seconds mirrors the behaviour in the Next.js backend.
_CACHE_TTL = 60

class _PermCacheEntry:
    __slots__ = ("perm_set", "expires")

    def __init__(self, perm_set: set[str], expires: float):
        self.perm_set = perm_set
        self.expires = expires


_perm_cache: dict[str, _PermCacheEntry] = {}


def _perm_key(resource: str, action: str) -> str:
    """Return a canonical ``resource:action`` key for permission lookup."""
    return f"{resource or ''}:{action or ''}".lower()


def _compute_user_perm_set(user_id: str) -> set[str]:
    """
    Compute the set of permission keys granted to ``user_id``.

    The algorithm mirrors the Next.js implementation:

      1. All ``RolePermission`` records for the user's roles are loaded.  Each
         permission contributes its resource/action key to the base set.
      2. All per-user overrides are fetched.  For each override, its
         ``permission.resource``/``permission.action`` key is either added or
         removed from the base set depending on ``grant``.

    The result is a set of strings like ``"absensi:create"``.  The set is
    returned and also stored in the global cache with the current time.
    """
    with get_session() as s:
        # Start with permissions granted via roles
        perm_set: set[str] = set()
        # Join through UserRole -> RolePermission -> Permission
        role_perms = (
            s.query(Permission.resource, Permission.action)
            .join(RolePermission, Permission.id_permission == RolePermission.id_permission)
            .join(UserRole, RolePermission.id_role == UserRole.id_role)
            .filter(UserRole.id_user == user_id)
            .all()
        )
        for resource, action in role_perms:
            if resource and action:
                perm_set.add(_perm_key(resource, action))

        # Apply per-user overrides (grant=True adds, grant=False removes)
        overrides = (
            s.query(UserPermissionOverride.grant, Permission.resource, Permission.action)
            .join(Permission, Permission.id_permission == UserPermissionOverride.id_permission)
            .filter(UserPermissionOverride.id_user == user_id)
            .all()
        )
        for grant, resource, action in overrides:
            if not resource or not action:
                continue
            k = _perm_key(resource, action)
            if grant:
                perm_set.add(k)
            else:
                perm_set.discard(k)

        # Update cache
        _perm_cache[user_id] = _PermCacheEntry(perm_set, time.time() + _CACHE_TTL)
        return perm_set


def _get_user_perm_set(user_id: str) -> set[str]:
    """
    Fetch the cached permission set for ``user_id`` or compute it if missing.

    This helper respects the TTL on cached entries: if the cache entry has
    expired the permissions are recomputed.
    """
    entry = _perm_cache.get(user_id)
    now = time.time()
    if entry is not None and entry.expires > now:
        return entry.perm_set
    # Cache miss or expired
    return _compute_user_perm_set(user_id)


def can(user_id: str, resource: str, action: str) -> bool:
    """
    Check whether ``user_id`` has permission to perform ``action`` on ``resource``.

    :param user_id: The UUID of the user (subject).  If falsy, returns False.
    :param resource: The protected resource name (e.g. ``"absensi"``).
    :param action: The action (e.g. ``"create"``, ``"read"``, ``"update"``, ``"delete"``).
    :returns: ``True`` if the user has the specified permission, ``False`` otherwise.
    """
    if not user_id:
        return False
    perm_set = _get_user_perm_set(user_id)
    return _perm_key(resource, action) in perm_set


def require_permission(resource: str, action: str) -> Callable[[Callable], Callable]:
    """
    Decorator to enforce a specific permission on a Flask route.

    Routes using this decorator **must** also be protected by
    ``@token_required`` to ensure that a valid JWT has been processed.  The
    decorator looks up the current user id using ``get_user_id_from_auth`` and
    then checks the permission set using :func:`can`.  If the permission is
    missing, a 403 Forbidden response is raised via ``abort``.

    Usage::

        @absensi_bp.post("/checkin")
        @token_required
        @require_permission("absensi", "create")
        def checkin():
            ...

    :param resource: The resource name to protect.
    :param action: The required action on that resource.
    :returns: A decorator applying the permission check.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapped(*args, **kwargs):
            user_id = get_user_id_from_auth() or ""
            if not can(user_id, resource, action):
                # Raise 403 Forbidden.  Provide a generic message to avoid leaking
                # details about what permissions are missing.
                abort(403, description="Akses ditolak")
            return func(*args, **kwargs)

        return wrapped

    return decorator


def clear_perm_cache(user_id: str | None = None) -> None:
    """
    Clear the cached permission set for ``user_id`` or all users.

    This helper may be called after making changes to role assignments or
    permission overrides to ensure that subsequent requests see the updated
    state.

    :param user_id: If provided, only the cache entry for this user is
        removed.  Otherwise the entire cache is purged.
    """
    if user_id:
        _perm_cache.pop(user_id, None)
    else:
        _perm_cache.clear()