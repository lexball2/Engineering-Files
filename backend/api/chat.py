"""知识库问答接口——接收用户问题，返回 AI 回答"""
import logging
import json
import re
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.api.images import is_image_request, search_images_by_text
from backend.core.memory import memory
from backend.config import settings
from backend.core.rag_chain import ask, ask_general, ask_general_stream, ask_stream, extract_sources, retrieve_documents
from backend.core.auth_dependencies import get_current_user
from backend.core.document_loader import load_document
from backend.core.storage import storage
from backend.database import SessionLocal
from backend.models.document_asset import DocumentAsset
from backend.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()


def _format_image_answer(related_images: list[dict]) -> str:
    if not related_images:
        return "我在图片库里没有找到足够相关的图片。你可以换一个更具体的关键词，或先到图片库上传并标注相关图片。"

    names = []
    for image in related_images[:3]:
        filename = image.get("filename") or "未命名图片"
        tags = image.get("tags") or ""
        score = image.get("score")
        detail = filename
        if tags:
            detail += f"（标签：{tags}）"
        if isinstance(score, (int, float)):
            detail += f"，相关度 {score:.2f}"
        names.append(detail)

    intro = f"已从图片库中找到 {len(related_images)} 张相关图片，并展示在下方。"
    if names:
        intro += "\n\n优先返回的图片包括：\n" + "\n".join(f"{idx}. {name}" for idx, name in enumerate(names, 1))
    intro += "\n\n这些结果会结合图片向量相似度、自动生成的描述/标签和下载热度排序。"
    return intro


_GENERAL_CHAT_EXACT = {
    "你好", "您好", "嗨", "hi", "hello", "在吗", "谢谢", "感谢", "早上好", "下午好", "晚上好",
    "你是谁", "介绍一下你自己", "你能做什么", "你可以做什么",
}

_GENERAL_CHAT_CUES = {
    "介绍你自己", "你当前使用", "你是什么模型", "你是什么", "你能帮我", "能做什么",
    "写一段", "帮我写", "润色", "翻译", "改写", "生成文案", "头脑风暴", "讲个",
}

_KNOWLEDGE_RETRIEVAL_CUES = {
    "知识库", "文档", "文件", "资料", "报告", "说明书", "制度", "流程", "方案", "合同",
    "手册", "规范", "记录", "来源", "引用", "根据", "依据", "结合", "上传", "总结",
    "这份", "该文件", "这篇", "上述", "上面", "里面", "内容", "条款", "规定",
    "用法", "禁忌", "注意事项", "成分", "规格", "有效期", "批准文号", "生产企业",
}


def should_use_knowledge_base(question: str) -> bool:
    """判断问题是否需要检索知识库；普通闲聊和通用创作不触发文档来源。"""
    text = re.sub(r"\s+", "", question.strip().lower())
    if not text:
        return False
    stripped = text.strip("，。！？!?.,;；：:")
    if stripped in _GENERAL_CHAT_EXACT:
        return False
    if len(stripped) <= 8 and any(cue in stripped for cue in _GENERAL_CHAT_EXACT):
        return False
    if any(cue in text for cue in _KNOWLEDGE_RETRIEVAL_CUES):
        return True
    if any(cue in text for cue in _GENERAL_CHAT_CUES):
        return False
    return False


