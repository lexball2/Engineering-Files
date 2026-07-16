import hashlib
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from PIL import Image
from pydantic import BaseModel, Field
from sqlalchemy import func, text
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from backend.api.images import ALLOWED_SUFFIXES, IMAGE_DIR, MAX_IMAGE_SIZE, THUMB_DIR, _delete_image_vectors
from backend.config import settings
from backend.core.embeddings import embed_text_query
from backend.core.image_text_vector_store import get_image_text_vector_store
from backend.core.image_vector_store import get_image_vector_store
from backend.core.multimodal_embeddings import embed_image_file, embed_text_for_image_search
from backend.core.vision_understanding import generate_image_metadata
from backend.core.auth_dependencies import require_staff
from backend.core.storage import storage
from backend.core.upload_security import inspect_image_content, read_upload_limited, safe_download_name
from backend.database import SessionLocal, get_db
from backend.models.image_asset import ImageAsset, ImagePlatformUsage, ImageUsageRecord
from backend.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()

PHASH_DISTANCE_THRESHOLD = 8
IMAGE_ASSET_EXECUTOR = ThreadPoolExecutor(
    max_workers=max(1, settings.IMAGE_ASSET_WORKERS),
    thread_name_prefix="image-asset-worker",
)


class AssetSearchRequest(BaseModel):
    query: str = Field(default="", max_length=500)
    platform: str | None = Field(default=None, max_length=100)
    sort_mode: str = Field(default="recommended", pattern="^(recommended|downloads)$")
    unused_first: bool = True
    deduplicate: bool = True
    limit: int = Field(default=30, ge=1, le=100)


class AssetDownloadRequest(BaseModel):
    id: str = Field(..., min_length=8, max_length=64)
    platform: str = Field(..., min_length=1, max_length=100)
    note: str = Field(default="", max_length=1000)


class AssetIdRequest(BaseModel):
    id: str = Field(..., min_length=8, max_length=64)


class AssetIdsRequest(BaseModel):
    ids: list[str] = Field(..., min_length=1, max_length=100)


class AssetInfo(BaseModel):
    id: str
    filename: str
    width: int
    height: int
    file_size: int
    description: str = ""
    tags: str = ""
    group_id: str = ""
    current_platform_usage: int = 0
    total_download_count: int = 0
    created_at: str
    thumbnail_url: str
    view_url: str
    status: str = "ready"
    processing_error: str = ""
    score: float | None = None


class BatchUploadResponse(BaseModel):
    job_id: str
    accepted: int
    assets: list[AssetInfo]
    message: str


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _dhash(path: Path) -> str:
    with Image.open(path) as img:
        img = img.convert("L").resize((9, 8))
        pixels = list(img.getdata())
    bits = []
    for row in range(8):
        offset = row * 9
        for col in range(8):
            bits.append(1 if pixels[offset + col] > pixels[offset + col + 1] else 0)
    value = 0
    for bit in bits:
        value = (value << 1) | bit
    return f"{value:016x}"


def _hamming_hex(left: str | None, right: str | None) -> int:
    if not left or not right:
        return 64
    try:
        return (int(left, 16) ^ int(right, 16)).bit_count()
    except ValueError:
        return 64


def _save_thumbnail(source: Path, target: Path):
    with Image.open(source) as img:
        img.thumbnail((360, 360))
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
        img.save(target)


def _usage_map(db: Session, platform: str | None) -> dict[str, int]:
    if not platform:
        return {}
    rows = db.query(ImagePlatformUsage).filter(ImagePlatformUsage.platform == platform).all()
    return {row.image_id: row.usage_count or 0 for row in rows}


def _limit_tags(tags: str, limit: int = 5) -> str:
    parts = [part.strip() for part in re.split(r"[,，;；、\s]+", tags or "") if part.strip()]
    seen: set[str] = set()
    limited: list[str] = []
    for part in parts:
        key = part.lower()
        if key in seen:
            continue
        seen.add(key)
        limited.append(part)
        if len(limited) >= limit:
            break
    return ", ".join(limited)


def _merge_tags(*tag_groups: str, limit: int = 5) -> str:
    return _limit_tags(", ".join(group for group in tag_groups if group), limit=limit)


