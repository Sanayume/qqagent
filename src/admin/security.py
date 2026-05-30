"""Admin Console security checks."""

from __future__ import annotations

import secrets
from typing import Any


DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin123"
DEFAULT_ADMIN_SECRET = "change-me-to-a-random-string"


def is_default_admin_password(admin_cfg: dict[str, Any]) -> bool:
    return (
        admin_cfg.get("username", DEFAULT_ADMIN_USERNAME) == DEFAULT_ADMIN_USERNAME
        and admin_cfg.get("password", DEFAULT_ADMIN_PASSWORD) == DEFAULT_ADMIN_PASSWORD
    )


def is_default_admin_secret(admin_cfg: dict[str, Any]) -> bool:
    return admin_cfg.get("secret_key", DEFAULT_ADMIN_SECRET) == DEFAULT_ADMIN_SECRET


def verify_admin_password(admin_cfg: dict[str, Any], username: str, password: str) -> bool:
    expected_user = str(admin_cfg.get("username", DEFAULT_ADMIN_USERNAME))
    expected_password = str(admin_cfg.get("password", DEFAULT_ADMIN_PASSWORD))
    return secrets.compare_digest(username, expected_user) and secrets.compare_digest(
        password,
        expected_password,
    )


def get_admin_security_warnings(admin_cfg: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if is_default_admin_password(admin_cfg):
        warnings.append("Admin Console is using the default username/password.")
    if is_default_admin_secret(admin_cfg):
        warnings.append("Admin Console is using the default JWT secret_key.")
    if admin_cfg.get("allow_query_token", False):
        warnings.append("HTTP query-token authentication is enabled.")
    return warnings
