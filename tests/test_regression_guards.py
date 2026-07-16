from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_chat_does_not_render_untrusted_html():
    source = (ROOT / "frontend" / "src" / "pages" / "Chat.tsx").read_text(encoding="utf-8")
    assert "dangerouslySetInnerHTML" not in source


def test_vector_stores_never_drop_collections_automatically():
    for name in ("image_vector_store.py", "image_text_vector_store.py"):
        source = (ROOT / "backend" / "core" / name).read_text(encoding="utf-8")
        assert ".drop_collection(" not in source
