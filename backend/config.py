"""
项目配置——所有配置项集中管理

通俗理解：这里就是你项目的"控制面板"。
以后改一个数据库地址或者换一个模型，只在这里改就行，不用满项目找。
"""
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """自动从 .env 文件加载所有配置"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",
    )

    # ===== 大模型 API =====
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DASHSCOPE_API_KEY: str = ""

    # ===== Milvus 向量数据库 =====
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: int = 19530
    MILVUS_URI: str = ""
    MILVUS_TOKEN: str = ""
    MILVUS_SERVER_PEM_PATH: str = ""
    MILVUS_COLLECTION_NAME: str = "knowledge_base"

    # ===== Embedding 模型配置 =====
    # 千问 text-embedding-v4，1024 维，中文效果好且便宜
    EMBEDDING_MODEL: str = "text-embedding-v4"
    EMBEDDING_DIM: int = 1024
    IMAGE_EMBEDDING_MODEL: str = "tongyi-embedding-vision-flash-2026-03-06"
    IMAGE_EMBEDDING_DIM: int = 768
    IMAGE_COLLECTION_NAME: str = "image_library"
    IMAGE_TEXT_COLLECTION_NAME: str = "image_text_library"
    IMAGE_TEXT_EMBEDDING_DIM: int = 1024
    IMAGE_UNDERSTANDING_MODEL: str = "qwen-vl-plus"
    IMAGE_SEARCH_SCORE_THRESHOLD: float = 0.12
    IMAGE_ASSET_TEXT_SCORE_THRESHOLD: float = 0.28
    IMAGE_ASSET_SEMANTIC_SCORE_THRESHOLD: float = 0.55
    MAX_IMAGE_SIZE_MB: int = 15
    MAX_IMAGE_PIXELS: int = 40_000_000
    MAX_BATCH_FILES: int = 20
    MAX_BATCH_SIZE_MB: int = 200
    IMAGE_ASSET_WORKERS: int = 2
    MAX_DOCUMENT_SIZE_MB: int = 20
    MAX_DOCUMENT_EXPANDED_SIZE_MB: int = 200
    MAX_DOCUMENT_TEXT_CHARS: int = 2_000_000

    # ===== LLM 对话模型 =====
    LLM_MODEL: str = "qwen3.7-plus"
    LLM_TEMPERATURE: float = 0.3

    # ===== RAG 配置 =====
    RAG_TOP_K: int = 5  # 每次检索返回条数
    RAG_SCORE_THRESHOLD: float = 0.3  # 相似度阈值（低于此值丢弃，防污染）
    MAX_CONTEXT_LENGTH: int = 4000  # 上下文最长字符数（防止超 LLM 输入上限）

    # ===== 会话记忆 =====
    MAX_HISTORY_ROUNDS: int = 6
    MAX_MEMORY_SESSIONS: int = 1000
    MEMORY_TTL_SECONDS: int = 86400
    REDIS_URL: str = ""

    # ===== MySQL =====
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = ""
    MYSQL_DATABASE: str = "knowledge_base"
    MYSQL_POOL_SIZE: int = 5
    MYSQL_MAX_OVERFLOW: int = 10
    MYSQL_SSL_CA: str = ""

    # ===== JWT 鉴权 =====
    JWT_SECRET: str = "your-secret-key-change-me"   # 生产环境换成长随机串
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 1
    JWT_ISSUER: str = "engineering-files-api"
    JWT_AUDIENCE: str = "engineering-files-web"
    RATE_LIMIT_PER_MINUTE: int = 10        # 每分钟每 IP 最多请求数（登录/注册）
    API_RATE_LIMIT_PER_MINUTE: int = 60
    EXPENSIVE_RATE_LIMIT_PER_MINUTE: int = 10
    COOKIE_SECURE: bool = False
    COOKIE_NAME: str = "kb_access_token"
    MEDIA_URL_TTL_SECONDS: int = 3600

    # ===== File/object storage =====
    STORAGE_BACKEND: str = "local"  # local or oss
    LOCAL_STORAGE_ROOT: str = "data"
    OSS_REGION: str = ""
    OSS_ENDPOINT: str = ""
    OSS_BUCKET: str = ""
    OSS_PREFIX: str = "engineering-files"
    OSS_ACCESS_KEY_ID: str = ""
    OSS_ACCESS_KEY_SECRET: str = ""
    OSS_SESSION_TOKEN: str = ""

    # ===== Web / deployment =====
    ENVIRONMENT: str = "development"
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"
    TRUSTED_HOSTS: str = "localhost,127.0.0.1"
    AUTO_INIT_DB: bool = True
    RAG_REQUIRE_DEPARTMENT_MATCH: bool = False

    @property
    def llm_api_key(self) -> str:
        return self.LLM_API_KEY or self.DEEPSEEK_API_KEY

    @property
    def llm_base_url(self) -> str:
        return self.LLM_BASE_URL or self.DEEPSEEK_BASE_URL

    @field_validator("JWT_ALGORITHM")
    @classmethod
    def validate_jwt_algorithm(cls, value: str) -> str:
        if value != "HS256":
            raise ValueError("JWT_ALGORITHM currently supports HS256 only")
        return value

    @property
    def cors_origins(self) -> list[str]:
        return [item.strip() for item in self.CORS_ORIGINS.split(",") if item.strip()]

    @property
    def trusted_hosts(self) -> list[str]:
        return [item.strip() for item in self.TRUSTED_HOSTS.split(",") if item.strip()]

    @property
    def milvus_uri(self) -> str:
        return self.MILVUS_URI or f"http://{self.MILVUS_HOST}:{self.MILVUS_PORT}"

    @field_validator("STORAGE_BACKEND")
    @classmethod
    def validate_storage_backend(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in {"local", "oss"}:
            raise ValueError("STORAGE_BACKEND must be 'local' or 'oss'")
        return normalized

# 全局唯一配置实例——其他模块都 import 这个
settings = Settings()
