"""论文切片与入库（Phase 2）。

接收 PDF 路径，提取文本（rag.chunker）并按章节切片，调用 DeepSeek 给每个切片做
结构化标注，最后用 BGE-small-zh embedding 存入 ChromaDB。

复用 agents/analyzer.py 的 LLM 调用范式（get_llm_client + json_object + 指数退避重试）。
"""

import json
import logging
from pathlib import Path

from config import PAPERS_DIR, PROCESSED_DIR
from rag.annotator import annotate_chunk
from rag.chunker import extract_text, split_sections
from rag.store import embed_texts, get_collection

logger = logging.getLogger(__name__)


def index_pdf(pdf_path: str) -> int:
    """索引单个 PDF：提取 → 切片 → 标注 → embedding → 存入 ChromaDB。

    Args:
        pdf_path: PDF 文件路径。

    Returns:
        成功入库的切片数量；无有效内容时返回 0。

    Raises:
        FileNotFoundError: PDF 不存在时抛出。
        ValueError: PDF 无法打开时抛出。
    """
    source = Path(pdf_path).name
    logger.info("开始索引 PDF：%s", source)

    full_text = extract_text(pdf_path)
    if not full_text.strip():
        logger.warning("PDF 文本为空，跳过：%s", source)
        return 0

    raw_chunks = split_sections(full_text)
    if not raw_chunks:
        logger.warning("未切出任何片段，跳过：%s", source)
        return 0
    logger.info("切出 %d 个片段，开始标注", len(raw_chunks))

    records: list[dict] = []
    for chunk in raw_chunks:
        ann = annotate_chunk(chunk["text"], chunk["section"])
        records.append({**chunk, **ann})

    _store_records(source, records)

    # 备查：把切片+标注写入 processed/
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / f"{Path(source).stem}.json"
    out_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info("索引完成：%s，入库 %d 个切片", source, len(records))
    return len(records)


def _store_records(source: str, records: list[dict]) -> None:
    """把一篇论文的切片记录 embedding 后写入 ChromaDB。

    Args:
        source: 来源 PDF 文件名（用于生成 chunk id 与 metadata.source）。
        records: 每项含 title/section/text/summary/methods/keywords 的切片记录。
    """
    embeddings = embed_texts([r["text"] for r in records])

    ids, documents, metadatas = [], [], []
    for idx, r in enumerate(records):
        ids.append(f"{source}-{idx}")
        documents.append(r["text"])
        metadatas.append(
            {
                "source": source,
                "section": r["section"],
                "title": r["title"],
                "summary": r["summary"],
                "methods": ", ".join(r["methods"]),
                "keywords": ", ".join(r["keywords"]),
            }
        )

    collection = get_collection()
    collection.add(ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas)


def index_documents(doc_dir: str | None = None) -> dict:
    """递归批量索引目录及其所有子目录下的 PDF。

    按题型子目录（如 A-F）聚合统计，便于查看各文件夹的论文数与切片分布。

    Args:
        doc_dir: PDF 根目录，默认 knowledge/papers/。

    Returns:
        统计字典：total_chunks（切片总数）、total_papers（成功论文数）、
        by_folder（子目录名 -> {"papers", "chunks"}）、failed（失败文件路径列表）。
    """
    root = Path(doc_dir) if doc_dir else PAPERS_DIR
    pdfs = sorted(root.rglob("*.pdf"))
    if not pdfs:
        logger.warning("目录下未找到 PDF：%s", root)
        return {"total_chunks": 0, "total_papers": 0, "by_folder": {}, "failed": []}

    total_chunks = 0
    total_papers = 0
    by_folder: dict[str, dict[str, int]] = {}
    failed: list[str] = []

    for pdf in pdfs:
        # 以相对根目录的第一层子目录作为题型分组（无子目录则归为根目录名）
        rel = pdf.relative_to(root)
        folder = rel.parts[0] if len(rel.parts) > 1 else root.name
        bucket = by_folder.setdefault(folder, {"papers": 0, "chunks": 0})
        try:
            n = index_pdf(str(pdf))
            total_chunks += n
            total_papers += 1
            bucket["papers"] += 1
            bucket["chunks"] += n
        except Exception as exc:  # noqa: BLE001 - 单篇失败不阻塞其余
            logger.error("索引失败，跳过 %s：%s", pdf, exc)
            failed.append(str(pdf))

    logger.info(
        "批量索引完成：%d 篇论文，共入库 %d 个切片，失败 %d 个",
        total_papers, total_chunks, len(failed),
    )
    return {
        "total_chunks": total_chunks,
        "total_papers": total_papers,
        "by_folder": by_folder,
        "failed": failed,
    }


def rebuild_from_processed(processed_dir: str | None = None) -> int:
    """从 processed/ 下已标注的切片 JSON 重建向量库，不重新调用 LLM。

    用于向量库损坏、更换 embedding 模型，或需要重新生成 ChromaDB 时快速重建——
    复用缓存的标注结果，仅重新做本地 embedding。调用前应先清空 chroma_db 目录。

    Args:
        processed_dir: 切片 JSON 目录，默认 knowledge/processed/。

    Returns:
        重建入库的切片总数。
    """
    directory = Path(processed_dir) if processed_dir else PROCESSED_DIR
    files = sorted(directory.glob("*.json"))
    if not files:
        logger.warning("processed 目录下未找到 JSON：%s", directory)
        return 0

    total = 0
    for jf in files:
        records = json.loads(jf.read_text(encoding="utf-8"))
        if not records:
            continue
        source = f"{jf.stem}.pdf"  # processed 文件名即 PDF 主名
        _store_records(source, records)
        total += len(records)
        logger.info("重建入库：%s，%d 个切片", source, len(records))

    logger.info("向量库重建完成，共入库 %d 个切片（%d 篇）", total, len(files))
    return total
