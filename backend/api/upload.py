"""文件上传接口——接收文档 → 解析 → 切块 → 向量化 → 入库"""
import logging
import re
import tempfile
from pathlib import Path
from uuid import uuid4
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from backend.config import settings
from backend.core.classifier import classify_and_tag
from backend.core.document_loader import load_document
from backend.core.text_splitter import split_documents
from backend.core.vector_store import get_langchain_vectorstore
from backend.core.embeddings import get_embeddings
from backend.core.auth_dependencies import require_admin, require_staff
from backend.core.storage import storage
from backend.core.upload_security import read_upload_limited, safe_download_name, validate_document_content
from backend.database import get_db
from backend.models.document_asset import DocumentAsset
from backend.models.user import User
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
router = APIRouter()
UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOW_SUFFIX = {".txt", ".md", ".docx", ".pdf", ".xlsx", ".pptx"}
MAX_FILE_SIZE = settings.MAX_DOCUMENT_SIZE_MB * 1024 * 1024
SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+")

class UploadResponse(BaseModel):
    filename: str
    chunks: int
    message: str

class DocInfo(BaseModel):
    id: str
    filename: str
    file_type: str
    upload_time: str
    status: str

class DeleteRequest(BaseModel):
    id: str = Field(..., min_length=8, max_length=64, pattern=r"^[A-Za-z0-9-]+$")

class PreviewResponse(BaseModel):
    filename: str
    file_type: str
    content: str
    total_chars: int

def _sanitize_filename(filename: str | None) -> str:
    raw_name = Path(filename or "").name.strip()
    if not raw_name:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    suffix = Path(raw_name).suffix.lower()
    stem = Path(raw_name).stem.strip()
    stem = SAFE_FILENAME_RE.sub("_", stem).strip("._- ")
    if not stem:
        stem = "document"

    safe_name = f"{stem[:120]}{suffix}"
    if Path(safe_name).name != safe_name or any(part in safe_name for part in ("/", "\\")):
        raise HTTPException(status_code=400, detail="文件名不合法")
    return safe_name

def _resolve_upload_path(file_id: str) -> Path:
    if not file_id or any(part in file_id for part in ("/", "\\")):
        raise HTTPException(status_code=400, detail="文件 ID 不合法")

    root = UPLOAD_DIR.resolve()
    file_name = Path(file_id).name
    if not file_name or file_name in {".", ".."}:
        raise HTTPException(status_code=400, detail="文件 ID 不合法")

    file_path = (root / file_name).resolve()
    if root != file_path and root not in file_path.parents:
        raise HTTPException(status_code=400, detail="文件路径不合法")
    return file_path


def _get_document(db: Session, document_id: str) -> DocumentAsset:
    document = db.query(DocumentAsset).filter(DocumentAsset.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="文件不存在")
    return document

