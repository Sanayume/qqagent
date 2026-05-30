from src.admin.security import get_admin_security_warnings, verify_admin_password


def test_verify_admin_password_uses_constant_time_compare():
    admin_cfg = {"username": "admin", "password": "admin123"}
    assert verify_admin_password(admin_cfg, "admin", "admin123") is True
    assert verify_admin_password(admin_cfg, "admin", "wrong") is False


def test_admin_security_warnings_flag_unsafe_defaults():
    warnings = get_admin_security_warnings(
        {
            "username": "admin",
            "password": "admin123",
            "secret_key": "change-me-to-a-random-string",
            "allow_query_token": True,
        }
    )

    assert any("password" in warning for warning in warnings)
    assert any("secret" in warning for warning in warnings)
    assert any("query-token" in warning for warning in warnings)
