"""切片结构化标注（Phase 2）。

调用 DeepSeek（reasoner）为单个论文切片打结构化标签（章节/摘要/方法/关键词）。
reasoner 不支持 response_format=json_object，改为文本输出+健壮 JSON 提取。
"""

import json
import logging
import time

from config import DEEPSEEK_REASONER_MODEL, LLM_MAX_RETRIES, get_llm_client
from rag.chunker import SECTIONS

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT: str = (
    "你是数学建模竞赛（CUMCM）论文分析专家。请阅读给出的论文片段，"
    f"判断它属于哪个章节（必须从以下选择一个：{'、'.join(SECTIONS)}），"
    "并给出一句话摘要、用到的建模方法、关键词。"
    "只能返回 JSON，不要附加解释。结构如下：\n"
    "{\n"
    f'  "section": "{"|".join(SECTIONS)}",\n'
    '  "summary": "一句话摘要",\n'
    '  "methods": ["方法1", ...],\n'
    '  "keywords": ["关键词1", ...]\n'
    "}"
)


def _extract_json(raw: str) -> dict:
    """从 LLM 原始输出中提取 JSON，兼容 ```json 围栏与前后多余文字。"""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        end_idx = next(
            (i for i in range(1, len(lines)) if lines[i].strip() == "```"),
            len(lines),
        )
        text = "\n".join(lines[1:end_idx])
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise ValueError(f"no JSON object found: {raw[:100]!r}")
    return json.loads(text[start : end + 1])


def annotate_chunk(text: str, guessed_section: str) -> dict:
    """调用 DeepSeek（reasoner）对切片做结构化标注，失败时退回基于正则的猜测。

    Args:
        text: 切片正文。
        guessed_section: 正则切片阶段猜测的章节，用作兜底。

    Returns:
        含 section / summary / methods / keywords 的字典。
    """
    client = get_llm_client(DEEPSEEK_REASONER_MODEL)
    fallback_section = guessed_section if guessed_section in SECTIONS else SECTIONS[0]
    fallback = {"section": fallback_section, "summary": "", "methods": [], "keywords": []}

    for attempt in range(1, LLM_MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=DEEPSEEK_REASONER_MODEL,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": text[:4000]},
                ],
                # reasoner 不支持 response_format=json_object，改为健壮文本解析
                temperature=0.2,
            )
            data = _extract_json(response.choices[0].message.content or "{}")
            section = data.get("section")
            return {
                "section": section if section in SECTIONS else fallback_section,
                "summary": str(data.get("summary", "")),
                "methods": [str(x) for x in (data.get("methods") or [])],
                "keywords": [str(x) for x in (data.get("keywords") or [])],
            }
        except Exception as exc:  # noqa: BLE001 - 标注失败不应中断整篇入库
            logger.warning("切片标注失败（第 %d/%d 次）：%s", attempt, LLM_MAX_RETRIES, exc)
            if attempt < LLM_MAX_RETRIES:
                time.sleep(2 ** (attempt - 1))

    logger.warning("切片标注重试耗尽，使用兜底标注（section=%s）", fallback_section)
    return fallback
