from datetime import datetime, timezone, timedelta
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint

from backend.models.user import Base

TZ = timezone(timedelta(hours=8))


class ImageAsset(Base):
    __tablename__ = "image_assets"

    id = Column(String(64), primary_key=True)
    filename = Column(String(255), nullable=False)
    stored_name = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    thumbnail_path = Column(String(500), nullable=False)
    mime_type = Column(String(100), default="")
    file_size = Column(Integer, default=0)
    width = Column(Integer, default=0)
    height = Column(Integer, default=0)
    description = Column(Text, default="")
    tags = Column(String(500), default="")
    category_id = Column(String(64), nullable=True)
    content_hash = Column(String(64), nullable=True, index=True)
    perceptual_hash = Column(String(32), nullable=True, index=True)
    group_id = Column(String(64), nullable=True, index=True)
    download_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(TZ))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(TZ), onupdate=lambda: datetime.now(TZ))
    last_downloaded_at = Column(DateTime(timezone=True), nullable=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), default="processing", nullable=False, index=True)
    processing_error = Column(Text, default="")


class ImageCategory(Base):
    __tablename__ = "image_categories"

    id = Column(String(64), primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(TZ))


class ImagePlatformUsage(Base):
    __tablename__ = "image_platform_usage"
    __table_args__ = (UniqueConstraint("image_id", "platform", name="uq_image_platform_usage"),)

    id = Column(String(64), primary_key=True)
    image_id = Column(String(64), ForeignKey("image_assets.id", ondelete="CASCADE"), nullable=False, index=True)
    platform = Column(String(100), nullable=False)
    usage_count = Column(Integer, default=0)
    last_used_at = Column(DateTime(timezone=True), nullable=True)


class ImageUsageRecord(Base):
    __tablename__ = "image_usage_records"
    __table_args__ = (Index("ix_usage_image_platform_created", "image_id", "platform", "created_at"),)

    id = Column(String(64), primary_key=True)
    image_id = Column(String(64), ForeignKey("image_assets.id", ondelete="CASCADE"), nullable=False, index=True)
    platform = Column(String(100), nullable=False)
    note = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(TZ))
