"""题目分析 Agent。

接收建模题目原文，调用 DeepSeek 分析，输出结构化结果：
题目类型、关键变量列表、建议建模方法（含适用理由）。
"""

import json
import logging
import time

from config import DEEPSEEK_REASONER_MODEL, LLM_MAX_RETRIES, get_llm_client

logger = logging.getLogger(__name__)

# 允许的题目类型，用于校验 LLM 输出
PROBLEM_TYPES: tuple[str, ...] = ("优化", "预测", "评价", "分类")

_SYSTEM_PROMPT: str = (
    "你是数学建模竞赛（CUMCM）的资深分析专家。"
    "请深入阅读用户给出的建模题目，分析其**具体结构与特征**（决策变量类型、约束形式、"
    "数据维度、优化目标结构等），然后：\n"
    "1. 判断题目类型（必须从以下四类中选择一个）："
    f"{'、'.join(PROBLEM_TYPES)}。\n"
    "2. 提取关键变量。\n"
    "3. 给出 2-3 个最适合本题的具体数学建模方法，每种方法必须说明它为什么适合这道题"
    "（结合题目具体特征，不能只说【常用】或【适合优化问题】这类泛化理由）。\n"
    "方法推荐质量要求：不要只推荐通用方法（如【整数规划】），要根据题目特征给出具体建模策略，"
    "例如：排班/覆盖问题→集合覆盖模型/列生成算法；网络流问题→最小费用最大流；"
    "选址问题→p-中位模型/p-中心模型；多周期时序预测→SARIMA/Prophet；"
    "多准则评价→熵权法-TOPSIS/AHP+TOPSIS；图像/分类→SVM/判别分析等。\n"
    "4. 给出对应的 Python 库名。\n"
    "只能返回 JSON，不要附加任何解释性文字。JSON 结构如下：\n"
    "{\n"
    '  "problem_type": "优化|预测|评价|分类",\n'
    '  "key_variables": ["变量1", "变量2", ...],\n'
    '  "suggested_methods": ["建模方向1", ...],\n'
    '  "recommended_methods": [\n'
    '    {"method": "具体方法名", "reason": "为何适合本题的具体理由"},\n'
    '    {"method": "具体方法名2", "reason": "为何适合本题的具体理由"}\n'
    "  ],\n"
    '  "recommended_libraries": ["库1", "库2", ...]\n'
    "}"
)


def _extract_json(raw: str) -> dict:
    """从 LLM 原始输出中提取 JSON，兼容 ```json 围栏与前后多余文字。

    Args:
        raw: LLM 原始输出文本。

    Returns:
        解析后的字典。

    Raises:
        ValueError: 未找到有效 JSON 对象时抛出。
    """
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        end_idx = next(
            (i for i in range(1, len(lines)) if lines[i].strip() == "```"),
            len(lines),
        )
        text = "\n".join(lines[1:end_idx])
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end < start:
        raise ValueError(f"未找到有效 JSON 对象：{raw[:200]!r}")
    return json.loads(text[start : end + 1])


def _call_llm(problem_text: str, method_floor: list[str] | None = None) -> str:
    """调用 DeepSeek 获取分析结果原始文本，带重试逻辑。

    Args:
        problem_text: 建模题目原文。
        method_floor: RAG 检索到的优秀论文方法下限列表，可为 None。

    Returns:
        LLM 返回的原始文本（应含 JSON）。

    Raises:
        RuntimeError: 多次重试后仍失败时抛出。
    """
    client = get_llm_client(DEEPSEEK_REASONER_MODEL)
    user_content = problem_text
    if method_floor:
        user_content += (
            "\n\n以下为优秀论文使用过的方法（方法参考下限），"
            "请在此基础上推荐同等或更高水平的具体方法：\n"
            + "、".join(method_floor)
        )
    last_error: Exception | None = None

    for attempt in range(1, LLM_MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=DEEPSEEK_REASONER_MODEL,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                # reasoner 不支持 response_format=json_object，改为文本输出+健壮解析
                temperature=0.2,
            )
            return response.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001 - 统一捕获后重试
            last_error = exc
            logger.warning("题目分析 LLM 调用失败（第 %d/%d 次）：%s", attempt, LLM_MAX_RETRIES, exc)
            if attempt < LLM_MAX_RETRIES:
                time.sleep(2 ** (attempt - 1))

    raise RuntimeError(f"题目分析 LLM 调用失败，已重试 {LLM_MAX_RETRIES} 次") from last_error


