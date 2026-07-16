
"""安全工具——密码加密、密码强度校验、JWT 生成与验证"""
from typing import Optional
import re
from uuid import uuid4
import jwt
from passlib.context import CryptContext
from backend.config import settings
from datetime import datetime, timezone, timedelta


TZ = timezone(timedelta(hours=8))
# 密码加密器
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def check_password_strength(password: str) -> tuple[bool, str]:
    """
    校验密码复杂度强度
    规则：
    1. 长度 ≥8 位
    2. 包含大写英文字母
    3. 包含小写英文字母
    4. 包含数字
    返回：(是否合法, 提示文案)
    """
    if len(password) < 8:
        return False, "密码长度不能少于8位"
    if len(password.encode("utf-8")) > 72:
        return False, "密码过长，UTF-8 编码后不能超过72字节"
    if not re.search(r"[A-Z]", password):
        return False, "密码必须包含大写字母"
    if not re.search(r"[a-z]", password):
        return False, "密码必须包含小写字母"
    if not re.search(r"\d", password):
        return False, "密码必须包含数字"
    return True, "密码强度合格"


def hash_password(password: str) -> str:
    """明文密码 → 加密哈希"""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """验证明文密码是否匹配哈希"""
    return pwd_context.verify(plain, hashed)


def create_token(data: dict, expires_hours: int | None = None) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + timedelta(hours=expires_hours or settings.JWT_EXPIRE_HOURS)
    to_encode.update({
        "exp": expire,
        "iat": now,
        "jti": str(uuid4()),
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
    })
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

def decode_token(token: str) -> Optional[dict]:
    """解析 JWT Token，失败/载荷缺失字段返回 None"""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            issuer=settings.JWT_ISSUER,
            audience=settings.JWT_AUDIENCE,
            options={"require": ["exp", "iat", "sub", "role", "ver"]},
        )
        # ====================== 修复缺陷4：强制校验必须字段 sub、role ======================
        if not payload or "sub" not in payload or "role" not in payload or "ver" not in payload:
            return None
        return payload
    except jwt.InvalidTokenError:
        return None
