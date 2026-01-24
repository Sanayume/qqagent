"""
JWT 认证模块

提供 JWT Token 的生成、验证和依赖注入。
"""

import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from pydantic import BaseModel

# 配置
SECRET_KEY = os.getenv("ADMIN_SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24小时


class TokenData(BaseModel):
    """Token 数据模型"""
    username: str
    exp: datetime


class Token(BaseModel):
    """Token 响应模型"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # 秒


# Bearer Token 安全方案
security = HTTPBearer(auto_error=False)


def create_access_token(username: str, expires_delta: Optional[timedelta] = None) -> str:
    """创建 JWT Access Token
    
    Args:
        username: 用户名
        expires_delta: 过期时间增量，默认使用配置值
        
    Returns:
        JWT Token 字符串
    """
    if expires_delta is None:
        expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    expire = datetime.utcnow() + expires_delta
    to_encode = {
        "sub": username,
        "exp": expire,
        "iat": datetime.utcnow(),
    }
    
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> Optional[TokenData]:
    """验证 JWT Token
    
    Args:
        token: JWT Token 字符串
        
    Returns:
        TokenData 如果验证成功，否则 None
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        exp: datetime = datetime.fromtimestamp(payload.get("exp"))
        
        if username is None:
            return None
            
        return TokenData(username=username, exp=exp)
    except JWTError:
        return None


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> str:
    """获取当前登录用户（FastAPI 依赖）
    
    Args:
        credentials: HTTP Bearer 凭证
        
    Returns:
        当前用户名
        
    Raises:
        HTTPException: 401 如果未登录或 Token 无效
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token_data = verify_token(credentials.credentials)
    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return token_data.username


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[str]:
    """获取当前用户（可选，不强制登录）
    
    Args:
        credentials: HTTP Bearer 凭证
        
    Returns:
        用户名，如果未登录则返回 None
    """
    if credentials is None:
        return None
    
    token_data = verify_token(credentials.credentials)
    if token_data is None:
        return None
    
    return token_data.username
