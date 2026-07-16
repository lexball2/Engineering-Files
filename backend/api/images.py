import logging
import re
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from PIL import Image
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from backend.config import settings
from backend.core.embeddings import embed_text_query
from backend.core.image_text_vector_store import get_image_text_vector_store
from backend.core.image_vector_store import get_image_vector_store
from backend.core.multimodal_embeddings import embed_image_file, embed_text_for_image_search
from backend.core.vision_understanding import generate_image_metadata, understand_image
from backend.core.auth_dependencies import get_current_user, require_admin, require_staff
from backend.core.storage import storage
from backend.core.upload_security import inspect_image_content, read_upload_limited, safe_download_name
from backend.database import SessionLocal, get_db
from backend.models.image_asset import ImageAsset
from backend.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()

IMAGE_DIR = Path("data/images")
THUMB_DIR = IMAGE_DIR / "thumbnails"
IMAGE_DIR.mkdir(parents=True, exist_ok=True)
THUMB_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
MAX_IMAGE_SIZE = settings.MAX_IMAGE_SIZE_MB * 1024 * 1024


class ImageIdRequest(BaseModel):
    id: str = Field(..., min_length=8, max_length=64, pattern=r"^[A-Za-z0-9-]+$")


class ImageSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    limit: int = Field(default=6, ge=1, le=20)


class ImageInfo(BaseModel):
    id: str
    filename: str
    width: int
    height: int
    file_size: int
    description: str = ""
    tags: str = ""
    download_count: int
    hot_score: float
    created_at: str
    thumbnail_url: str
    view_url: str
    score: float | None = None


class ImageUnderstandingResponse(BaseModel):
    answer: str


def _to_info(asset: ImageAsset, score: float | None = None) -> dict:
    hot_score = float(asset.download_count or 0)
    if score is not None:
        hot_score += score * 0.2
    return {
        "id": asset.id,
        "filename": asset.filename,
        "width": asset.width or 0,
        "height": asset.height or 0,
        "file_size": asset.file_size or 0,
        "description": asset.description or "",
        "tags": asset.tags or "",
        "download_count": asset.download_count or 0,
        "hot_score": round(hot_score, 4),
        "created_at": asset.created_at.strftime("%Y-%m-%d %H:%M") if asset.created_at else "",
        "thumbnail_url": f"/api/images/view/{asset.id}?thumbnail=1",
        "view_url": f"/api/images/view/{asset.id}",
        "score": score,
    }


def _save_thumbnail(source: Path, target: Path):
    with Image.open(source) as img:
        img.thumbnail((360, 360))
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
        img.save(target)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", text.lower())


def _query_terms(query: str) -> list[str]:
    cleaned = query.lower()
    generic_words = [
        "图片",
        "照片",
        "图像",
        "截图",
        "配图",
        "相关",
        "相似",
        "类似",
        "找",
        "搜",
        "搜索",
        "返回",
        "展示",
        "推荐",
        "几张",
        "一些",
        "有没有",
        "给我",
        "image",
        "photo",
        "picture",
        "related",
        "similar",
        "find",
        "search",
        "show",
        "recommend",
    ]
    for word in generic_words:
        cleaned = cleaned.replace(word, " ")
    terms = [term for term in re.findall(r"[\u4e00-\u9fffA-Za-z0-9_\-]+", cleaned) if len(term) >= 2]
    compact = _normalize_text(cleaned)
    if compact and len(compact) >= 2:
        terms.append(compact)
    return list(dict.fromkeys(terms))


def _metadata_bonus(query: str, asset: ImageAsset) -> float:
    haystack = _normalize_text(" ".join([asset.filename or "", asset.description or "", asset.tags or ""]))
    if not haystack:
        return 0
    bonus = 0.0
    for term in _query_terms(query):
        if _normalize_text(term) in haystack:
            bonus += 0.08
    return min(bonus, 0.24)


def _build_vector_metadata(asset: ImageAsset) -> dict:
    return {
        "image_id": asset.id,
        "filename": asset.filename,
        "file_path": asset.file_path,
        "thumbnail_url": f"/api/images/view/{asset.id}?thumbnail=1",
        "view_url": f"/api/images/view/{asset.id}",
        "description": asset.description or "",
        "tags": asset.tags or "",
        "download_count": asset.download_count or 0,
    }


