from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_chat_does_not_render_untrusted_html():
    source = (ROOT / "frontend" / "src" / "pages" / "Chat.tsx").read_text(encoding="utf-8")
    assert "dangerouslySetInnerHTML" not in source


def test_vector_stores_never_drop_collections_automatically():
    for name in ("image_vector_store.py", "image_text_vector_store.py"):
        source = (ROOT / "backend" / "core" / name).read_text(encoding="utf-8")
        assert ".drop_collection(" not in source


def test_image_asset_download_counts_after_response_completion():
    source = (ROOT / "backend" / "api" / "image_assets.py").read_text(encoding="utf-8")
    download_func = source.split('@router.post("/image-assets/download")', 1)[1].split("def _delete_asset", 1)[0]

    assert "BackgroundTask(_record_completed_asset_download" in download_func
    assert "db.commit()" not in download_func


def test_image_download_counts_after_response_completion():
    source = (ROOT / "backend" / "api" / "images.py").read_text(encoding="utf-8")
    download_func = source.split('@router.post("/images/download"', 1)[1].split('@router.post("/images/delete"', 1)[0]

    assert "BackgroundTask(_record_completed_image_download" in download_func
    assert "db.commit()" not in download_func


def test_chat_retrieval_intent_skips_casual_questions():
    from backend.api.chat import should_use_knowledge_base

    assert should_use_knowledge_base("你好") is False
    assert should_use_knowledge_base("请用三句话介绍你自己") is False
    assert should_use_knowledge_base("痛经软膏说明书主要内容是什么") is True
    assert should_use_knowledge_base("根据上传文档总结注意事项") is True