class ChatRequest(BaseModel):
    """问答请求体"""
    question: str = Field(..., min_length=1, max_length=8000, description="用户提问")
    session_id: str = Field(..., min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$", description="会话 ID，用于多轮记忆")


class ChatResponse(BaseModel):
    """问答响应体"""
    answer: str = Field(..., description="AI 回答")
    session_id: str = Field(..., description="会话 ID")
    sources: list[dict[str, str]] = Field(default_factory=list, description="本次回答参考的来源文件")
    related_images: list[dict] = Field(default_factory=list, description="本次回答相关图片")


class ChatClearRequest(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$", description="要清理的会话 ID")


class SourcePreviewRequest(BaseModel):
    source: str = Field(..., min_length=1, max_length=1024, description="来源文件标识")


class SourcePreviewResponse(BaseModel):
    filename: str
    content: str
    total_chars: int


def _memory_key(user: User, session_id: str) -> str:
    return f"{user.id}:{session_id}"


def _department_filter(user: User) -> str | None:
    if not settings.RAG_REQUIRE_DEPARTMENT_MATCH or user.role == "admin":
        return None
    department = (user.department or "").replace("\\", "\\\\").replace('"', '\\"')
    return f'department == "{department}"'


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/chat/source-preview", response_model=SourcePreviewResponse, summary="预览问答来源文档")
def preview_chat_source(req: SourcePreviewRequest, current_user: User = Depends(get_current_user)):
    db = SessionLocal()
    try:
        document = (
            db.query(DocumentAsset)
            .filter((DocumentAsset.file_path == req.source) | (DocumentAsset.filename == req.source))
            .first()
        )
        if not document:
            raise HTTPException(status_code=404, detail="来源文件不存在")
        if settings.RAG_REQUIRE_DEPARTMENT_MATCH and current_user.role != "admin":
            if (document.department or "") != (current_user.department or ""):
                raise HTTPException(status_code=403, detail="无权预览该来源文件")
        if not storage.exists(document.file_path):
            raise HTTPException(status_code=404, detail="来源文件已不存在")

        suffix = "." + (document.file_type or "").lower().lstrip(".")
        if suffix in {".txt", ".md"}:
            text = storage.get_bytes(document.file_path).decode("utf-8", errors="replace")
        else:
            with storage.local_file(document.file_path, suffix=suffix) as local_path:
                docs = load_document(str(local_path))
            text = "\n\n".join(doc.page_content for doc in docs)

        preview = text[:2000]
        return SourcePreviewResponse(
            filename=document.filename,
            content=preview,
            total_chars=len(text),
        )
    finally:
        db.close()


@router.post("/chat/clear", summary="清理会话记录")
def clear_chat(req: ChatClearRequest, current_user: User = Depends(get_current_user)):
    memory.clear(_memory_key(current_user, req.session_id))
    return {"ok": True, "session_id": req.session_id}


@router.post("/chat", response_model=ChatResponse, summary="知识库问答")
def chat(req: ChatRequest, current_user: User = Depends(get_current_user)):
    """向知识库提问（非流式），返回完整回答"""
    try:
        filter_expr = _department_filter(current_user)
        related_images = []
        if is_image_request(req.question):
            db = SessionLocal()
            try:
                related_images = search_images_by_text(req.question, db)
            except Exception as image_error:
                logger.warning(f"图片检索失败: {image_error}", exc_info=True)
            finally:
                db.close()
            return ChatResponse(
                answer=_format_image_answer(related_images),
                session_id=req.session_id,
                sources=[],
                related_images=related_images,
            )
        if not should_use_knowledge_base(req.question):
            answer = ask_general(req.question, memory_key=_memory_key(current_user, req.session_id))
            return ChatResponse(answer=answer, session_id=req.session_id, sources=[], related_images=related_images)

        retrieved_docs = retrieve_documents(req.question, filter=filter_expr)
        sources = extract_sources(retrieved_docs)
        answer = ask(
            req.question,
            memory_key=_memory_key(current_user, req.session_id),
            filter=filter_expr,
            retrieved_docs=retrieved_docs,
        )
        return ChatResponse(answer=answer, session_id=req.session_id, sources=sources, related_images=related_images)
    except Exception as e:
        logger.error(f"问答异常: {e}", exc_info=True)
        return ChatResponse(answer="抱歉，处理您的问题时出错，请稍后重试。", session_id=req.session_id)


@router.post("/chat/stream", summary="知识库问答（流式 SSE）")
def chat_stream(req: ChatRequest, current_user: User = Depends(get_current_user)):
    """向知识库提问，通过 SSE 逐 token 流式返回回答"""
    def generate():
        try:
            filter_expr = _department_filter(current_user)
            if is_image_request(req.question):
                yield _sse("sources", [])
                db = SessionLocal()
                try:
                    related_images = search_images_by_text(req.question, db)
                except Exception as image_error:
                    logger.warning(f"图片检索失败: {image_error}", exc_info=True)
                    related_images = []
                finally:
                    db.close()
                yield _sse("related_images", related_images)
                yield _sse("chunk", _format_image_answer(related_images))
                yield _sse("done", True)
                return

            if not should_use_knowledge_base(req.question):
                yield _sse("sources", [])
                for chunk in ask_general_stream(req.question, memory_key=_memory_key(current_user, req.session_id)):
                    yield _sse("chunk", chunk)
                yield _sse("done", True)
                return

            retrieved_docs = retrieve_documents(req.question, filter=filter_expr)
            sources = extract_sources(retrieved_docs)
            yield _sse("sources", sources)
            for chunk in ask_stream(
                req.question,
                memory_key=_memory_key(current_user, req.session_id),
                filter=filter_expr,
                retrieved_docs=retrieved_docs,
            ):
                yield _sse("chunk", chunk)
            yield _sse("done", True)
        except Exception as e:
            logger.error(f"流式问答异常: {e}", exc_info=True)
            yield _sse("error", "抱歉，处理您的问题时出错，请稍后重试。")
            yield _sse("done", True)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
