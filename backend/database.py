"""数据库连接管理——所有模块共用一个连接池"""
from sqlalchemy import URL, create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, Session
from pathlib import Path
from uuid import UUID, uuid4

from backend.config import settings
from backend.models import Base          # ← 从包导入，自动包含所有注册过的表
from backend.models.document_asset import DocumentAsset


DATABASE_URL = URL.create(
    "mysql+pymysql",
    username=settings.MYSQL_USER,
    password=settings.MYSQL_PASSWORD,
    host=settings.MYSQL_HOST,
    port=settings.MYSQL_PORT,
    database=settings.MYSQL_DATABASE,
    query={"charset": "utf8mb4"},
)

connect_args = {
    "connect_timeout": 10,
    "read_timeout": 30,
    "write_timeout": 30,
}
if settings.MYSQL_SSL_CA:
    connect_args["ssl"] = {"ca": settings.MYSQL_SSL_CA, "check_hostname": True}

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=settings.MYSQL_POOL_SIZE,
    max_overflow=settings.MYSQL_MAX_OVERFLOW,
    pool_recycle=3600,                  # ← 每小时回收连接，防 MySQL 8 小时断开
    connect_args=connect_args,
    echo=False,
)
SessionLocal = sessionmaker(bind=engine)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_image_asset_columns():
    required_columns = {
        "category_id": "VARCHAR(64) NULL",
        "content_hash": "VARCHAR(64) NULL",
        "perceptual_hash": "VARCHAR(32) NULL",
        "group_id": "VARCHAR(64) NULL",
        "last_used_at": "DATETIME NULL",
        "status": "VARCHAR(20) NOT NULL DEFAULT 'ready'",
        "processing_error": "TEXT NULL",
    }
    inspector = inspect(engine)
    if "image_assets" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("image_assets")}
    with engine.begin() as conn:
        for name, definition in required_columns.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE image_assets ADD COLUMN {name} {definition}"))


def _ensure_image_asset_indexes():
    inspector = inspect(engine)
    if "image_assets" not in inspector.get_table_names():
        return
    existing = {index.get("name") for index in inspector.get_indexes("image_assets")}
    wanted = {
        "ix_image_assets_content_hash": "content_hash",
        "ix_image_assets_perceptual_hash": "perceptual_hash",
        "ix_image_assets_group_id": "group_id",
        "ix_image_assets_status": "status",
    }
    with engine.begin() as conn:
        for name, column in wanted.items():
            if name not in existing:
                conn.execute(text(f"CREATE INDEX {name} ON image_assets ({column})"))


def _migrate_legacy_user_roles():
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return
    with engine.begin() as conn:
        conn.execute(text("UPDATE users SET role = 'employee' WHERE role = 'user'"))


def _ensure_user_security_columns():
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("users")}
    if "token_version" not in existing:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN token_version INT NOT NULL DEFAULT 0"))


def _ensure_usage_unique_index():
    inspector = inspect(engine)
    if "image_platform_usage" not in inspector.get_table_names():
        return
    indexes = inspector.get_indexes("image_platform_usage")
    if any(index.get("name") == "uq_image_platform_usage" for index in indexes):
        return
    with engine.begin() as conn:
        groups = conn.execute(text("""
            SELECT image_id, platform, MIN(id) AS keeper_id,
                   SUM(usage_count) AS total_count, MAX(last_used_at) AS latest_use
            FROM image_platform_usage
            GROUP BY image_id, platform
            HAVING COUNT(*) > 1
        """)).mappings().all()
        for group in groups:
            conn.execute(
                text("""
                    UPDATE image_platform_usage
                    SET usage_count = :total_count, last_used_at = :latest_use
                    WHERE id = :keeper_id
                """),
                dict(group),
            )
            conn.execute(
                text("""
                    DELETE FROM image_platform_usage
                    WHERE image_id = :image_id AND platform = :platform AND id <> :keeper_id
                """),
                dict(group),
            )
        conn.execute(text(
            "ALTER TABLE image_platform_usage "
            "ADD UNIQUE INDEX uq_image_platform_usage (image_id, platform)"
        ))


def _register_legacy_documents():
    upload_dir = Path("data/uploads")
    if not upload_dir.exists():
        return
    db = SessionLocal()
    try:
        existing = {row[0] for row in db.query(DocumentAsset.stored_name).all()}
        for file_path in upload_dir.iterdir():
            if not file_path.is_file() or file_path.name in existing:
                continue
            prefix, separator, original_name = file_path.name.partition("_")
            try:
                document_id = str(UUID(prefix)) if separator else str(uuid4())
            except ValueError:
                document_id = str(uuid4())
                original_name = file_path.name
            stat = file_path.stat()
            db.add(DocumentAsset(
                id=document_id,
                filename=original_name or file_path.name,
                stored_name=file_path.name,
                file_path=str(file_path),
                file_type=file_path.suffix.lower().lstrip("."),
                file_size=stat.st_size,
                status="ready",
            ))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(engine)
    _ensure_image_asset_columns()
    _ensure_image_asset_indexes()
    _ensure_user_security_columns()
    _ensure_usage_unique_index()
    _migrate_legacy_user_roles()
    _register_legacy_documents()