@router.post("/upload", response_model=UploadResponse, summary="上传知识文档")
async def upload(
    file: UploadFile = File(..., description="文档文件，支持 txt/docx/pdf/xlsx/pptx/md"),
    _current_user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    temp_path: Path | None = None
    storage_location: str | None = None
    document: DocumentAsset | None = None
    try:
        original_name = _sanitize_filename(file.filename)
        suffix = Path(original_name).suffix.lower()
        if suffix not in ALLOW_SUFFIX:
            raise HTTPException(status_code=400, detail=f"不支持的文件格式，仅允许：{ALLOW_SUFFIX}")
        content = await read_upload_limited(file, MAX_FILE_SIZE)
        validate_document_content(content, suffix)
        document_id = str(uuid4())
        safe_name = f"{document_id}_{original_name}"

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
            handle.write(content)
            temp_path = Path(handle.name)

        storage_key = f"uploads/{safe_name}"
        storage_location = await run_in_threadpool(
            storage.put_bytes,
            storage_key,
            content,
            "application/octet-stream",
        )
        document = DocumentAsset(
            id=document_id,
            filename=original_name,
            stored_name=safe_name,
            file_path=storage_location,
            file_type=suffix.lstrip("."),
            file_size=len(content),
            status="processing",
            owner_id=_current_user.id,
            department=_current_user.department or "",
        )
        db.add(document)
        db.commit()
        logger.info(f"收到文件: {original_name} 保存为{safe_name} ({len(content)} bytes)")
        docs = await run_in_threadpool(load_document, str(temp_path))
        logger.info(f"解析完成: {len(docs)} 段")
        if not docs:
            raise HTTPException(status_code=400, detail="文档内未识别到有效文本")
        if sum(len(doc.page_content) for doc in docs) > settings.MAX_DOCUMENT_TEXT_CHARS:
            raise HTTPException(status_code=400, detail="文档解析后的文本内容过大")
        category = await run_in_threadpool(classify_and_tag, docs)
        logger.info(f"自动分类: {category}")
        chunks = await run_in_threadpool(split_documents, docs)
        for chunk in chunks:
            chunk.metadata["source"] = storage_location
            chunk.metadata["category"] = category
            chunk.metadata["owner_id"] = _current_user.id
            chunk.metadata["department"] = _current_user.department or ""
        embeddings = get_embeddings()
        vectorstore = get_langchain_vectorstore(embeddings)
        for chunk in chunks:
            chunk.metadata.pop("category", None)
        await run_in_threadpool(vectorstore.add_documents, chunks)
        document.status = "ready"
        document.chunks = len(chunks)
        db.commit()
        if temp_path:
            temp_path.unlink(missing_ok=True)
        return UploadResponse(filename=original_name, chunks=len(chunks), message="上传成功，文档已入库")
    except HTTPException as he:
        db.rollback()
        if storage_location:
            try:
                get_langchain_vectorstore(get_embeddings()).delete_by_source(storage_location)
            except Exception:
                logger.exception("清理失败文档向量时出错: %s", storage_location)
            try:
                storage.delete(storage_location)
            except Exception:
                logger.exception("清理失败文档存储对象时出错: %s", storage_location)
        if temp_path:
            temp_path.unlink(missing_ok=True)
        if document:
            persisted = db.query(DocumentAsset).filter(DocumentAsset.id == document.id).first()
            if persisted:
                db.delete(persisted)
                db.commit()
        raise he
    except Exception as e:
        db.rollback()
        if storage_location:
            try:
                get_langchain_vectorstore(get_embeddings()).delete_by_source(storage_location)
            except Exception:
                logger.exception("清理失败文档向量时出错: %s", storage_location)
            try:
                storage.delete(storage_location)
            except Exception:
                logger.exception("清理失败文档存储对象时出错: %s", storage_location)
        if temp_path:
            temp_path.unlink(missing_ok=True)
        if document:
            persisted = db.query(DocumentAsset).filter(DocumentAsset.id == document.id).first()
            if persisted:
                db.delete(persisted)
                db.commit()
        logger.error(f"文件上传失败：{str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="文档处理失败，请检查文件格式或稍后重试")

@router.post("/upload/list", response_model=list[DocInfo], summary="获取上传文档列表")
def list_uploads(limit: int = 100, offset: int = 0, db: Session = Depends(get_db), _current_user: User = Depends(require_staff)):
    records = (
        db.query(DocumentAsset)
        .order_by(DocumentAsset.created_at.desc())
        .offset(max(0, offset))
        .limit(max(1, min(limit, 100)))
        .all()
    )
    return [
        DocInfo(
            id=item.id,
            filename=item.filename,
            file_type=item.file_type,
            upload_time=item.created_at.strftime("%Y-%m-%d %H:%M") if item.created_at else "",
            status="indexed" if item.status == "ready" else item.status,
        )
        for item in records
        if storage.exists(item.file_path)
    ]

@router.post("/upload/download", summary="下载原始文件")
def download_file(req: DeleteRequest, db: Session = Depends(get_db), _current_user: User = Depends(require_staff)):
    """下载已上传的原始文件"""
    document = _get_document(db, req.id)
    if not storage.exists(document.file_path):
        raise HTTPException(status_code=404, detail="文件不存在")
    # 返回原始文件名（去掉 UUID 前缀）
    original_name = safe_download_name(document.filename, document.stored_name)
    return storage.response(document.file_path, filename=original_name, media_type="application/octet-stream")

@router.post("/upload/preview", response_model=PreviewResponse, summary="预览文件内容")
def preview_file(req: DeleteRequest, db: Session = Depends(get_db), _current_user: User = Depends(require_staff)):
    """返回文件前 2000 字的文本内容"""
    document = _get_document(db, req.id)
    if not storage.exists(document.file_path):
        raise HTTPException(status_code=404, detail="文件不存在")
    suffix = Path(document.stored_name).suffix.lower()
    original_name = document.filename

    if suffix in {".txt", ".md"}:
        text = storage.get_bytes(document.file_path).decode("utf-8", errors="replace")
    else:
        try:
            with storage.local_file(document.file_path, suffix=suffix) as local_path:
                docs = load_document(str(local_path))
            text = "\n\n".join(d.page_content for d in docs)
        except Exception as e:
            logger.warning(f"预览解析失败: {e}")
            raise HTTPException(status_code=400, detail="该文件格式不支持预览，请下载查看")

    preview = text[:2000]
    return PreviewResponse(
        filename=original_name,
        file_type=suffix.lstrip("."),
        content=preview,
        total_chars=len(text),
    )

@router.post("/upload/delete", summary="删除文件及向量")
def delete_file(req: DeleteRequest, db: Session = Depends(get_db), _current_user: User = Depends(require_admin)):
    """删除磁盘文件和对应的 Milvus 向量数据"""
    document = _get_document(db, req.id)
    if not storage.exists(document.file_path):
        raise HTTPException(status_code=404, detail="文件不存在")

    # 1. 删向量
    embeddings = get_embeddings()
    vs = get_langchain_vectorstore(embeddings)
    deleted_count = vs.delete_by_source(document.file_path)

    # 2. 删文件
    try:
        storage.delete(document.file_path)
    except Exception as e:
        logger.error(f"删除文件失败: {e}")
        raise HTTPException(status_code=503, detail="向量已删除，但原始文件删除失败，请重试") from e

    db.delete(document)
    db.commit()
    return {"ok": True, "deleted_chunks": deleted_count, "filename": document.filename}
