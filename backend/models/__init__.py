"""数据模型汇总——新增表只需在这里加一行 import"""
from backend.models.user import Base, User
from backend.models.image_asset import ImageAsset, ImageCategory, ImagePlatformUsage, ImageUsageRecord
from backend.models.document_asset import DocumentAsset

__all__ = [
    "Base",
    "User",
    "ImageAsset",
    "ImageCategory",
    "ImagePlatformUsage",
    "ImageUsageRecord",
    "DocumentAsset",
]

# 未来加：from backend.models.document import Document
# 未来加：from backend.models.category import Category
