import logging

from pymilvus import MilvusClient

from backend.config import settings
from backend.core.image_vector_store import _get_client

logger = logging.getLogger(__name__)


class ImageTextVectorStore:
    def __init__(self, collection_name: str | None = None):
        self.collection_name = collection_name or settings.IMAGE_TEXT_COLLECTION_NAME
        self.dim = settings.IMAGE_TEXT_EMBEDDING_DIM
        uri = settings.milvus_uri
        self.client = _get_client(uri)
        self._ensure_collection()
        self._ensure_index()

    def _ensure_collection(self):
        if self.client.has_collection(self.collection_name):
            desc = self.client.describe_collection(self.collection_name)
            fields = desc.get("fields", [])
            id_field = next((field for field in fields if field.get("name") == "id"), None)
            if id_field and str(id_field.get("type", "")).upper() not in {"VARCHAR", "21"}:
                raise RuntimeError(
                    f"Milvus collection '{self.collection_name}' has an incompatible id field "
                    f"type ({id_field.get('type')}). Run an explicit collection migration; "
                    "automatic deletion is disabled."
                )
            else:
                return
        if self.client.has_collection(self.collection_name):
            return
        self.client.create_collection(
            collection_name=self.collection_name,
            dimension=self.dim,
            primary_field_name="id",
            id_type="string",
            vector_field_name="vector",
            metric_type="COSINE",
            auto_id=False,
            enable_dynamic_field=True,
            max_length=128,
        )
        logger.info("[Milvus] Created image text collection '%s' with dim=%s", self.collection_name, self.dim)

    def _ensure_index(self):
        try:
            self.client.load_collection(self.collection_name)
            return
        except Exception as exc:
            logger.info("[Milvus] Collection %s is not loaded yet: %s", self.collection_name, exc)
        index_params = MilvusClient.prepare_index_params()
        index_params.add_index(
            field_name="vector",
            index_type="HNSW",
            metric_type="COSINE",
            params={"M": 16, "efConstruction": 200},
        )
        self.client.create_index(collection_name=self.collection_name, index_params=index_params)
        self.client.load_collection(self.collection_name)

    def upsert_text(self, vector: list[float], metadata: dict):
        image_id = metadata["image_id"]
        self.delete_text(image_id)
        self.client.insert(
            collection_name=self.collection_name,
            data=[{"id": image_id, "vector": vector, **metadata}],
        )
        self.client.flush(self.collection_name)

    def search(self, vector: list[float], limit: int = 20) -> list[dict]:
        results = self.client.search(
            collection_name=self.collection_name,
            data=[vector],
            limit=limit,
            output_fields=["*"],
        )
        items = []
        for hit in results[0]:
            entity = hit.get("entity", {})
            items.append(
                {
                    "image_id": entity.get("image_id") or entity.get("id"),
                    "filename": entity.get("filename", ""),
                    "score": float(hit.get("distance", 0)),
                    "description": entity.get("description", ""),
                    "tags": entity.get("tags", ""),
                }
            )
        return items

    def delete_text(self, image_id: str):
        try:
            self.client.delete(collection_name=self.collection_name, ids=[image_id])
            self.client.flush(self.collection_name)
        except Exception as exc:
            logger.error("[Milvus] Failed to delete image text vector image_id=%s: %s", image_id, exc)
            raise


def get_image_text_vector_store() -> ImageTextVectorStore:
    return ImageTextVectorStore()
