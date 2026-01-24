"""
认证 API 路由

提供登录、登出、获取当前用户等接口。
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.admin.auth import (
    Token,
    create_access_token,
    get_current_user,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)
from src.admin.services.user_service import get_user_service


router = APIRouter(prefix="/api/auth", tags=["认证"])


class LoginRequest(BaseModel):
    """登录请求"""
    username: str
    password: str


class UserInfo(BaseModel):
    """用户信息响应"""
    username: str
    display_name: str


class ChangePasswordRequest(BaseModel):
    """修改密码请求"""
    old_password: str
    new_password: str


@router.post("/login", response_model=Token)
async def login(request: LoginRequest):
    """用户登录
    
    验证用户名和密码，返回 JWT Token。
    """
    user_service = get_user_service()
    user = user_service.authenticate(request.username, request.password)
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )
    
    access_token = create_access_token(user.username)
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/logout")
async def logout(current_user: str = Depends(get_current_user)):
    """用户登出
    
    由于使用无状态 JWT，实际登出由客户端删除 Token 实现。
    此接口仅用于记录日志和未来可能的 Token 黑名单。
    """
    return {"message": "登出成功", "username": current_user}


@router.get("/me", response_model=UserInfo)
async def get_me(current_user: str = Depends(get_current_user)):
    """获取当前登录用户信息"""
    user_service = get_user_service()
    user = user_service.get_user(current_user)
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )
    
    return UserInfo(
        username=user.username,
        display_name=user.display_name,
    )


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user: str = Depends(get_current_user),
):
    """修改密码"""
    user_service = get_user_service()
    success = user_service.change_password(
        current_user,
        request.old_password,
        request.new_password,
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="旧密码错误",
        )
    
    return {"message": "密码修改成功"}