def _text_index_content(asset: ImageAsset) -> str:
    return "\n".join(
        item
        for item in [
            f"文件名：{asset.filename}",
            f"描述：{asset.description or ''}",
            f"标签：{asset.tags or ''}",
        ]
        if item.strip()
    )


def _delete_image_vectors(image_id: str, strict: bool = False) -> None:
    errors = []
    for factory, method_name in (
        (get_image_vector_store, "delete_image"),
        (get_image_text_vector_store, "delete_text"),
    ):
        try:
            getattr(factory(), method_name)(image_id)
        except Exception as exc:
            errors.append(exc)
            logger.exception("Failed to delete vector %s for image_id=%s", method_name, image_id)
    if strict and errors:
        raise RuntimeError("one or more image vectors could not be deleted") from errors[0]


def _upsert_image_vectors(asset: ImageAsset, file_path: str):
    try:
        visual_store = get_image_vector_store()
        visual_vector = embed_image_file(file_path)
        visual_store.upsert_image(visual_vector, _build_vector_metadata(asset))
        text_content = _text_index_content(asset)
        if text_content.strip():
            text_store = get_image_text_vector_store()
            text_vector = embed_text_query(text_content)
            text_store.upsert_text(text_vector, _build_vector_metadata(asset))
    except Exception:
        _delete_image_vectors(asset.id)
        raise


