"""鉴权接口——注册、登录、修改密码、获取当前用户"""
import logging
import re
import secrets
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.user import User
from backend.core.auth_dependencies import get_current_user, require_admin
from backend.core.security import (
    hash_password, verify_password, create_token,
    check_password_strength,
)
from backend.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()
USERNAME_RE = re.compile(r"^[A-Za-z0-9_\-\u4e00-\u9fff]{2,50}$")
SYSTEM_GUEST_USERNAME = "__guest__"
RESERVED_USERNAMES = {SYSTEM_GUEST_USERNAME}

# ============================================================
# 请求 / 响应模型（标准化 Pydantic）
# ============================================================
class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=8, max_length=128)
    department: str = Field(default="", max_length=50)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        value = value.strip()
        if not USERNAME_RE.fullmatch(value):
            raise ValueError("用户名只能包含中文、字母、数字、下划线或短横线")
        return value

    @field_validator("department")
    @classmethod
    def normalize_department(cls, value: str) -> str:
        return value.strip()

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=1, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.strip()

class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)

class AuthResponse(BaseModel):
    username: str
    role: str

class UserInfoResponse(BaseModel):
    username: str
    role: str
    department: str
    is_active: bool
    created_at: datetime

class MessageResponse(BaseModel):
    message: str

class UserListItem(BaseModel):
    id: int
    username: str
    role: str
    department: str
    is_active: bool
    created_at: datetime

class UpdateUserRoleRequest(BaseModel):
    username: str
    role: str = Field(..., pattern="^(guest|employee|admin)$")

class UpdateUserStatusRequest(BaseModel):
    username: str
    is_active: bool


# ============================================================
# 简易内存限流（开发用，生产切 slowapi + Redis）
# ============================================================
_rate_store: dict[str, list[float]] = {}

