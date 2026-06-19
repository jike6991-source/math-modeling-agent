"""图表修复 Agent。

接收失败图表的报错信息，调用 LLM 生成仅包含图表修复逻辑的 Python 代码。
修复代码从 _results.pkl 加载求解结果，只重新生成失败的图表。
"""

import logging
import time

from config import DEEPSEEK_CHAT_MODEL, LLM_MAX_RETRIES, get_llm_client

logger = logging.getLogger(__name__)

_REPAIR_SYSTEM_PROMPT: str = (
    "你是 Python 数据可视化修复专家。用户会提供：\n"
    "1. 原始求解代码（仅供参考上下文，不要重新求解）\n"
    "2. 失败图表的文件名和报错 traceback\n"
    "你的任务：生成一段独立可运行的 Python 修复代码，要求：\n"
    "- 用 pickle.load 从当前目录的 _results.pkl 加载求解结果\n"
    "- 只生成失败的图表，不要重新求解任何优化问题\n"
    "- 每张图用 try-except 包裹，成功 print('[CHART_OK:文件名.png]')，"
    "失败 print('[CHART_FAIL:文件名.png]') 后紧接着 print(traceback.format_exc())\n"
    "- 设置中文字体：plt.rcParams['font.sans-serif']=['SimHei']，"
    "plt.rcParams['axes.unicode_minus']=False\n"
    "- 用 plt.savefig 保存到当前目录，不要 plt.show()\n"
    "- 只输出纯 Python 代码，不要任何 Markdown 围栏或解释文字\n"
    "- 根据 traceback 分析真实错误原因并修复，常见原因包括：\n"
    "  * 变量名不匹配（_results.pkl 中的 key 与代码中变量名不同）\n"
    "  * 数组维度/形状错误\n"
    "  * 字体缺失（改用其他中文字体或去掉中文标签）\n"
    "  * 数据类型错误（如对 None 值做数学运算）\n"
)


def _strip_code_fence(code: str) -> str:
    """去除代码两端可能存在的 Markdown 围栏。"""
    text = code.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1] if "\n" in text else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text.strip("\n")


def generate_repair_code(
    original_code: str,
    failed_charts: list[dict],
) -> str:
    """调用 LLM 生成图表修复代码。

    Args:
        original_code: 原始完整求解代码（供 LLM 理解上下文）。
        failed_charts: 失败图表列表，每项含 name 和 traceback。

    Returns:
        可独立运行的 Python 修复代码。

    Raises:
        RuntimeError: LLM 调用失败时抛出。
    """
    if not failed_charts:
        return ""

    failures_text = "\n\n".join(
        f"### {f['name']}\n```\n{f['traceback']}\n```"
        for f in failed_charts
    )

    user_prompt = (
        f"原始求解代码（仅供参考，不要重新求解）：\n"
        f"```python\n{original_code}\n```\n\n"
        f"以下图表生成失败，请修复：\n\n{failures_text}"
    )

    client = get_llm_client(DEEPSEEK_CHAT_MODEL)
    last_error: Exception | None = None

    for attempt in range(1, LLM_MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=DEEPSEEK_CHAT_MODEL,
                messages=[
                    {"role": "system", "content": _REPAIR_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
            )
            raw = response.choices[0].message.content or ""
            return _strip_code_fence(raw)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning(
                "图表修复 LLM 调用失败（第 %d/%d 次）：%s",
                attempt, LLM_MAX_RETRIES, exc,
            )
            if attempt < LLM_MAX_RETRIES:
                time.sleep(2 ** (attempt - 1))

    raise RuntimeError(
        f"图表修复 LLM 调用失败，已重试 {LLM_MAX_RETRIES} 次"
    ) from last_error
