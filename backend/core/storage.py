import logging
import tempfile
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote

from fastapi import HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from backend.config import settings

logger = logging.getLogger(__name__)


class StorageError(RuntimeError):
    pass


def _clean_key(key: str) -> str:
    normalized = str(key).replace("\\", "/").strip("/")
    raw_parts = [part for part in normalized.split("/") if part]
    if any(part in {".", ".."} for part in raw_parts):
        raise StorageError("storage key contains unsafe path segments")
    parts = raw_parts
    if not parts:
        raise StorageError("empty storage key")
    return "/".join(parts)


def _content_disposition(filename: str) -> str:
    safe = quote(filename or "download", safe="")
    return f"attachment; filename*=UTF-8''{safe}"


class LocalStorage:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def put_bytes(self, key: str, content: bytes, content_type: str = "") -> str:
        path = self._path_for_key(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return str(path)

    def get_bytes(self, location: str) -> bytes:
        return self._path_for_location(location).read_bytes()

    def exists(self, location: str) -> bool:
        try:
            return self._path_for_location(location).is_file()
        except StorageError:
            return False

    def delete(self, location: str) -> None:
        path = self._path_for_location(location)
        path.unlink(missing_ok=True)

    def response(self, location: str, filename: str, media_type: str, headers: dict[str, str] | None = None):
        path = self._path_for_location(location)
        if not path.is_file():
            raise FileNotFoundError(str(path))
        return FileResponse(
            path=str(path),
            filename=filename,
            media_type=media_type,
            headers=headers,
        )

    def _path_for_key(self, key: str) -> Path:
        path = (self.root / _clean_key(key)).resolve()
        if self.root != path and self.root not in path.parents:
            raise StorageError("storage key escapes local root")
        return path

    def _path_for_location(self, location: str) -> Path:
        if location.startswith("oss://"):
            raise StorageError("OSS location cannot be opened by local storage")
        path = Path(location)
        if not path.is_absolute():
            if path.parts and path.parts[0] == self.root.name:
                path = Path.cwd() / path
            else:
                path = self.root / _clean_key(location)
        path = path.resolve()
        if self.root != path and self.root not in path.parents:
            raise StorageError("storage location escapes local root")
        return path


class OssStorage:
    def __init__(self):
        if not settings.OSS_BUCKET:
            raise StorageError("OSS_BUCKET is required")
        if not settings.OSS_REGION:
            raise StorageError("OSS_REGION is required")
        if not settings.OSS_ENDPOINT:
            raise StorageError("OSS_ENDPOINT is required")
        if not settings.OSS_ACCESS_KEY_ID or not settings.OSS_ACCESS_KEY_SECRET:
            raise StorageError("OSS access key is required")

        import alibabacloud_oss_v2 as oss

        provider = oss.credentials.StaticCredentialsProvider(
            settings.OSS_ACCESS_KEY_ID,
            settings.OSS_ACCESS_KEY_SECRET,
            settings.OSS_SESSION_TOKEN or None,
        )
        config = oss.Config(
            region=settings.OSS_REGION,
            endpoint=settings.OSS_ENDPOINT,
            signature_version="v4",
            credentials_provider=provider,
            connect_timeout=5,
            readwrite_timeout=30,
        )
        self._oss = oss
        self._client = oss.Client(config)
        self.bucket = settings.OSS_BUCKET
        self.prefix = settings.OSS_PREFIX.strip("/")

    def put_bytes(self, key: str, content: bytes, content_type: str = "") -> str:
        object_key = self._object_key(key)
        self._client.put_object(
            self._oss.PutObjectRequest(
                bucket=self.bucket,
                key=object_key,
                body=content,
                content_type=content_type or None,
            )
        )
        return self._uri(object_key)

    def get_bytes(self, location: str) -> bytes:
        object_key = self._key_from_location(location)
        result = self._client.get_object(self._oss.GetObjectRequest(bucket=self.bucket, key=object_key))
        try:
            return result.body.read()
        finally:
            result.body.close()

    def exists(self, location: str) -> bool:
        object_key = self._key_from_location(location)
        return bool(self._client.is_object_exist(self.bucket, object_key))

    def delete(self, location: str) -> None:
        object_key = self._key_from_location(location)
        self._client.delete_object(self._oss.DeleteObjectRequest(bucket=self.bucket, key=object_key))

    def response(self, location: str, filename: str, media_type: str, headers: dict[str, str] | None = None):
        payload = self.get_bytes(location)
        response_headers = dict(headers or {})
        response_headers.setdefault("Content-Disposition", _content_disposition(filename))
        return StreamingResponse(
            iter([payload]),
            media_type=media_type,
            headers=response_headers,
        )

    def _object_key(self, key: str) -> str:
        clean = _clean_key(key)
        return f"{self.prefix}/{clean}" if self.prefix else clean

    def _uri(self, object_key: str) -> str:
        return f"oss://{self.bucket}/{object_key}"

    def _key_from_location(self, location: str) -> str:
        if location.startswith("oss://"):
            marker = f"oss://{self.bucket}/"
            if not location.startswith(marker):
                raise StorageError("OSS location belongs to a different bucket")
            return _clean_key(location[len(marker):])
        return self._object_key(location)


class StorageManager:
    def __init__(self):
        self.local = LocalStorage(settings.LOCAL_STORAGE_ROOT)
        self._oss: OssStorage | None = None

    @property
    def oss(self) -> OssStorage:
        if self._oss is None:
            self._oss = OssStorage()
        return self._oss

    @property
    def write_backend(self):
        return self.oss if settings.STORAGE_BACKEND.lower() == "oss" else self.local

    def put_bytes(self, key: str, content: bytes, content_type: str = "") -> str:
        return self.write_backend.put_bytes(key, content, content_type)

    def exists(self, location: str) -> bool:
        return self._backend_for_location(location).exists(location)

    def delete(self, location: str) -> None:
        self._backend_for_location(location).delete(location)

    def get_bytes(self, location: str) -> bytes:
        return self._backend_for_location(location).get_bytes(location)

    def response(
        self,
        location: str,
        filename: str,
        media_type: str = "application/octet-stream",
        headers: dict[str, str] | None = None,
    ):
        try:
            return self._backend_for_location(location).response(location, filename, media_type, headers=headers)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="文件不存在") from exc

    @contextmanager
    def local_file(self, location: str, suffix: str = ""):
        if not location.startswith("oss://"):
            yield self.local._path_for_location(location)
            return
        payload = self.get_bytes(location)
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
            handle.write(payload)
            tmp_path = Path(handle.name)
        try:
            yield tmp_path
        finally:
            tmp_path.unlink(missing_ok=True)

    def _backend_for_location(self, location: str):
        return self.oss if location.startswith("oss://") else self.local


storage = StorageManager()
