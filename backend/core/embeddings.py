from http import HTTPStatus

from dashscope import TextEmbedding
from langchain_core.embeddings import Embeddings

from backend.config import settings


class DashScopeTextEmbeddings(Embeddings):
    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        response = TextEmbedding.call(
            model=settings.EMBEDDING_MODEL,
            input=texts,
            api_key=settings.DASHSCOPE_API_KEY,
            dimension=settings.EMBEDDING_DIM,
        )
        if response.status_code != HTTPStatus.OK:
            raise RuntimeError(f"DashScope embedding failed: {response.code} {response.message}")
        ordered = sorted(response.output["embeddings"], key=lambda item: item.get("text_index", 0))
        return [[float(value) for value in item["embedding"]] for item in ordered]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), 10):
            vectors.extend(self._embed_batch(texts[start:start + 10]))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self._embed_batch([text])[0]


def get_embeddings() -> Embeddings:
    return DashScopeTextEmbeddings()


def embed_text_query(text: str) -> list[float]:
    return get_embeddings().embed_query(text)
