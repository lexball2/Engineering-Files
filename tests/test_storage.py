import pytest

from backend.core.storage import LocalStorage, StorageError


def test_local_storage_round_trip(tmp_path):
    storage = LocalStorage(tmp_path / "data")
    location = storage.put_bytes("uploads/example.txt", b"hello", "text/plain")

    assert storage.exists(location)
    assert storage.get_bytes(location) == b"hello"

    storage.delete(location)
    assert not storage.exists(location)


def test_local_storage_rejects_traversal(tmp_path):
    storage = LocalStorage(tmp_path / "data")

    with pytest.raises(StorageError):
        storage.put_bytes("../secret.txt", b"nope")
