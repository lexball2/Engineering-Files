import io

import pytest
from fastapi import HTTPException
from PIL import Image

from backend.core.upload_security import inspect_image_content, validate_document_content


def _png_bytes(size=(8, 8)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, "blue").save(buffer, format="PNG")
    return buffer.getvalue()


def test_image_format_is_detected_from_content():
    width, height, image_format, mime = inspect_image_content(_png_bytes(), ".png", 1_000)
    assert (width, height, image_format, mime) == (8, 8, "PNG", "image/png")


def test_image_extension_mismatch_is_rejected():
    with pytest.raises(HTTPException):
        inspect_image_content(_png_bytes(), ".jpg", 1_000)


def test_image_pixel_limit_is_enforced():
    with pytest.raises(HTTPException):
        inspect_image_content(_png_bytes((20, 20)), ".png", 100)


def test_document_magic_is_validated():
    validate_document_content(b"%PDF-1.7\n", ".pdf")
    with pytest.raises(HTTPException):
        validate_document_content(b"not a pdf", ".pdf")
