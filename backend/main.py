import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy import text

from backend.api.auth import router as auth_router
from backend.api.chat import router as chat_router
from backend.api.image_assets import requeue_unfinished_image_assets, router as image_assets_router
from backend.api.images import router as images_router
from backend.api.upload import router as upload_router
from backend.config import settings
from backend.core.rate_limit import request_rate_limiter
from backend.database import engine, init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title="企业智能知识库",
    version="0.1.0",
    description="基于 LangChain + Milvus + DeepSeek 的 RAG 知识库系统",
    docs_url=None if settings.ENVIRONMENT.lower() == "production" else "/docs",
    redoc_url=None if settings.ENVIRONMENT.lower() == "production" else "/redoc",
    openapi_url=None if settings.ENVIRONMENT.lower() == "production" else "/openapi.json",
)


def _validate_production_settings() -> None:
    if settings.ENVIRONMENT.lower() != "production":
        return
    problems = []
    if settings.JWT_SECRET == "your-secret-key-change-me" or len(settings.JWT_SECRET) < 32:
        problems.append("JWT_SECRET must be a random value of at least 32 characters")
    if not settings.COOKIE_SECURE:
        problems.append("COOKIE_SECURE must be true")
    if "*" in settings.cors_origins:
        problems.append("CORS_ORIGINS cannot contain '*'")
    if settings.AUTO_INIT_DB:
        problems.append("AUTO_INIT_DB must be false; run migrations before starting replicas")
    if not settings.REDIS_URL:
        problems.append("REDIS_URL is required for shared sessions and distributed rate limiting")
    if settings.MYSQL_USER.lower() == "root":
        problems.append("MYSQL_USER must be a dedicated least-privilege account")
    local_mysql_hosts = {"localhost", "127.0.0.1", "mysql"}
    if not settings.MYSQL_SSL_CA and settings.MYSQL_HOST not in local_mysql_hosts:
        problems.append("MYSQL_SSL_CA is required for verified database TLS")
    local_milvus_hosts = {"http://milvus:19530", "http://localhost:19530", "http://127.0.0.1:19530"}
    using_local_milvus = settings.milvus_uri in local_milvus_hosts
    if not settings.MILVUS_TOKEN and not using_local_milvus:
        problems.append("MILVUS_TOKEN is required")
    if not settings.milvus_uri.startswith("https://") and not using_local_milvus:
        problems.append("MILVUS_URI must use https:// in production")
    if not settings.llm_api_key or not settings.DASHSCOPE_API_KEY:
        problems.append("LLM_API_KEY and DASHSCOPE_API_KEY are required")
    if settings.STORAGE_BACKEND != "oss":
        problems.append("STORAGE_BACKEND must be oss in production")
    if not settings.OSS_BUCKET or not settings.OSS_ENDPOINT or not settings.OSS_REGION:
        problems.append("OSS_BUCKET, OSS_ENDPOINT, and OSS_REGION are required")
    if not settings.OSS_ACCESS_KEY_ID or not settings.OSS_ACCESS_KEY_SECRET:
        problems.append("OSS access keys are required")
    if problems:
        raise RuntimeError("Invalid production configuration: " + "; ".join(problems))


_validate_production_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)


@app.middleware("http")
async def security_and_rate_limit(request: Request, call_next):
    if request.url.path.startswith("/api/") and request.method != "OPTIONS":
        if not request_rate_limiter.allow(request):
            return JSONResponse(
                status_code=429,
                content={"detail": "请求过于频繁，请稍后再试"},
                headers={"Retry-After": "60"},
            )

        origin = request.headers.get("origin")
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and origin and origin not in settings.cors_origins:
            return JSONResponse(status_code=403, content={"detail": "请求来源不受信任"})

    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
        "font-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'"
    )
    if settings.COOKIE_SECURE:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

if settings.AUTO_INIT_DB:
    init_db()

app.include_router(chat_router, prefix="/api", tags=["问答"])
app.include_router(upload_router, prefix="/api", tags=["文档"])
app.include_router(images_router, prefix="/api", tags=["图片"])
app.include_router(image_assets_router, prefix="/api", tags=["图片资产"])
app.include_router(auth_router, prefix="/api", tags=["鉴权"])


@app.on_event("startup")
def resume_background_image_asset_jobs():
    requeued = requeue_unfinished_image_assets()
    if requeued:
        logging.getLogger(__name__).info("Requeued %s unfinished image asset jobs", requeued)


@app.get("/", summary="健康检查")
def root():
    return {"status": "ok", "message": "企业智能知识库后端运行中"}


@app.get("/health/live", include_in_schema=False)
def health_live():
    return {"status": "ok"}


@app.get("/health/ready", include_in_schema=False)
def health_ready():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        if settings.REDIS_URL:
            from redis import Redis

            Redis.from_url(settings.REDIS_URL, socket_timeout=2).ping()
        return {"status": "ready"}
    except Exception:
        return JSONResponse(status_code=503, content={"status": "not_ready"})