def _normalize_search_text(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").lower())


def _search_terms(query: str) -> list[str]:
    terms = [
        term.strip()
        for term in re.split(r"[,，;；、\s]+", query.strip())
        if len(term.strip()) >= 2
    ]
    if not terms and query.strip():
        terms = [query.strip()]
    return list(dict.fromkeys(terms))


def _asset_search_haystack(asset: ImageAsset) -> str:
    return _normalize_search_text(
        " ".join([
            asset.filename or "",
            asset.description or "",
            asset.tags or "",
        ])
    )


def _term_match_count(asset: ImageAsset, terms: list[str]) -> int:
    haystack = _asset_search_haystack(asset)
    return sum(1 for term in terms if _normalize_search_text(term) in haystack)


def _asset_matches_query(asset: ImageAsset, terms: list[str], score: float) -> bool:
    if not terms:
        return True

    matched_terms = _term_match_count(asset, terms)
    if matched_terms == len(terms):
        return score >= settings.IMAGE_ASSET_TEXT_SCORE_THRESHOLD or matched_terms > 0

    if matched_terms > 0:
        return len(terms) == 1 and score >= settings.IMAGE_ASSET_TEXT_SCORE_THRESHOLD

    return score >= settings.IMAGE_ASSET_SEMANTIC_SCORE_THRESHOLD


def _score_with_keyword_bonus(asset: ImageAsset, terms: list[str], base_score: float) -> float:
    if not terms:
        return base_score
    matched_terms = _term_match_count(asset, terms)
    return min(base_score + matched_terms * 0.08, 1.0)


def _to_asset_info(
    asset: ImageAsset,
    usage_by_image: dict[str, int],
    score: float | None = None,
) -> dict:
    return {
        "id": asset.id,
        "filename": asset.filename,
        "width": asset.width or 0,
        "height": asset.height or 0,
        "file_size": asset.file_size or 0,
        "description": asset.description or "",
        "tags": asset.tags or "",
        "group_id": asset.group_id or asset.id,
        "current_platform_usage": usage_by_image.get(asset.id, 0),
        "total_download_count": asset.download_count or 0,
        "created_at": asset.created_at.strftime("%Y-%m-%d %H:%M") if asset.created_at else "",
        "thumbnail_url": f"/api/images/view/{asset.id}?thumbnail=1",
        "view_url": f"/api/images/view/{asset.id}",
        "status": asset.status or "ready",
        "processing_error": asset.processing_error or "",
        "score": score,
    }


def _find_group_id(db: Session, content_hash: str, perceptual_hash: str, fallback_id: str) -> str:
    exact = db.query(ImageAsset).filter(ImageAsset.content_hash == content_hash).first()
    if exact:
        return exact.group_id or exact.id

    closest = db.execute(
        text("""
            SELECT id, group_id,
                   BIT_COUNT(
                       CAST(CONV(perceptual_hash, 16, 10) AS UNSIGNED) ^
                       CAST(CONV(:perceptual_hash, 16, 10) AS UNSIGNED)
                   ) AS distance
            FROM image_assets
            WHERE perceptual_hash IS NOT NULL
            ORDER BY distance ASC
            LIMIT 1
        """),
        {"perceptual_hash": perceptual_hash},
    ).mappings().first()

    if closest and int(closest["distance"]) <= PHASH_DISTANCE_THRESHOLD:
        return closest["group_id"] or closest["id"]
    return fallback_id


def _vector_metadata(asset: ImageAsset) -> dict:
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


def _upsert_asset_vectors(asset: ImageAsset, file_path: str):
    try:
        visual_vector = embed_image_file(file_path)
        get_image_vector_store().upsert_image(visual_vector, _vector_metadata(asset))

        text_content = _text_index_content(asset)
        if text_content.strip():
            text_vector = embed_text_query(text_content)
            get_image_text_vector_store().upsert_text(text_vector, _vector_metadata(asset))
    except Exception:
        _delete_image_vectors(asset.id)
        raise


def _process_asset_job(image_id: str) -> None:
    db = SessionLocal()
    try:
        claimed = db.query(ImageAsset).filter(ImageAsset.id == image_id, ImageAsset.status == "queued").update(
            {ImageAsset.status: "processing", ImageAsset.processing_error: ""},
            synchronize_session=False,
        )
        db.commit()
        if claimed == 0:
            return

        asset = db.query(ImageAsset).filter(ImageAsset.id == image_id).first()
        if not asset:
            return

        suffix = Path(asset.stored_name).suffix.lower()
        with storage.local_file(asset.file_path, suffix=suffix) as local_path:
            metadata = generate_image_metadata(str(local_path))
            asset.description = metadata.get("caption", "") or asset.description or ""
            asset.tags = _merge_tags(asset.tags or "", ", ".join(metadata.get("tags", [])))
            db.commit()
            _upsert_asset_vectors(asset, str(local_path))

        asset.status = "ready"
        asset.processing_error = ""
        db.commit()
    except Exception as exc:
        logger.error("Image asset background processing failed for %s: %s", image_id, exc, exc_info=True)
        db.rollback()
        try:
            failed = db.query(ImageAsset).filter(ImageAsset.id == image_id).first()
            if failed:
                _delete_image_vectors(image_id)
                failed.status = "failed"
                failed.processing_error = str(exc)[:1000]
                db.commit()
        except Exception:
            db.rollback()
            logger.exception("Failed to mark image asset as failed: %s", image_id)
    finally:
        db.close()


def _enqueue_asset_processing(image_id: str) -> None:
    IMAGE_ASSET_EXECUTOR.submit(_process_asset_job, image_id)


def requeue_unfinished_image_assets(limit: int = 200) -> int:
    db = SessionLocal()
    try:
        db.query(ImageAsset).filter(ImageAsset.status == "processing").update(
            {ImageAsset.status: "queued"},
            synchronize_session=False,
        )
        db.commit()
        ids = [
            row[0]
            for row in db.query(ImageAsset.id)
            .filter(ImageAsset.status == "queued")
            .order_by(ImageAsset.created_at.asc())
            .limit(limit)
            .all()
        ]
    finally:
        db.close()

    for image_id in ids:
        _enqueue_asset_processing(image_id)
    return len(ids)


def _merge_retrieval_scores(visual_hits: list[dict], text_hits: list[dict]) -> dict[str, float]:
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


def _rank_assets(
    assets: list[ImageAsset],
    usage_by_image: dict[str, int],
    scores: dict[str, float],
    unused_first: bool,
    sort_mode: str = "recommended",
) -> list[ImageAsset]:
    if sort_mode == "downloads":
        return sorted(
            assets,
            key=lambda asset: (
                asset.download_count or 0,
                scores.get(asset.id, 0.0),
                asset.last_downloaded_at.timestamp() if asset.last_downloaded_at else 0,
                asset.created_at.timestamp() if asset.created_at else 0,
            ),
            reverse=True,
        )

    def key(asset: ImageAsset):
        platform_count = usage_by_image.get(asset.id, 0)
        unused = 1 if platform_count == 0 else 0
        created_ts = asset.created_at.timestamp() if asset.created_at else datetime.now().timestamp()
        score = scores.get(asset.id, 0.0)
        if unused_first:
            return (unused, -platform_count, -(asset.download_count or 0), -created_ts, score)
        return (score, unused, -platform_count, -(asset.download_count or 0), -created_ts)

    return sorted(assets, key=key, reverse=True)


@router.get("/image-assets/platforms")
def list_platforms(db: Session = Depends(get_db), _current_user: User = Depends(require_staff)):
    rows = db.query(ImagePlatformUsage.platform).group_by(ImagePlatformUsage.platform).order_by(ImagePlatformUsage.platform.asc()).all()
    defaults = ["小红书", "抖音", "微信公众号", "视频号", "B站", "快手", "今日头条", "微博"]
    existing = [row[0] for row in rows if row[0]]
    return list(dict.fromkeys(defaults + existing))


@router.post("/image-assets/upload-batch", response_model=BatchUploadResponse)
async def upload_batch(
    files: list[UploadFile] = File(...),
    tags: str = Form(default=""),
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_staff),
):
    if not files:
        raise HTTPException(status_code=400, detail="至少需要上传一张图片")
    if len(files) > settings.MAX_BATCH_FILES:
        raise HTTPException(status_code=413, detail=f"单次最多上传 {settings.MAX_BATCH_FILES} 张图片")

    prepared = []
    total_size = 0
    max_batch_bytes = settings.MAX_BATCH_SIZE_MB * 1024 * 1024
    for file in files:
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            raise HTTPException(status_code=400, detail=f"{file.filename} 不是支持的图片格式")
        content = await read_upload_limited(file, MAX_IMAGE_SIZE)
        total_size += len(content)
        if total_size > max_batch_bytes:
            raise HTTPException(status_code=413, detail=f"批量文件总大小不能超过 {settings.MAX_BATCH_SIZE_MB}MB")
        width, height, _image_format, detected_mime = inspect_image_content(
            content, suffix, settings.MAX_IMAGE_PIXELS
        )
        prepared.append((file, suffix, content, width, height, detected_mime))

    manual_tags = _limit_tags(tags)
    usage_by_image: dict[str, int] = {}
    uploaded_assets: list[ImageAsset] = []
    created_paths: list[Path] = []
    storage_locations: list[str] = []
    job_id = str(uuid4())

    try:
        for file, suffix, content, width, height, detected_mime in prepared:
            image_id = str(uuid4())
            stored_name = f"{image_id}{suffix}"
            file_path = IMAGE_DIR / f"asset_tmp_{stored_name}"
            thumb_path = THUMB_DIR / f"asset_tmp_{stored_name}"
            file_path.write_bytes(content)
            created_paths.extend((file_path, thumb_path))

            await run_in_threadpool(_save_thumbnail, file_path, thumb_path)
            content_hash = _sha256(content)
            perceptual_hash = await run_in_threadpool(_dhash, file_path)
            group_id = _find_group_id(db, content_hash, perceptual_hash, image_id)

            original_location = await run_in_threadpool(storage.put_bytes, f"images/{stored_name}", content, detected_mime)
            thumb_location = await run_in_threadpool(
                storage.put_bytes,
                f"images/thumbnails/{stored_name}",
                thumb_path.read_bytes(),
                detected_mime,
            )
            storage_locations.extend((original_location, thumb_location))
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
                description="",
                tags=manual_tags,
                content_hash=content_hash,
                perceptual_hash=perceptual_hash,
                group_id=group_id,
                status="queued",
                processing_error="",
            )
            db.add(asset)
            db.flush()
            uploaded_assets.append(asset)

        db.commit()
        for asset in uploaded_assets:
            db.refresh(asset)
        for path in created_paths:
            path.unlink(missing_ok=True)
    except Exception as exc:
        db.rollback()
        for location in storage_locations:
            try:
                storage.delete(location)
            except Exception:
                logger.exception("Failed to delete storage object during rollback: %s", location)
        for path in created_paths:
            path.unlink(missing_ok=True)
        logger.error("Batch image upload failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="批量图片保存失败，已回滚本次上传") from exc

    for asset in uploaded_assets:
        _enqueue_asset_processing(asset.id)

    return BatchUploadResponse(
        job_id=job_id,
        accepted=len(uploaded_assets),
        assets=[_to_asset_info(asset, usage_by_image) for asset in uploaded_assets],
        message="图片已保存并加入后台处理队列",
    )


@router.post("/image-assets/batch-status", response_model=list[AssetInfo])
def batch_status(req: AssetIdsRequest, db: Session = Depends(get_db), _current_user: User = Depends(require_staff)):
    unique_ids = list(dict.fromkeys(req.ids))
    assets = db.query(ImageAsset).filter(ImageAsset.id.in_(unique_ids)).all()
    asset_map = {asset.id: asset for asset in assets}
    return [_to_asset_info(asset_map[image_id], {}) for image_id in unique_ids if image_id in asset_map]


@router.post("/image-assets/search", response_model=list[AssetInfo])
def search_assets(req: AssetSearchRequest, db: Session = Depends(get_db), _current_user: User = Depends(require_staff)):
    limit = max(1, min(req.limit, 100))
    usage_by_image = _usage_map(db, req.platform)
    scores: dict[str, float] = {}
    terms: list[str] = []

    if req.query.strip():
        query_text = req.query.strip()
        terms = _search_terms(query_text)
        visual_vector = embed_text_for_image_search(query_text)
        text_vector = embed_text_query(query_text)
        visual_hits = get_image_vector_store().search(visual_vector, limit=max(limit * 5, 50))
        text_hits = get_image_text_vector_store().search(text_vector, limit=max(limit * 5, 50))
        scores = _merge_retrieval_scores(visual_hits, text_hits)
        ids = list(scores.keys())
        if not ids:
            return []
        query = db.query(ImageAsset).filter(ImageAsset.id.in_(ids), ImageAsset.status == "ready")
    else:
        query = db.query(ImageAsset).filter(ImageAsset.status == "ready")

    if not req.query.strip():
        query = query.order_by(ImageAsset.last_used_at.asc(), ImageAsset.created_at.asc()).limit(limit * 10)
    assets = [asset for asset in query.all() if storage.exists(asset.file_path)]

    if req.query.strip():
        boosted_scores = {
            asset.id: _score_with_keyword_bonus(asset, terms, scores.get(asset.id, 0.0))
            for asset in assets
        }
        assets = [asset for asset in assets if _asset_matches_query(asset, terms, boosted_scores.get(asset.id, 0.0))]
        scores = boosted_scores

    ranked = _rank_assets(
        assets,
        usage_by_image,
        scores,
        req.unused_first and not req.query.strip(),
        req.sort_mode,
    )
    if req.deduplicate:
        seen_groups = set()
        deduped = []
        for asset in ranked:
            group = asset.group_id or asset.id
            if group in seen_groups:
                continue
            seen_groups.add(group)
            deduped.append(asset)
        ranked = deduped

    return [_to_asset_info(asset, usage_by_image, score=scores.get(asset.id)) for asset in ranked[:limit]]


def _record_completed_asset_download(image_id: str, platform: str, note: str) -> None:
    db = SessionLocal()
    try:
        asset = db.query(ImageAsset).filter(ImageAsset.id == image_id).first()
        if not asset:
            return

        now = datetime.now()
        usage_insert = mysql_insert(ImagePlatformUsage).values(
            id=str(uuid4()),
            image_id=image_id,
            platform=platform,
            usage_count=1,
            last_used_at=now,
        )
        db.execute(usage_insert.on_duplicate_key_update(
            usage_count=ImagePlatformUsage.usage_count + 1,
            last_used_at=now,
        ))
        db.add(ImageUsageRecord(id=str(uuid4()), image_id=image_id, platform=platform, note=note))
        db.query(ImageAsset).filter(ImageAsset.id == image_id).update(
            {
                ImageAsset.download_count: func.coalesce(ImageAsset.download_count, 0) + 1,
                ImageAsset.last_downloaded_at: now,
                ImageAsset.last_used_at: now,
            },
            synchronize_session=False,
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to record completed image asset download image_id=%s", image_id)
    finally:
        db.close()


@router.post("/image-assets/download")
def download_asset(req: AssetDownloadRequest, db: Session = Depends(get_db), _current_user: User = Depends(require_staff)):
    platform = req.platform.strip()
    if not platform:
        raise HTTPException(status_code=400, detail="下载前必须填写新媒体平台用途")

    asset = db.query(ImageAsset).filter(ImageAsset.id == req.id, ImageAsset.status == "ready").first()
    if not asset or not storage.exists(asset.file_path):
        raise HTTPException(status_code=404, detail="图片不存在")

    return storage.response(
        asset.file_path,
        filename=safe_download_name(asset.filename, asset.stored_name),
        media_type=asset.mime_type or "application/octet-stream",
        background=BackgroundTask(_record_completed_asset_download, asset.id, platform, req.note.strip()),
    )


def _delete_asset(asset: ImageAsset, strict_vectors: bool = False) -> None:
    _delete_image_vectors(asset.id, strict=strict_vectors)
    storage.delete(asset.file_path)
    storage.delete(asset.thumbnail_path)


@router.post("/image-assets/delete")
def delete_asset(req: AssetIdRequest, db: Session = Depends(get_db), _current_user: User = Depends(require_staff)):
    asset = db.query(ImageAsset).filter(ImageAsset.id == req.id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="图片不存在")
    try:
        _delete_asset(asset, strict_vectors=asset.status == "ready")
        db.delete(asset)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("Image asset deletion failed for %s: %s", req.id, exc, exc_info=True)
        raise HTTPException(status_code=503, detail="图片删除未完成，请稍后重试") from exc
    return {"ok": True, "id": req.id}


@router.post("/image-assets/delete-batch")
def delete_assets(req: AssetIdsRequest, db: Session = Depends(get_db), _current_user: User = Depends(require_staff)):
    unique_ids = list(dict.fromkeys(req.ids))
    assets = db.query(ImageAsset).filter(ImageAsset.id.in_(unique_ids)).all()
    if not assets:
        raise HTTPException(status_code=404, detail="没有找到可删除的图片")

    failed: list[str] = []
    deleted: list[str] = []
    for asset in assets:
        try:
            _delete_asset(asset, strict_vectors=asset.status == "ready")
            db.delete(asset)
            deleted.append(asset.id)
        except Exception:
            failed.append(asset.id)
            logger.exception("Image asset batch deletion failed for %s", asset.id)
    if failed:
        db.rollback()
        raise HTTPException(status_code=503, detail=f"有 {len(failed)} 张图片删除失败，请稍后重试")
    db.commit()
    return {"ok": True, "deleted": deleted}


@router.get("/image-assets/duplicates/{image_id}", response_model=list[AssetInfo])
def list_duplicates(image_id: str, db: Session = Depends(get_db), _current_user: User = Depends(require_staff)):
    asset = db.query(ImageAsset).filter(ImageAsset.id == image_id, ImageAsset.status == "ready").first()
    if not asset:
        raise HTTPException(status_code=404, detail="图片不存在")
    group = asset.group_id or asset.id
    assets = db.query(ImageAsset).filter(ImageAsset.group_id == group, ImageAsset.status == "ready").order_by(ImageAsset.created_at.asc()).all()
    return [_to_asset_info(item, {}) for item in assets if storage.exists(item.file_path)]
