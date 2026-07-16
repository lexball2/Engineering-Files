
"""用户表——ORM 模型定义"""
from datetime import datetime, timezone, timedelta
from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.orm import declarative_base

Base = declarative_base()

# 文件顶部加
TZ = timezone(timedelta(hours=8))

class User(Base):
    """用户表，管理知识库后台登录账号"""
    __tablename__ = "users"

    # 主键自增ID
    id = Column(Integer, primary_key=True, autoincrement=True, comment="用户唯一ID")
    # 用户名，唯一不可重复，建立索引加速查询
    username = Column(String(50), unique=True, nullable=False, index=True, comment="登录用户名")
    # 密码哈希，绝对不能存储明文密码
    password_hash = Column(String(255), nullable=False, comment="加密后的密码，不存明文")
    # 角色权限
    role = Column(String(20), default="guest", comment="角色：guest游客 / employee员工 / admin管理员")
    # 所属部门
    department = Column(String(50), default="", comment="用户所属部门")
    # 账号是否启用
    is_active = Column(Boolean, default=True, comment="账号是否可用，false代表禁用")
    token_version = Column(Integer, default=0, nullable=False, comment="令牌版本，改密或禁用时递增")
    # 创建时间
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(TZ))
    # 更新时间，数据修改时自动刷新
    updated_at = Column(DateTime, default=datetime.now(TZ), onupdate=datetime.now(TZ), comment="账号信息更新时间")

