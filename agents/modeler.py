"""建模 Agent。

根据题目原文与分析结果，调用 DeepSeek 生成数学模型和可执行的求解代码。
"""

import json
import logging
import time

from config import DEEPSEEK_MODEL, LLM_MAX_RETRIES, get_llm_client

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT: str = (
    "你是数学建模竞赛（CUMCM）的资深建模专家。"
    "请根据用户给出的题目原文及其分析结果，建立完整的数学模型，并编写可直接运行的 Python 求解代码。\n"
    "要求：\n"
    "1. 数学模型用 Markdown 表述，包含模型假设、符号说明、目标函数、约束条件、求解思路。\n"
    "2. 求解代码必须自包含、可独立运行，只依赖常见库（numpy、scipy、matplotlib 等）；"
    "若题目缺少具体数据，可用合理的模拟数据并在代码注释中说明。\n"
    "3. 代码中 matplotlib 图表须设置中文字体（plt.rcParams['font.sans-serif']=['SimHei']，"
    "plt.rcParams['axes.unicode_minus']=False），并将图表保存为 PNG 文件。\n"
    "只能返回 JSON，不要附加任何解释性文字。JSON 结构如下：\n"
    "{\n"
    '  "model_description": "Markdown 格式的数学模型",\n'
    '  "solver_code": "完整的 Python 求解代码",\n'
    '  "expected_outputs": ["产出说明1", "产出说明2", ...]\n'
    "}"
)


def _build_user_prompt(problem_text: str, analysis: dict, references: str | None = None) -> str:
    """组装发送给 LLM 的用户消息。

    Args:
        problem_text: 建模题目原文。
        analysis: 题目分析 Agent 的输出。
        references: 检索到的优秀论文参考片段，可为 None。

    Returns:
        包含题目、分析结果与参考片段的提示文本。
    """
    parts = [
        f"题目原文：\n{problem_text}",
        f"分析结果（JSON）：\n{json.dumps(analysis, ensure_ascii=False, indent=2)}",
    ]
    if references and references.strip():
        parts.append(
            "以下为往年优秀论文的相关片段，仅供借鉴建模思路与方法，"
            "不可照抄，须结合本题实际：\n" + references
        )
    return "\n\n".join(parts)


def _call_llm(problem_text: str, analysis: dict, references: str | None = None) -> str:
    """调用 DeepSeek 获取建模结果原始文本，带重试逻辑。

    Args:
        problem_text: 建模题目原文。
        analysis: 题目分析结果。
        references: 检索到的参考片段，可为 None。

    Returns:
        LLM 返回的 JSON 字符串。

    Raises:
        RuntimeError: 多次重试后仍失败时抛出。
    """
    client = get_llm_client()
    user_prompt = _build_user_prompt(problem_text, analysis, references)
    last_error: Exception | None = None

    for attempt in range(1, LLM_MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
            )
            return response.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001 - 统一捕获后重试
            last_error = exc
            logger.warning("建模 LLM 调用失败（第 %d/%d 次）：%s", attempt, LLM_MAX_RETRIES, exc)
            if attempt < LLM_MAX_RETRIES:
                time.sleep(2 ** (attempt - 1))  # 指数退避：1s、2s、4s...

    raise RuntimeError(f"建模 LLM 调用失败，已重试 {LLM_MAX_RETRIES} 次") from last_error


def _parse_and_validate(raw: str) -> dict:
    """解析并校验 LLM 返回的 JSON。

    Args:
        raw: LLM 返回的 JSON 字符串。

    Returns:
        规范化后的建模结果字典。

    Raises:
        ValueError: JSON 解析失败或关键字段缺失时抛出。
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"建模返回内容不是合法 JSON：{raw!r}") from exc

    model_description = data.get("model_description")
    solver_code = data.get("solver_code")
    if not model_description or not isinstance(model_description, str):
        raise ValueError("model_description 缺失或类型错误")
    if not solver_code or not isinstance(solver_code, str):
        raise ValueError("solver_code 缺失或类型错误")

    expected_outputs = data.get("expected_outputs") or []
    if not isinstance(expected_outputs, list):
        raise ValueError("expected_outputs 必须为列表")

    return {
        "model_description": model_description,
        "solver_code": solver_code,
        "expected_outputs": [str(o) for o in expected_outputs],
    }


def build_model(problem_text: str, analysis: dict, references: str | None = None) -> dict:
    """生成数学模型与求解代码。

    根据题目原文与分析结果，调用 DeepSeek 建立数学模型并编写求解代码。

    Args:
        problem_text: 建模题目原文。
        analysis: 题目分析 Agent 的输出（problem_type、key_variables、suggested_methods）。
        references: 检索到的优秀论文参考片段，可选；提供时供 LLM 借鉴建模思路。

    Returns:
        建模结果字典，包含：
        - model_description (str): Markdown 格式的数学模型
        - solver_code (str): 可独立运行的 Python 求解代码
        - expected_outputs (list[str]): 代码预期产出说明

    Raises:
        ValueError: 输入为空，或 LLM 返回结果无法解析/校验时抛出。
        RuntimeError: LLM 调用重试后仍失败时抛出。
    """
    if not problem_text or not problem_text.strip():
        raise ValueError("题目原文不能为空")
    if not analysis:
        raise ValueError("分析结果不能为空")

    logger.info("开始建模：题目类型=%s", analysis.get("problem_type", "未知"))
    raw = _call_llm(problem_text, analysis, references)
    result = _parse_and_validate(raw)
    logger.info("建模完成：模型描述 %d 字符，代码 %d 字符", len(result["model_description"]), len(result["solver_code"]))
    return result
