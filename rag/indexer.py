"""论文切片与入库（Phase 2）。

将论文切片并写入向量库（ChromaDB + BGE-small-zh-v1.5）。本文件为骨架。
"""

import logging

logger = logging.getLogger(__name__)


def index_documents(doc_dir: str) -> int:
    """切片论文并入库。

    Args:
        doc_dir: 论文文件所在目录。

    Returns:
        入库的切片数量。
    """
    raise NotImplementedError("索引逻辑待实现（Phase 2）")
