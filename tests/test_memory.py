from backend.config import settings
from backend.core.memory import ConversationMemory


def test_memory_isolated_by_server_side_key():
    memory = ConversationMemory(max_history=2)
    memory.add("1:session", "first", "answer-one")
    memory.add("2:session", "second", "answer-two")

    assert "answer-one" in memory.get_history("1:session")
    assert "answer-two" not in memory.get_history("1:session")
    assert "answer-two" in memory.get_history("2:session")


def test_memory_is_bounded(monkeypatch):
    monkeypatch.setattr(settings, "MAX_MEMORY_SESSIONS", 2)
    memory = ConversationMemory(max_history=1)
    memory.add("oldest", "q", "a")
    memory.add("middle", "q", "a")
    memory.add("newest", "q", "a")

    assert len(memory._store) <= 2
