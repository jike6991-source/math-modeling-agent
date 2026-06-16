"""题目分析 Agent。

接收建模题目原文，调用 DeepSeek 分析，输出结构化结果：
题目类型、关键变量列表、建议建模方法。
"""

import json
import logging
import time

from config import DEEPSEEK_MODEL, LLM_MAX_RETRIES, get_llm_client

logger = logging.getLogger(__name__)

# 允许的题目类型，用于校验 LLM 输出
PROBLEM_TYPES: tuple[str, ...] = ("优化", "预测", "评价", "分类")

_SYSTEM_PROMPT: str = (
    "你是数学建模竞赛（CUMCM）的资深分析专家。"
    "请阅读用户给出的建模题目，判断题目类型、提取关键变量、给出建议的建模方法。"
    f"题目类型必须从以下四类中选择一个：{'、'.join(PROBLEM_TYPES)}。"
    "只能返回 JSON，不要附加任何解释性文字。JSON 结构如下：\n"
    "{\n"
    '  "problem_type": "优化|预测|评价|分类",\n'
    '  "key_variables": ["变量1", "变量2", ...],\n'
    '  "suggested_methods": ["方法1", "方法2", ...]\n'
    "}"
)


def _call_llm(problem_text: str) -> str:
    """调用 DeepSeek 获取分析结果原始文本，带重试逻辑。

    Args:
        problem_text: 建模题目原文。

    Returns:
        LLM 返回的 JSON 字符串。

    Raises:
        RuntimeError: 多次重试后仍失败时抛出。
    """
    client = get_llm_client()
    last_error: Exception | None = None

    for attempt in range(1, LLM_MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": problem_text},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
            )
            return response.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001 - 统一捕获后重试
            last_error = exc
            logger.warning("题目分析 LLM 调用失败（第 %d/%d 次）：%s", attempt, LLM_MAX_RETRIES, exc)
            if attempt < LLM_MAX_RETRIES:
                time.sleep(2 ** (attempt - 1))  # 指数退避：1s、2s、4s...

    raise RuntimeError(f"题目分析 LLM 调用失败，已重试 {LLM_MAX_RETRIES} 次") from last_error


def _parse_and_validate(raw: str) -> dict:
    """解析并校验 LLM 返回的 JSON。

    Args:
        raw: LLM 返回的 JSON 字符串。

    Returns:
        规范化后的分析结果字典。

    Raises:
        ValueError: JSON 解析失败或字段不合法时抛出。
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"题目分析返回内容不是合法 JSON：{raw!r}") from exc

    problem_type = data.get("problem_type")
    if problem_type not in PROBLEM_TYPES:
        raise ValueError(f"题目类型非法：{problem_type!r}，应为 {PROBLEM_TYPES} 之一")

    key_variables = data.get("key_variables") or []
    suggested_methods = data.get("suggested_methods") or []
    if not isinstance(key_variables, list) or not isinstance(suggested_methods, list):
        raise ValueError("key_variables 与 suggested_methods 必须为列表")

    return {
        "problem_type": problem_type,
        "key_variables": [str(v) for v in key_variables],
        "suggested_methods": [str(m) for m in suggested_methods],
    }


def analyze(problem_text: str) -> dict:
    """分析建模题目。

    调用 DeepSeek 识别题目类型、提取关键变量、给出建议建模方法。

    Args:
        problem_text: 建模题目原文。

    Returns:
        分析结果字典，包含：
        - problem_type (str): 题目类型（优化/预测/评价/分类）
        - key_variables (list[str]): 关键变量列表
        - suggested_methods (list[str]): 建议建模方法列表

    Raises:
        ValueError: 题目为空，或 LLM 返回结果无法解析/校验时抛出。
        RuntimeError: LLM 调用重试后仍失败时抛出。
    """
    if not problem_text or not problem_text.strip():
        raise ValueError("题目原文不能为空")

    logger.info("开始分析题目（长度 %d 字符）", len(problem_text))
    raw = _call_llm(problem_text)
    result = _parse_and_validate(raw)
    logger.info("题目分析完成：类型=%s，变量数=%d", result["problem_type"], len(result["key_variables"]))
    return result
