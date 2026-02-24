"""
用户管理服务

从 config.yaml 的 admin 段读取管理员账号密码。
"""

from typing import Optional
from pydantic import BaseModel
from src.utils.logger import log


class AdminUser(BaseModel):
    """管理员用户模型"""
    username: str
    display_name: str = ""
    is_active: bool = True


class UserService:
    """用户管理服务 — 从 config.yaml 读取凭据"""

    def _get_admin_config(self) -> dict:
        """从 config loader 获取 admin 配置"""
        from src.utils.config_loader import get_config_loader
        return get_config_loader().config.admin

    def authenticate(self, username: str, password: str) -> Optional[AdminUser]:
        """认证用户

        Args:
            username: 用户名
            password: 明文密码

        Returns:
            AdminUser 如果认证成功，否则 None
        """
        cfg = self._get_admin_config()
        expected_user = cfg.get("username", "admin")
        expected_pass = cfg.get("password", "admin123")

        if username != expected_user:
            return None
        if password != expected_pass:
            return None

        return AdminUser(
            username=username,
            display_name="管理员",
            is_active=True,
        )

    def get_user(self, username: str) -> Optional[AdminUser]:
        """获取用户（仅当用户名匹配配置时返回）"""
        cfg = self._get_admin_config()
        expected_user = cfg.get("username", "admin")
        if username != expected_user:
            return None
        return AdminUser(
            username=expected_user,
            display_name="管理员",
            is_active=True,
        )


# 全局单例
_user_service: Optional[UserService] = None


def get_user_service() -> UserService:
    """获取用户服务单例"""
    global _user_service
    if _user_service is None:
        _user_service = UserService()
    return _user_service