def _merge_scores(visual_hits: list[dict], text_hits: list[dict]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for hit in visual_hits:
        image_id = hit.get("image_id")
        if image_id:
            scores[image_id] = scores.get(image_id, 0.0) + float(hit.get("score") or 0) * 0.35
    for hit in text_hits:
        image_id = hit.get("image_id")
        if image_id:
            scores[image_id] = scores.get(image_id, 0.0) + float(hit.get("score") or 0) * 0.65
    return scores


def _search_by_vector(vector: list[float], db: Session, limit: int, query: str = "") -> list[dict]:
    hits = get_image_vector_store().search(vector, limit=max(limit * 3, limit))
    ids = [hit["image_id"] for hit in hits if hit.get("image_id")]
    if not ids:
        return []

    assets = db.query(ImageAsset).filter(ImageAsset.id.in_(ids), ImageAsset.status == "ready").all()
    asset_map = {asset.id: asset for asset in assets}
    results = []
    for hit in hits:
        asset = asset_map.get(hit.get("image_id"))
        if not asset or not storage.exists(asset.file_path):
            continue
        base_score = float(hit.get("score") or 0)
        score = base_score + _metadata_bonus(query, asset)
        if score < settings.IMAGE_SEARCH_SCORE_THRESHOLD:
            continue
        results.append(_to_info(asset, score=round(score, 4)))
    return sorted(results, key=lambda item: (item.get("score") or 0, item.get("hot_score") or 0), reverse=True)[:limit]


def search_images_by_text(query: str, db: Session, limit: int = 6) -> list[dict]:
    visual_vector = embed_text_for_image_search(query)
    text_vector = embed_text_query(query)
    visual_hits = get_image_vector_store().search(visual_vector, limit=max(limit * 3, limit))
    text_hits = get_image_text_vector_store().search(text_vector, limit=max(limit * 3, limit))
    scores = _merge_scores(visual_hits, text_hits)
    if not scores:
        return []

    assets = db.query(ImageAsset).filter(ImageAsset.id.in_(scores.keys()), ImageAsset.status == "ready").all()
    results = []
    for asset in assets:
        if not storage.exists(asset.file_path):
            continue
        score = scores.get(asset.id, 0) + _metadata_bonus(query, asset)
        if score < settings.IMAGE_SEARCH_SCORE_THRESHOLD:
            continue
        results.append(_to_info(asset, score=round(score, 4)))
    return sorted(results, key=lambda item: (item.get("score") or 0, item.get("hot_score") or 0), reverse=True)[:limit]


def is_image_request(text: str) -> bool:
    lowered = text.lower().strip()
    image_terms = ["图片", "照片", "图像", "截图", "配图", "image", "photo", "picture"]
    if not any(term in lowered for term in image_terms):
        return False

    retrieval_terms = [
        "找",
        "搜",
        "搜索",
        "查找",
        "返回",
        "展示",
        "推荐",
        "配",
        "给我",
        "有没有",
        "相关",
        "相似",
        "类似",
        "find",
        "search",
        "show",
        "recommend",
        "related",
        "similar",
    ]
    discussion_terms = [
        "上传",
        "识别",
        "逻辑",
        "接口",
        "功能",
        "失败",
        "报错",
        "调用",
        "为什么",
        "怎么",
        "如何",
        "解决",
        "实现",
        "修改",
        "测试",
        "模板",
        "download",
        "upload",
        "api",
        "error",
        "bug",
    ]
    has_retrieval = any(term in lowered for term in retrieval_terms)
    has_discussion = any(term in lowered for term in discussion_terms)
    if has_retrieval:
        return True
    if has_discussion:
        return False

    cleaned = lowered
    for term in image_terms + ["相关", "的", "一张", "几张", "一些"]:
        cleaned = cleaned.replace(term, "")
    return len(cleaned.strip()) >= 2 and len(lowered) <= 30


@router.post("/images/upload", response_model=ImageInfo, summary="Upload image")
async def upload_image(
    file: UploadFile = File(...),
    description: str = Form(default=""),
    tags: str = Form(default=""),
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_staff),
):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=400, detail="Unsupported image format")

    content = await read_upload_limited(file, MAX_IMAGE_SIZE)
    width, height, _image_format, detected_mime = inspect_image_content(
        content, suffix, settings.MAX_IMAGE_PIXELS
    )

    image_id = str(uuid4())
    stored_name = f"{image_id}{suffix}"
    file_path = IMAGE_DIR / f"tmp_{stored_name}"
    thumb_path = THUMB_DIR / f"tmp_{stored_name}"
    original_location: str | None = None
    thumb_location: str | None = None
    file_path.write_bytes(content)

    try:
        _save_thumbnail(file_path, thumb_path)
    except Exception as exc:
        file_path.unlink(missing_ok=True)
        thumb_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Invalid image file: {exc}") from exc

    final_description = description.strip()
    final_tags = tags.strip()
    try:
        metadata = await run_in_threadpool(generate_image_metadata, str(file_path))
        if not final_description:
            final_description = metadata.get("caption", "")
        if not final_tags:
            final_tags = ", ".join(metadata.get("tags", []))
    except Exception as exc:
        logger.warning("Image metadata generation failed: %s", exc, exc_info=True)

    try:
        original_location = await run_in_threadpool(storage.put_bytes, f"images/{stored_name}", content, detected_mime)
        thumb_location = await run_in_threadpool(
            storage.put_bytes,
            f"images/thumbnails/{stored_name}",
            thumb_path.read_bytes(),
            detected_mime,
        )
    except Exception as exc:
        file_path.unlink(missing_ok=True)
        thumb_path.unlink(missing_ok=True)
        if original_location:
            try:
                storage.delete(original_location)
            except Exception:
                logger.exception("Failed to delete image object after partial upload: %s", original_location)
        raise HTTPException(status_code=503, detail="图片存储失败，请稍后重试") from exc

    asset = ImageAsset(
        id=image_id,
        filename=safe_download_name(file.filename or "", stored_name),
        stored_name=stored_name,
        file_path=original_location,
        thumbnail_path=thumb_location,
        mime_type=detected_mime,
        file_size=len(content),
        width=width,
        height=height,
        description=final_description,
        tags=final_tags,
        status="processing",
    )
    db.add(asset)

    try:
        await run_in_threadpool(_upsert_image_vectors, asset, str(file_path))
        asset.status = "ready"
        db.commit()
        db.refresh(asset)
        file_path.unlink(missing_ok=True)
        thumb_path.unlink(missing_ok=True)
    except Exception as exc:
        logger.error("Image embedding failed: %s", exc, exc_info=True)
        db.rollback()
        _delete_image_vectors(asset.id)
        if original_location:
            try:
                storage.delete(original_location)
            except Exception:
                logger.exception("Failed to delete image object during rollback: %s", original_location)
        if thumb_location:
            try:
                storage.delete(thumb_location)
            except Exception:
                logger.exception("Failed to delete thumbnail object during rollback: %s", thumb_location)
        file_path.unlink(missing_ok=True)
        thumb_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=500,
            detail="Image embedding failed; please check DashScope or Milvus configuration",
        ) from exc

    return _to_info(asset)


@router.post("/images/list", response_model=list[ImageInfo], summary="List images")
def list_images(limit: int = 100, offset: int = 0, db: Session = Depends(get_db), _current_user: User = Depends(require_staff)):
    page_size = max(1, min(limit, 100))
    page_offset = max(0, offset)
    assets = (
        db.query(ImageAsset)
        .filter(ImageAsset.status == "ready")
        .order_by(ImageAsset.created_at.desc())
        .offset(page_offset)
        .limit(page_size)
        .all()
    )
    return [_to_info(asset) for asset in assets if storage.exists(asset.file_path)]


