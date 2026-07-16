"""
Milvus 向量数据库的连接管理与操作（pymilvus 3.0 原生版）
"""

from pymilvus import MilvusClient
from langchain_core.documents import Document
from backend.config import settings

import logging

logger = logging.getLogger(__name__)

# ============================================================
# 客户端复用
# ============================================================
_client_cache = {}


def _get_client(uri: str) -> MilvusClient:
    """全局共用一个 MilvusClient，避免反复建立连接"""
    if uri not in _client_cache:
        kwargs = {"uri": uri, "token": settings.MILVUS_TOKEN}
        if settings.MILVUS_SERVER_PEM_PATH:
            kwargs["server_pem_path"] = settings.MILVUS_SERVER_PEM_PATH
        _client_cache[uri] = MilvusClient(**kwargs)
    return _client_cache[uri]


# ============================================================
# LangChain 兼容封装器
# ============================================================
class MilvusWrapper:
    """用 MilvusClient（pymilvus 3.0+ 推荐方式）封装 LangChain 兼容接口"""

    def __init__(self, embeddings, collection_name: str = "knowledge_base"):
        uri = settings.milvus_uri
        self.embeddings = embeddings
        self.collection_name = collection_name
        self.client = _get_client(uri)

        # 动态检测向量维度
        self.dim = self._detect_dimension()

        # 确保 collection 存在
        self._ensure_collection()

        # 确保索引存在
        self._ensure_index()

    # ----- 内部方法 -----

    def _detect_dimension(self) -> int:
        """Use the configured dimension so construction does not consume an API call."""
        return settings.EMBEDDING_DIM

    def _ensure_collection(self):
        """创建 collection（如果不存在）"""
        if self.client.has_collection(self.collection_name):
            description = self.client.describe_collection(self.collection_name)
            vector_field = next(
                (field for field in description.get("fields", []) if field.get("name") == "vector"),
                None,
            )
            params = (vector_field or {}).get("params", {})
            existing_dim = int(params.get("dim", self.dim))
            if existing_dim != self.dim:
                raise RuntimeError(
                    f"Milvus collection '{self.collection_name}' dimension is {existing_dim}, "
                    f"but the configured embedding model returns {self.dim}. Run an explicit migration."
                )
            return
        self.client.create_collection(
            collection_name=self.collection_name,
            dimension=self.dim,
            auto_id=True,                # Milvus 自动生成唯一主键
            enable_dynamic_field=True,   # 允许存入任意 metadata 字段
        )
        logger.info(f"[Milvus] 创建 Collection '{self.collection_name}'，维度 {self.dim}")


    def _ensure_index(self):
        """自动创建 HNSW 索引（如果不存在）"""
        try:
            indexes = self.client.list_indexes(self.collection_name)
            has_vector_index = False
            if isinstance(indexes, list):
                for idx in indexes:
                    # 仅当是字典时才读取字段
                    if isinstance(idx, dict) and idx.get("field_name") == "vector":
                        has_vector_index = True
                        break
            if has_vector_index:
                logger.info(f"[Milvus] 集合 {self.collection_name} vector索引已存在")
                self.client.load_collection(self.collection_name)
                return
        except Exception as e:
            logger.warning(f"[Milvus] 查询索引列表异常，将尝试新建索引: {str(e)}")

        index_params = MilvusClient.prepare_index_params()
        index_params.add_index(
            field_name="vector",
            index_type="HNSW",
            metric_type="COSINE",
            params={"M": 16, "efConstruction": 200},
        )
        self.client.create_index(
            collection_name=self.collection_name,
            index_params=index_params,
        )
        # 新建索引后必须加载
        self.client.load_collection(self.collection_name)
        logger.info("[Milvus] 创建索引并加载集合完成 (HNSW, COSINE)")
    # ----- 对外接口 -----

    def add_documents(self, docs: list[Document], batch_size: int = 100):
        """分批次写入文档到 Milvus

        docs: LangChain Document 对象列表（已切分好的小块）
        """
        if not docs:
            return

        texts = [doc.page_content for doc in docs]
        metadatas = [doc.metadata for doc in docs]

        logger.info(f"   正在向量化 {len(texts)} 条文本...")
        vectors = self.embeddings.embed_documents(texts)

        # 构建插入数据
        data = []
        for i, (text, vector, meta) in enumerate(zip(texts, vectors, metadatas)):
            data.append({
                "vector": vectors[i],
                "text": texts[i],
                **metadatas[i],          # 展开完整 metadata（动态字段）
            })

        # 分批插入
        total = len(data)
        for start in range(0, total, batch_size):
            end = min(start + batch_size, total)
            try:
                self.client.insert(
                    collection_name=self.collection_name,
                    data=data[start:end],
                )
            except Exception as e:
                logger.error(f"插入失败 [{start}:{end}]: {e}")
                raise

        # 刷盘
        self.client.flush(self.collection_name)
        logger.info(f"   {total} 条数据写入完成")

    
    def delete_by_source(self, file_path: str) -> int:
        """按文件路径删除所有相关chunk，返回删除条数"""
        safe_path = file_path.replace("\\", "/")
        windows_path = file_path.replace("/", "\\\\")
        filter_expr = f'source in ["{safe_path}", "{windows_path}"]'
        res = self.client.delete(
            collection_name=self.collection_name,
            filter=filter_expr,
        )
        self.client.flush(self.collection_name)
        count = res.get("delete_count", 0) if isinstance(res, dict) else 0
        logger.info(f"[Milvus] 已删除 {count} 条向量，source={file_path}")
        return count

    def search(self,query: str, k: int = 5) -> list[Document]:
        """相似度搜索（返回 Document 列表）"""
        pairs = self.similarity_search_with_score(query, k)
        return [doc for doc, _ in pairs]

    def similarity_search_with_score(self, query: str, k: int = 5,filter:str=None) -> list[tuple]:
        """带分数的相似度搜索
        返回: [(Document, score), ...]
        """
        query_vec = self.embeddings.embed_query(query)
        results = self.client.search(
            collection_name=self.collection_name,
            data=[query_vec],
            limit=k,
            output_fields=["*"],  # 取出所有字段（含动态 metadata）
            filter=filter,
        )

        pairs = []
        for hit in results[0]:
            entity = hit.get("entity", {})
            # 分离 text 和 metadata 字段
            metadata = {k: v for k, v in entity.items() if k not in ("text", "vector")}
            metadata["score"] = hit.get("distance", 0)
            doc = Document(
                page_content=entity.get("text", ""),
                metadata=metadata,
            )
            pairs.append((doc, hit.get("distance", 0)))
        return pairs


# ============================================================
# 对外暴露的入口函数
# ============================================================
def get_langchain_vectorstore(embeddings, collection_name: str = "knowledge_base"):
    """获取 LangChain 兼容的 Milvus 向量存储对象"""
    return MilvusWrapper(embeddings, collection_name)


def insert_documents(vectorstore, docs):
    """批量写入文档到 Milvus"""
    vectorstore.add_documents(docs)


def search_similar(vectorstore, query: str, k: int = 5):
    """搜索与 query 最相似的 k 个文档块"""
    return vectorstore.similarity_search_with_score(query, k)
