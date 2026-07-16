from datetime import datetime, timedelta, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text

from backend.models.user import Base


TZ = timezone(timedelta(hours=8))


class DocumentAsset(Base):
    __tablename__ = "document_assets"

    id = Column(String(64), primary_key=True)
    filename = Column(String(255), nullable=False)
    stored_name = Column(String(255), nullable=False, unique=True)
    file_path = Column(String(500), nullable=False)
    file_type = Column(String(20), nullable=False)
    file_size = Column(Integer, default=0, nullable=False)
    status = Column(String(20), default="processing", nullable=False, index=True)
    chunks = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, default="")
    owner_id = Column(Integer, nullable=True, index=True)
    department = Column(String(50), default="", index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(TZ), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(TZ), onupdate=lambda: datetime.now(TZ))