@router.post("/images/search/text", summary="Search images by text")
def search_text(req: ImageSearchRequest, db: Session = Depends(get_db), _current_user: User = Depends(get_current_user)):
    if not req.query.strip():
        return []
    return search_images_by_text(req.query, db, limit=max(1, min(req.limit, 20)))


@router.post("/images/search/image", summary="Search images by image")
async def search_image(
    file: UploadFile = File(...),
    limit: int = Form(default=6),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=400, detail="Please upload an image file")

    tmp_path = IMAGE_DIR / f"query_{uuid4()}{suffix}"
    content = await read_upload_limited(file, MAX_IMAGE_SIZE)
    inspect_image_content(content, suffix, settings.MAX_IMAGE_PIXELS)
    tmp_path.write_bytes(content)

    try:
        vector = await run_in_threadpool(embed_image_file, str(tmp_path))
        return _search_by_vector(vector, db, limit=max(1, min(limit, 20)))
    finally:
        tmp_path.unlink(missing_ok=True)


@router.post("/images/understand", response_model=ImageUnderstandingResponse, summary="Understand uploaded image")
async def understand_uploaded_image(
    file: UploadFile = File(...),
    question: str = Form(default=""),
    _current_user: User = Depends(get_current_user),
):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=400, detail="Please upload an image file")

    tmp_path = IMAGE_DIR / f"understand_{uuid4()}{suffix}"
    content = await read_upload_limited(file, MAX_IMAGE_SIZE)
    inspect_image_content(content, suffix, settings.MAX_IMAGE_PIXELS)
    tmp_path.write_bytes(content)

    try:
        answer = await run_in_threadpool(understand_image, str(tmp_path), question)
        return ImageUnderstandingResponse(answer=answer)
    except Exception as exc:
        logger.error("Image understanding failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Image understanding failed; please check DashScope vision model configuration") from exc
    finally:
        tmp_path.unlink(missing_ok=True)


@router.get("/images/view/{image_id}", summary="View image")
def view_image(
    image_id: str,
    thumbnail: int = 0,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    asset = db.query(ImageAsset).filter(ImageAsset.id == image_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Image not found")

    location = asset.thumbnail_path if thumbnail else asset.file_path
    if not storage.exists(location):
        raise HTTPException(status_code=404, detail="Image file not found")
    return storage.response(
        location,
        filename=safe_download_name(asset.filename, asset.stored_name),
        media_type=asset.mime_type or "image/jpeg",
        headers={
            "Cache-Control": "private, max-age=300",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "inline",
        },
    )


def _record_completed_image_download(image_id: str) -> None:
    db = SessionLocal()
    try:
        db.query(ImageAsset).filter(ImageAsset.id == image_id).update(
            {
                ImageAsset.download_count: func.coalesce(ImageAsset.download_count, 0) + 1,
                ImageAsset.last_downloaded_at: datetime.now(),
            },
            synchronize_session=False,
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to record completed image download image_id=%s", image_id)
    finally:
        db.close()


@router.post("/images/download", summary="Download image and count popularity")
def download_image(req: ImageIdRequest, db: Session = Depends(get_db), _current_user: User = Depends(get_current_user)):
    asset = db.query(ImageAsset).filter(ImageAsset.id == req.id, ImageAsset.status == "ready").first()
    if not asset or not storage.exists(asset.file_path):
        raise HTTPException(status_code=404, detail="Image not found")

    return storage.response(
        asset.file_path,
        filename=safe_download_name(asset.filename, asset.stored_name),
        media_type=asset.mime_type or "application/octet-stream",
        background=BackgroundTask(_record_completed_image_download, asset.id),
    )


@router.post("/images/delete", summary="Delete image")
def delete_image(req: ImageIdRequest, db: Session = Depends(get_db), _current_user: User = Depends(require_admin)):
    asset = db.query(ImageAsset).filter(ImageAsset.id == req.id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Image not found")

    try:
        _delete_image_vectors(asset.id, strict=True)
        storage.delete(asset.file_path)
        storage.delete(asset.thumbnail_path)
        db.delete(asset)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("Image deletion failed for %s: %s", asset.id, exc, exc_info=True)
        raise HTTPException(status_code=503, detail="图片删除未完成，请稍后重试") from exc
    return {"ok": True, "id": req.id}
