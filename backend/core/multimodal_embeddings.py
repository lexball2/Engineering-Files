import base64
import mimetypes
from http import HTTPStatus
from pathlib import Path

from dashscope import MultiModalEmbedding

from backend.config import settings


def _extract_embedding(response) -> list[float]:
    output = getattr(response, "output", None) or {}
    embeddings = output.get("embeddings") or output.get("embedding") or []
    if isinstance(embeddings, list) and embeddings:
        first = embeddings[0]
        vector = first.get("embedding") or first.get("vector") if isinstance(first, dict) else first
    else:
        vector = output.get("vector")
    if not isinstance(vector, list):
        raise RuntimeError(f"Unexpected DashScope embedding response: {output}")
    return [float(item) for item in vector]


def _call_multimodal_embedding(items) -> list[float]:
    response = MultiModalEmbedding.call(
        model=settings.IMAGE_EMBEDDING_MODEL,
        input=items,
        api_key=settings.DASHSCOPE_API_KEY,
        dimension=settings.IMAGE_EMBEDDING_DIM,
        output_type="dense",
    )
    status_code = getattr(response, "status_code", None)
    if status_code not in (HTTPStatus.OK, 200, None):
        message = getattr(response, "message", "") or getattr(response, "code", "")
        raise RuntimeError(f"DashScope multimodal embedding failed: {status_code} {message}")
    return _extract_embedding(response)


def embed_text_for_image_search(text: str) -> list[float]:
    return _call_multimodal_embedding([{"text": text}])


def embed_image_file(file_path: str) -> list[float]:
    path = Path(file_path)
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    data_uri = f"data:{mime};base64,{data}"
    return _call_multimodal_embedding([{"image": data_uri}])
