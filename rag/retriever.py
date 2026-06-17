"""相似论文片段检索（Phase 2）。

接收查询文本与可选的章节类型过滤，从 ChromaDB 检索最相关的切片，
返回带元数据（论文来源、章节类型、相似度分数）的结果列表。
"""

import logging

from rag.chunker import SECTIONS
from rag.store import embed_texts, get_collection

logger = logging.getLogger(__name__)


def retrieve(query: str, top_k: int = 5, section_type: str | None = None) -> list[dict]:
    """检索与查询最相关的论文切片。

    Args:
        query: 查询文本。
        top_k: 返回的切片数量，默认 5。
        section_type: 可选的章节过滤，只检索该章节（须为 SECTIONS 之一，
            如 "摘要"、"模型建立"）；为 None 时检索全部章节。

    Returns:
        结果列表，按相似度从高到低排序，每项为字典：
        - text (str): 切片正文
        - source (str): 来源论文文件名
        - section (str): 章节类型
        - title (str): 切片所属章节标题
        - summary (str): 切片一句话摘要
        - methods (str): 建模方法（逗号分隔）
        - keywords (str): 关键词（逗号分隔）
        - score (float): 余弦相似度 ∈ [-1, 1]，越大越相关
        - distance (float): ChromaDB 原始余弦距离

    Raises:
        ValueError: 查询为空，或 section_type 非法时抛出。
    """
    if not query or not query.strip():
        raise ValueError("查询文本不能为空")
    if section_type is not None and section_type not in SECTIONS:
        raise ValueError(f"section_type 非法：{section_type!r}，应为 {SECTIONS} 之一或 None")

    where = {"section": section_type} if section_type else None
    logger.info("检索：query 长度=%d，top_k=%d，section=%s", len(query), top_k, section_type)

    collection = get_collection()
    res = collection.query(
        query_embeddings=embed_texts([query]),
        n_results=top_k,
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    # query 结果为「每个查询一个列表」的二维结构，这里只有单个查询，取第 0 个
    documents = res["documents"][0] if res["documents"] else []
    metadatas = res["metadatas"][0] if res["metadatas"] else []
    distances = res["distances"][0] if res["distances"] else []

    results: list[dict] = []
    for doc, meta, dist in zip(documents, metadatas, distances):
        results.append(
            {
                "text": doc,
                "source": meta.get("source", ""),
                "section": meta.get("section", ""),
                "title": meta.get("title", ""),
                "summary": meta.get("summary", ""),
                "methods": meta.get("methods", ""),
                "keywords": meta.get("keywords", ""),
                "score": round(1.0 - dist, 4),
                "distance": round(dist, 4),
            }
        )

    logger.info("检索完成，返回 %d 条结果", len(results))
    return results
