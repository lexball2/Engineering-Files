from collections.abc import Callable

from fastapi import Cookie, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.config import settings
from backend.core.security import decode_token
from backend.database import get_db
from backend.models.user import User

security = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    cookie_token: str | None = Cookie(default=None, alias=settings.COOKIE_NAME),
    db: Session = Depends(get_db),
) -> User:
    token = credentials.credentials if credentials else cookie_token
    payload = decode_token(token or "")
    if not payload:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")

    username = payload.get("sub")
    user = db.query(User).filter(User.username == username).first()
    if not user or not user.is_active or int(payload.get("ver", -1)) != int(user.token_version or 0):
        raise HTTPException(status_code=401, detail="用户不存在或已被禁用")
    return user


def require_roles(*roles: str) -> Callable[[User], User]:
    allowed = set(roles)

    def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed:
            raise HTTPException(status_code=403, detail="当前账号没有执行该操作的权限")
        return current_user

    return checker


require_admin = require_roles("admin")
require_staff = require_roles("employee", "admin")
