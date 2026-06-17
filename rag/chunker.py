"""PDF 文本提取与章节切片（Phase 2）。

用 PyMuPDF 提取 PDF 全文，按中文章节标题正则切片并归并到 6 类标准章节；
无清晰标题时退化为定长滑窗切片。被 rag/indexer.py 复用。
"""

import logging
import re
from pathlib import Path

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

# 6 类标准章节，作为切片归并目标与标注枚举
SECTIONS: tuple[str, ...] = ("摘要", "问题重述", "模型假设", "模型建立", "求解", "结果分析")

# 标题关键词 -> 6 类映射（按从具体到宽泛顺序，命中第一个即采用；标注阶段会由 LLM 再校正）
_SECTION_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("摘要", "摘要"),
    ("关键词", "摘要"),
    ("问题重述", "问题重述"),
    ("问题分析", "问题重述"),
    ("背景", "问题重述"),
    ("假设", "模型假设"),
    ("符号", "模型假设"),
    ("建立", "模型建立"),
    ("求解", "求解"),
    ("算法", "求解"),
    ("结果", "结果分析"),
    ("分析", "结果分析"),
    ("检验", "结果分析"),
    ("灵敏度", "结果分析"),
    ("评价", "结果分析"),
    ("改进", "结果分析"),
    ("结论", "结果分析"),
)

# 非正文章节：不纳入知识库索引（参考文献、附录代码、致谢等对建模检索无价值且占比大）
_SKIP_KEYWORDS: tuple[str, ...] = ("参考文献", "参考资料", "附录", "致谢")

# 顶级标题正则：① 摘要/关键词（可能无编号、字间含全角空格）；
# ② 中文数字编号开头的短行（一、… 第一章 …），不要求关键词紧跟编号——真实国赛标题
#    常为「四、问题一：模型建立与求解」。流程图等无编号碎片因此不会被误判为标题。
_TITLE_PATTERN = re.compile(
    r"^[ \t]*("
    r"摘\s{0,3}要[^\n]{0,4}"  # 摘 要 / 摘要：
    r"|关\s{0,3}键\s{0,3}词[^\n]{0,4}"
    r"|第?[一二三四五六七八九十]{1,3}\s{0,3}[、.．章][^\n]{0,30}"
    r")[ \t]*$",
    re.MULTILINE,
)

# 滑窗参数：无标题时切片，以及对超长章节做二次细分
_WINDOW_SIZE = 1000
_WINDOW_OVERLAP = 150
_MAX_CHUNK = 1800  # 单个章节超过此长度则滑窗细分，保证 embedding 质量


def extract_text(pdf_path: str) -> str:
    """用 PyMuPDF 逐页提取 PDF 全文。

    Args:
        pdf_path: PDF 文件路径。

    Returns:
        拼接后的全文文本。

    Raises:
        FileNotFoundError: 文件不存在时抛出。
        ValueError: 文件无法作为 PDF 打开时抛出。
    """
    path = Path(pdf_path)
    if not path.is_file():
        raise FileNotFoundError(f"PDF 文件不存在：{pdf_path}")
    try:
        doc = fitz.open(path)
    except Exception as exc:  # noqa: BLE001 - 统一转换为 ValueError
        raise ValueError(f"无法打开 PDF：{pdf_path}") from exc
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


def _is_skip_section(title: str) -> bool:
    """判断标题是否属于不纳入索引的非正文章节（参考文献/附录/致谢）。"""
    clean = re.sub(r"\s", "", title)
    return any(kw in clean for kw in _SKIP_KEYWORDS)


def _guess_section(title: str) -> str:
    """根据标题关键词归并到 6 类标准章节，无法匹配时返回 '其他'。

    先去掉标题内的空白（PDF 提取常见「摘 要」全角空格），再做关键词匹配。
    """
    clean = re.sub(r"\s", "", title)
    for keyword, section in _SECTION_KEYWORDS:
        if keyword in clean:
            return section
    return "其他"


def _window_split(text: str, title: str = "", section: str = "其他") -> list[dict]:
    """把一段文本按定长滑窗切片，保留所属 title / section。

    用于两种场景：① 全文无清晰标题时的退化切片；② 单个章节过长时的二次细分。
    """
    chunks: list[dict] = []
    step = _WINDOW_SIZE - _WINDOW_OVERLAP
    multi = len(text) > _WINDOW_SIZE
    for i, start in enumerate(range(0, len(text), step)):
        piece = text[start : start + _WINDOW_SIZE].strip()
        if piece:
            part_title = f"{title}（续{i + 1}）" if (title and multi and i) else title
            chunks.append({"title": part_title, "section": section, "text": piece})
    return chunks


def split_sections(full_text: str) -> list[dict]:
    """按顶级章节标题切片；标题不足 2 个时退化为滑窗，超长章节再做滑窗细分。

    Args:
        full_text: PDF 全文。

    Returns:
        切片列表，每项含 title / section / text。
    """
    matches = list(_TITLE_PATTERN.finditer(full_text))
    if len(matches) < 2:
        logger.info("未识别到足够章节标题（%d 个），退化为滑窗切片", len(matches))
        return _window_split(full_text)

    chunks: list[dict] = []
    for i, m in enumerate(matches):
        title = m.group(0).strip()
        if _is_skip_section(title):
            continue  # 参考文献/附录/致谢不入索引
        section = _guess_section(title)
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
        text = full_text[body_start:body_end].strip()
        if not text:
            continue
        if len(text) > _MAX_CHUNK:
            chunks.extend(_window_split(text, title=title, section=section))
        else:
            chunks.append({"title": title, "section": section, "text": text})
    return chunks