def _check_rate_limit(ip: str, max_per_minute: int = 10) -> bool:
    """返回 True=放行，False=超限"""
    import time
    now = time.time()
    window = [t for t in _rate_store.get(ip, []) if now - t < 60]
    _rate_store[ip] = window
    if len(window) >= max_per_minute:
        return False
    window.append(now)
    return True


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _issue_auth_cookie(response: Response, user: User) -> None:
    token = create_token({
        "sub": user.username,
        "role": user.role,
        "ver": int(user.token_version or 0),
    })
    response.set_cookie(
        key=settings.COOKIE_NAME,
        value=token,
        max_age=settings.JWT_EXPIRE_HOURS * 3600,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


def _public_username(user: User) -> str:
    return "游客" if user.username == SYSTEM_GUEST_USERNAME else user.username


def _get_or_create_guest_user(db: Session) -> User:
    user = db.query(User).filter(User.username == SYSTEM_GUEST_USERNAME).first()
    if user:
        changed = False
        if user.role != "guest":
            user.role = "guest"
            user.token_version = (user.token_version or 0) + 1
            changed = True
        if not user.is_active:
            user.is_active = True
            user.token_version = (user.token_version or 0) + 1
            changed = True
        if changed:
            db.commit()
            db.refresh(user)
        return user

    user = User(
        username=SYSTEM_GUEST_USERNAME,
        password_hash=hash_password(secrets.token_urlsafe(32)),
        role="guest",
        department="",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ============================================================
# 接口
# ============================================================
@router.post("/auth/register", response_model=AuthResponse, summary="用户注册")
def register(req: RegisterRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = _client_ip(request)
    if not _check_rate_limit(f"reg:{ip}", settings.RATE_LIMIT_PER_MINUTE):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")

    # 密码强度
    ok, msg = check_password_strength(req.password)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    # 用户名唯一
    if req.username in RESERVED_USERNAMES:
        raise HTTPException(status_code=400, detail="该用户名不可注册")
    if db.query(User).filter(User.username == req.username).first():
        raise HTTPException(status_code=400, detail="用户名已被注册")

    # 所有自主注册账号均为游客，员工和管理员角色只能由管理员授予。
    role = "guest"

    user = User(
        username=req.username,
        password_hash=hash_password(req.password),
        role=role,
        department=req.department,
    )
    db.add(user)
    db.commit()

    _issue_auth_cookie(response, user)
    logger.info(f"[注册] {req.username} (role={role}, ip={ip})")
    return AuthResponse(username=_public_username(user), role=user.role)


@router.post("/auth/login", response_model=AuthResponse, summary="用户登录")
def login(req: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = _client_ip(request)
    if not _check_rate_limit(f"login:{ip}", settings.RATE_LIMIT_PER_MINUTE):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")

    user = db.query(User).filter(User.username == req.username).first()
    if not user or not verify_password(req.password, user.password_hash):
        logger.warning(f"[登录失败] {req.username} (ip={ip})")
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    if not user.is_active:
        logger.warning(f"[登录] 已禁用账号: {req.username}")
        raise HTTPException(status_code=403, detail="账号已被禁用")

    _issue_auth_cookie(response, user)
    logger.info(f"[登录成功] {req.username} (ip={ip})")
    return AuthResponse(username=_public_username(user), role=user.role)


@router.post("/auth/guest-login", response_model=AuthResponse, summary="游客一键登录")
def guest_login(request: Request, response: Response, db: Session = Depends(get_db)):
    ip = _client_ip(request)
    if not _check_rate_limit(f"guest:{ip}", settings.RATE_LIMIT_PER_MINUTE):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")

    user = _get_or_create_guest_user(db)
    _issue_auth_cookie(response, user)
    logger.info("[游客登录] ip=%s", ip)
    return AuthResponse(username=_public_username(user), role=user.role)


@router.post("/auth/logout", response_model=MessageResponse, summary="退出登录")
def logout(response: Response):
    response.delete_cookie(settings.COOKIE_NAME, path="/")
    return MessageResponse(message="已退出登录")


@router.get("/auth/me", response_model=UserInfoResponse, summary="获取当前用户")
def get_me(
    user: User = Depends(get_current_user),
):
    return UserInfoResponse(
        username=_public_username(user),
        role=user.role,
        department=user.department,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.post("/auth/change-password", response_model=MessageResponse, summary="修改密码")
def change_password(
    req: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(req.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="原密码错误")

    ok, msg = check_password_strength(req.new_password)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    user.password_hash = hash_password(req.new_password)
    user.token_version = (user.token_version or 0) + 1
    db.commit()
    logger.info(f"[修改密码] {user.username}")
    return MessageResponse(message="密码修改成功")


def _active_admin_count(db: Session) -> int:
    return db.query(User).filter(User.role == "admin", User.is_active.is_(True)).count()


@router.get("/auth/users", response_model=list[UserListItem], summary="管理员查看用户列表")
def list_users(
    _current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    users = db.query(User).filter(User.username != SYSTEM_GUEST_USERNAME).order_by(User.created_at.desc()).all()
    return [
        UserListItem(
            id=user.id,
            username=user.username,
            role=user.role,
            department=user.department or "",
            is_active=bool(user.is_active),
            created_at=user.created_at,
        )
        for user in users
    ]


@router.post("/auth/users/role", response_model=MessageResponse, summary="管理员修改用户角色")
def update_user_role(
    req: UpdateUserRoleRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    target = db.query(User).filter(User.username == req.username).first()
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    if target.username == SYSTEM_GUEST_USERNAME:
        raise HTTPException(status_code=400, detail="系统游客账号不可修改权限")

    if target.username == current_user.username and req.role != "admin":
        raise HTTPException(status_code=400, detail="不能取消自己的管理员权限")

    if target.role == "admin" and req.role != "admin" and _active_admin_count(db) <= 1:
        raise HTTPException(status_code=400, detail="至少需要保留一个启用的管理员")

    target.role = req.role
    target.token_version = (target.token_version or 0) + 1
    db.commit()
    logger.info("[权限变更] %s 将 %s 设置为 %s", current_user.username, target.username, req.role)
    return MessageResponse(message="用户角色已更新")


@router.post("/auth/users/status", response_model=MessageResponse, summary="管理员启用或禁用用户")
def update_user_status(
    req: UpdateUserStatusRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    target = db.query(User).filter(User.username == req.username).first()
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    if target.username == SYSTEM_GUEST_USERNAME:
        raise HTTPException(status_code=400, detail="系统游客账号不可禁用")

    if target.username == current_user.username and not req.is_active:
        raise HTTPException(status_code=400, detail="不能禁用自己的账号")

    if target.role == "admin" and not req.is_active and _active_admin_count(db) <= 1:
        raise HTTPException(status_code=400, detail="至少需要保留一个启用的管理员")

    target.is_active = req.is_active
    target.token_version = (target.token_version or 0) + 1
    db.commit()
    logger.info("[账号状态] %s 将 %s 设置为 %s", current_user.username, target.username, req.is_active)
    return MessageResponse(message="用户状态已更新")