def _parse_and_validate(raw: str) -> dict:
    """解析并校验 LLM 返回的 JSON，将 recommended_methods 规范化为结构化列表。

    Args:
        raw: LLM 返回的原始文本。

    Returns:
        规范化后的分析结果字典。

    Raises:
        ValueError: JSON 解析失败或字段不合法时抛出。
    """
    try:
        data = _extract_json(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"题目分析返回内容解析失败：{raw[:200]!r}") from exc

    problem_type = data.get("problem_type")
    if problem_type not in PROBLEM_TYPES:
        raise ValueError(f"题目类型非法：{problem_type!r}，应为 {PROBLEM_TYPES} 之一")

    key_variables = data.get("key_variables") or []
    suggested_methods = data.get("suggested_methods") or []
    recommended_libraries = data.get("recommended_libraries") or []
    for name, value in (
        ("key_variables", key_variables),
        ("suggested_methods", suggested_methods),
        ("recommended_libraries", recommended_libraries),
    ):
        if not isinstance(value, list):
            raise ValueError(f"{name} 必须为列表")

    # recommended_methods: 规范化为 list[{"method": str, "reason": str}]
    raw_methods = data.get("recommended_methods") or []
    recommended_methods: list[dict] = []
    for m in raw_methods:
        if isinstance(m, dict):
            recommended_methods.append(
                {
                    "method": str(m.get("method", "")),
                    "reason": str(m.get("reason", "")),
                }
            )
        else:
            # 兼容旧式 list[str]
            recommended_methods.append({"method": str(m), "reason": ""})

    return {
        "problem_type": problem_type,
        "key_variables": [str(v) for v in key_variables],
        "suggested_methods": [str(m) for m in suggested_methods],
        "recommended_methods": recommended_methods,
        "recommended_libraries": [str(lib) for lib in recommended_libraries],
    }


def analyze(problem_text: str, method_floor: list[str] | None = None) -> dict:
    """分析建模题目。

    调用 DeepSeek（reasoner）识别题目类型、提取关键变量、深度推理推荐建模方法。

    Args:
        problem_text: 建模题目原文。
        method_floor: RAG 检索到的优秀论文用过的方法列表，作为推荐下限；可为 None。

    Returns:
        分析结果字典，包含：
        - problem_type (str): 题目类型（优化/预测/评价/分类）
        - key_variables (list[str]): 关键变量列表
        - suggested_methods (list[str]): 建议建模方向（概括性）
        - recommended_methods (list[dict]): 推荐的具体数学方法，每项含 method 与 reason
        - recommended_libraries (list[str]): 推荐的 Python 库列表

    Raises:
        ValueError: 题目为空，或 LLM 返回结果无法解析/校验时抛出。
        RuntimeError: LLM 调用重试后仍失败时抛出。
    """
    if not problem_text or not problem_text.strip():
        raise ValueError("题目原文不能为空")

    logger.info("开始分析题目（长度 %d 字符，方法下限 %d 个）", len(problem_text), len(method_floor or []))
    raw = _call_llm(problem_text, method_floor)
    result = _parse_and_validate(raw)
    logger.info(
        "题目分析完成：类型=%s，变量数=%d，推荐方法数=%d",
        result["problem_type"],
        len(result["key_variables"]),
        len(result["recommended_methods"]),
    )
    return result
