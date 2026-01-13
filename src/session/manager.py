"""
会话管理器

支持灵活的会话隔离策略:
- 全局用户模式: 某些用户在所有群/私聊共享一个上下文
- 群内用户隔离: 某些群内每个用户独立上下文
- 默认模式: 每个群一个上下文，每个私聊用户一个上下文
"""

from dataclasses import dataclass, field
from src.utils.logger import log


@dataclass
class SessionConfig:
    """会话配置
    
    Attributes:
        global_users: 全局用户列表 - 这些用户在所有群/私聊共享同一个上下文
        per_user_groups: 群内用户隔离列表 - 这些群内每个用户独立上下文
        all_groups_per_user: 如果为 True，所有群都启用用户隔离
    """
    # 全局用户 (这些用户不管在哪个群/私聊，都共享同一个上下文)
    global_users: set[int] = field(default_factory=set)
    
    # 群内用户隔离 (这些群内，每个用户有独立的上下文)
    per_user_groups: set[int] = field(default_factory=set)
    
    # 所有群都启用用户隔离
    all_groups_per_user: bool = False


class SessionManager:
    """会话管理器
    
    根据配置决定会话ID的生成策略。
    使用 ConfigLoader 动态获取最新配置。
    """
    
    def __init__(self, use_loader: bool = True):
        self.use_loader = use_loader
        if use_loader:
            from src.utils.config_loader import get_config_loader
            self.loader = get_config_loader()
            # 注册回调以便在配置更新时打日志
            self.loader.add_callback(self._on_config_update)
            log.info("SessionManager initialized with dynamic config loader")
        else:
            self.static_session_config = {"global_users": [], "per_user_groups": [], "all_groups_per_user": False}
            log.info("SessionManager initialized with static config")

    def _on_config_update(self, config):
        log.info("SessionManager: Configuration updated")
        log.debug(f"New session rules: {config.session}")

    @property
    def config(self):
        """获取当前配置"""
        if self.use_loader:
            return self.loader.config.session
        return self.static_session_config
    
    def get_session_id(
        self,
        user_id: int,
        group_id: int | None = None,
        is_private: bool = False,
    ) -> str:
        """生成会话ID
        
        Args:
            user_id: 用户QQ号
            group_id: 群号 (私聊时为 None)
            is_private: 是否为私聊
        
        Returns:
            会话ID字符串
        """
        cfg = self.config
        
        # 规则 1: 全局用户
        global_users = set(cfg.get("global_users", []))
        if user_id in global_users:
            session_id = f"global_{user_id}"
            log.debug(f"Session (global user): {session_id}")
            return session_id
        
        # 规则 2: 私聊
        if is_private or group_id is None:
            session_id = f"private_{user_id}"
            log.debug(f"Session (private): {session_id}")
            return session_id
        
        # 规则 3: 群内用户隔离
        per_user_groups = set(cfg.get("per_user_groups", []))
        all_groups_per_user = cfg.get("all_groups_per_user", False)
        
        if all_groups_per_user or group_id in per_user_groups:
            session_id = f"group_{group_id}_user_{user_id}"
            log.debug(f"Session (group per-user): {session_id}")
            return session_id
        
        # 规则 4: 默认群聊 (整个群共享)
        session_id = f"group_{group_id}"
        log.debug(f"Session (group shared): {session_id}")
        return session_id

