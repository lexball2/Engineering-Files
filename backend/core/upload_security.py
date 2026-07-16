import io
import warnings
import zipfile
from pathlib import Path

from fastapi import HTTPException, UploadFile
from PIL import Image

from backend.config import settings


CHUNK_SIZE = 1024 * 1024
IMAGE_FORMATS = {
    "JPEG": (".jpg", ".jpeg", "image/jpeg"),
    "PNG": (".png", "image/png"),
    "WEBP": (".webp", "image/webp"),
    "BMP": (".bmp", "image/bmp"),
}


async def read_upload_limited(file: UploadFile, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(min(CHUNK_SIZE, max_bytes + 1 - total))
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=413, detail=f"上传内容超过 {max_bytes // (1024 * 1024)}MB 限制")
        chunks.append(chunk)
    return b"".join(chunks)


def inspect_image_content(content: bytes, claimed_suffix: str, max_pixels: int) -> tuple[int, int, str, str]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as image:
                image.verify()
            with Image.open(io.BytesIO(content)) as image:
                width, height = image.size
                image_format = (image.format or "").upper()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="图片文件无效或像素尺寸不安全") from exc

    if width <= 0 or height <= 0 or width * height > max_pixels:
        raise HTTPException(status_code=400, detail=f"图片像素总数不能超过 {max_pixels}")
    expected = IMAGE_FORMATS.get(image_format)
    if not expected or claimed_suffix.lower() not in expected[:-1]:
        raise HTTPException(status_code=400, detail="图片扩展名与实际格式不一致")
    return width, height, image_format, expected[-1]


def validate_document_content(content: bytes, suffix: str) -> None:
    if not content:
        raise HTTPException(status_code=400, detail="文件内容为空")
    suffix = suffix.lower()
    if suffix == ".pdf" and not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="PDF 扩展名与实际内容不一致")
    if suffix in {".docx", ".xlsx", ".pptx"} and not content.startswith(b"PK"):
        raise HTTPException(status_code=400, detail="Office 文档扩展名与实际内容不一致")
    if suffix in {".docx", ".xlsx", ".pptx"}:
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                entries = archive.infolist()
                expanded_size = sum(entry.file_size for entry in entries)
                if len(entries) > 10_000 or expanded_size > settings.MAX_DOCUMENT_EXPANDED_SIZE_MB * 1024 * 1024:
                    raise HTTPException(status_code=400, detail="Office 文档解压后体积过大")
        except zipfile.BadZipFile as exc:
            raise HTTPException(status_code=400, detail="Office 文档压缩结构无效") from exc
    if suffix in {".txt", ".md"}:
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail="文本文件必须使用 UTF-8 编码") from exc


def safe_download_name(filename: str, fallback: str) -> str:
    name = Path(filename).name.strip()
    return name[:255] if name else fallback
