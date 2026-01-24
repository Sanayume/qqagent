"""
用户管理服务

管理管理员用户的创建、验证和密码管理。
用户数据存储在 config/admin_users.json 中。
"""

import json
from pathlib import Path
from typing import Optional

from passlib.context import CryptContext
from pydantic import BaseModel

from src.utils.logger import log


# 密码哈希上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 用户数据文件路径
USERS_FILE = Path("config/admin_users.json")


class AdminUser(BaseModel):
    """管理员用户模型"""
    username: str
    hashed_password: str
    display_name: str = ""
    is_active: bool = True


class UserService:
    """用户管理服务"""
    
    def __init__(self, users_file: Path = USERS_FILE):
        self.users_file = users_file
        self._users: dict[str, AdminUser] = {}
        self._load_users()
    
    def _load_users(self):
        """从文件加载用户数据"""
        if not self.users_file.exists():
            log.info(f"用户文件不存在，创建默认管理员: {self.users_file}")
            self._create_default_admin()
            return
        
        try:
            with open(self.users_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            self._users = {}
            for username, user_data in data.get("users", {}).items():
                self._users[username] = AdminUser(
                    username=username,
                    **user_data
                )
            
            log.info(f"已加载 {len(self._users)} 个管理员用户")
        except Exception as e:
            log.error(f"加载用户文件失败: {e}")
            self._create_default_admin()
    
    def _create_default_admin(self):
        """创建默认管理员账户"""
        default_password = "admin123"  # 默认密码，首次登录后应修改
        hashed = pwd_context.hash(default_password)
        
        self._users = {
            "admin": AdminUser(
                username="admin",
                hashed_password=hashed,
                display_name="管理员",
                is_active=True,
            )
        }
        
        self._save_users()
        log.warning(f"已创建默认管理员账户 (用户名: admin, 密码: {default_password})")
    
    def _save_users(self):
        """保存用户数据到文件"""
        self.users_file.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "users": {
                username: {
                    "hashed_password": user.hashed_password,
                    "display_name": user.display_name,
                    "is_active": user.is_active,
                }
                for username, user in self._users.items()
            }
        }
        
        with open(self.users_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def get_user(self, username: str) -> Optional[AdminUser]:
        """获取用户"""
        return self._users.get(username)
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """验证密码"""
        return pwd_context.verify(plain_password, hashed_password)
    
    def authenticate(self, username: str, password: str) -> Optional[AdminUser]:
        """认证用户
        
        Args:
            username: 用户名
            password: 明文密码
            
        Returns:
            AdminUser 如果认证成功，否则 None
        """
        user = self.get_user(username)
        if user is None:
            return None
        
        if not user.is_active:
            return None
        
        if not self.verify_password(password, user.hashed_password):
            return None
        
        return user
    
    def change_password(self, username: str, old_password: str, new_password: str) -> bool:
        """修改密码
        
        Args:
            username: 用户名
            old_password: 旧密码
            new_password: 新密码
            
        Returns:
            是否成功
        """
        user = self.authenticate(username, old_password)
        if user is None:
            return False
        
        user.hashed_password = pwd_context.hash(new_password)
        self._save_users()
        log.info(f"用户 {username} 修改了密码")
        return True
    
    def create_user(self, username: str, password: str, display_name: str = "") -> bool:
        """创建用户
        
        Args:
            username: 用户名
            password: 密码
            display_name: 显示名称
            
        Returns:
            是否成功
        """
        if username in self._users:
            return False
        
        self._users[username] = AdminUser(
            username=username,
            hashed_password=pwd_context.hash(password),
            display_name=display_name or username,
            is_active=True,
        )
        
        self._save_users()
        log.info(f"创建了新用户: {username}")
        return True


# 全局单例
_user_service: Optional[UserService] = None


def get_user_service() -> UserService:
    """获取用户服务单例"""
    global _user_service
    if _user_service is None:
        _user_service = UserService()
    return _user_service
