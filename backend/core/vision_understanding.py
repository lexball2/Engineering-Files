import base64
import json
import mimetypes
import re
from http import HTTPStatus
from pathlib import Path
from typing import TypedDict

from dashscope import MultiModalConversation

from backend.config import settings


class ImageMetadata(TypedDict):
    caption: str
    tags: list[str]


def _image_data_uri(file_path: str) -> str:
    path = Path(file_path)
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def _extract_text(response) -> str:
    output = getattr(response, "output", None) or {}
    choices = output.get("choices") or []
    if choices:
        message = choices[0].get("message", {})
        content = message.get("content", "")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if text:
                        parts.append(str(text))
                elif isinstance(item, str):
                    parts.append(item)
            return "\n".join(parts).strip()
    text = output.get("text")
    if text:
        return str(text).strip()
    raise RuntimeError(f"Unexpected DashScope vision response: {output}")


def _call_vision(file_path: str, prompt: str) -> str:
    messages = [
        {
            "role": "user",
            "content": [
                {"image": _image_data_uri(file_path)},
                {"text": prompt},
            ],
        }
    ]
    response = MultiModalConversation.call(
        model=settings.IMAGE_UNDERSTANDING_MODEL,
        messages=messages,
        api_key=settings.DASHSCOPE_API_KEY,
        result_format="message",
        temperature=0.2,
    )
    status_code = getattr(response, "status_code", None)
    if status_code not in (HTTPStatus.OK, 200, None):
        message = getattr(response, "message", "") or getattr(response, "code", "")
        raise RuntimeError(f"DashScope vision understanding failed: {status_code} {message}")
    return _extract_text(response)


def understand_image(file_path: str, question: str = "") -> str:
    prompt = question.strip() or "请识别这张图片的主要内容，并说明它可能来自哪里。"
    return _call_vision(
        file_path,
        (
            "请直接根据图片内容回答用户问题。"
            "如果图片像某个游戏、影视、品牌或地点，请给出判断依据和不确定性。"
            f"\n用户问题：{prompt}"
        ),
    )


def generate_image_metadata(file_path: str) -> ImageMetadata:
    answer = _call_vision(
        file_path,
        (
            "请为这张图片生成用于图片库检索的元数据。"
            "只返回 JSON，不要输出 Markdown。格式："
            '{"caption":"一句话描述图片内容","tags":["标签1","标签2","标签3"]}。'
            "标签应包含主体、场景、风格、可能的游戏/影视/品牌/地点名称；不确定时不要强行写专有名词。"
        ),
    )
    match = re.search(r"\{.*\}", answer, flags=re.S)
    payload = match.group(0) if match else answer
    try:
        data = json.loads(payload)
        caption = str(data.get("caption") or "").strip()
        raw_tags = data.get("tags") or []
        tags = [str(tag).strip() for tag in raw_tags if str(tag).strip()]
        return {"caption": caption or answer.strip(), "tags": tags[:12]}
    except Exception:
        return {"caption": answer.strip(), "tags": []}
