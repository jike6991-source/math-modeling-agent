"""向量库与 embedding 的共享访问层（Phase 2）。

集中管理 BGE embedding 模型与 ChromaDB collection，供 rag.indexer（写入）与
rag.retriever（检索）复用，保证两端的 embedding 方式与 collection 配置完全一致。
"""

import logging

from config import CHROMA_COLLECTION, CHROMA_DIR, EMBEDDING_MODEL

logger = logging.getLogger(__name__)

_embedder = None  # SentenceTransformer 惰性缓存
_collection = None  # Chroma collection 惰性缓存

# collection 配置：
# - hnsw:space=cosine：配合归一化向量，使距离落在 [0,2]、相似度 = 1 - 距离 ∈ [-1,1]，便于解释；
# - sync_threshold/batch_size 调到极大：向量只留在持久化的 SQLite 日志、读取时在内存重建 HNSW，
#   规避 chromadb 1.1.1 批量写入跨阈值后只落 pickle 不落 .bin、致新进程冷读报错的缺陷。
_COLLECTION_CONFIG: dict = {
    "hnsw:space": "cosine",
    "hnsw:sync_threshold": 10_000_000,
    "hnsw:batch_size": 10_000_000,
}


def get_embedder():
    """惰性加载并缓存 BGE embedding 模型。"""
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer

        logger.info("加载 embedding 模型：%s", EMBEDDING_MODEL)
        _embedder = SentenceTransformer(EMBEDDING_MODEL)
    return _embedder


def embed_texts(texts: list[str]) -> list[list[float]]:
    """把文本批量编码为归一化向量（写入与检索共用，保证一致性）。

    Args:
        texts: 待编码文本列表。

    Returns:
        归一化后的向量列表（每个为 float 列表）。
    """
    return get_embedder().encode(texts, normalize_embeddings=True).tolist()


def get_collection():
    """惰性创建并缓存持久化的 Chroma collection。"""
    global _collection
    if _collection is None:
        import chromadb

        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        _collection = client.get_or_create_collection(CHROMA_COLLECTION, metadata=_COLLECTION_CONFIG)
    return _collection
