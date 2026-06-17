"""报告 Agent。

将题目、分析结果、建模结果与代码执行结果组装为符合国赛模板的
结构化 Markdown 论文，调用 DeepSeek 完成正文撰写。
"""

import json
import logging
import time

from config import DEEPSEEK_MODEL, LLM_MAX_RETRIES, TEMPLATES_DIR, get_llm_client

logger = logging.getLogger(__name__)

_TEMPLATE_PATH = TEMPLATES_DIR / "cumcm_template.md"

# 模板读取失败时的兜底结构
_FALLBACK_TEMPLATE: str = (
    "# {题目标题}\n\n## 摘要\n\n**关键词：**\n\n"
    "## 一、问题重述\n## 二、问题分析\n## 三、模型假设\n## 四、符号说明\n"
    "## 五、模型建立与求解\n## 六、模型检验与灵敏度分析\n"
    "## 七、模型评价\n## 参考文献\n## 附录\n"
)


def _load_template() -> str:
    """读取国赛论文模板，失败时返回兜底结构。

    Returns:
        Markdown 模板文本。
    """
    try:
        return _TEMPLATE_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("读取论文模板失败，使用兜底结构：%s", exc)
        return _FALLBACK_TEMPLATE


def _build_system_prompt(template: str) -> str:
    """构造系统提示，要求 LLM 按模板撰写论文。

    Args:
        template: 论文模板文本。

    Returns:
        系统提示文本。
    """
    return (
        "你是数学建模竞赛（CUMCM）的论文撰写专家。"
        "请根据用户提供的题目、分析结果、数学模型与代码运行结果，撰写一篇完整的国赛论文。\n"
        "要求：\n"
        "1. 严格遵循下面的模板结构（章节标题、顺序保持一致），将占位符替换为实际内容。\n"
        "2. 摘要需概述问题、方法、主要结论；关键词 3-5 个。\n"
        "3. 模型假设、符号说明、模型建立与求解须与提供的数学模型一致。\n"
        "4. 模型检验与灵敏度分析须结合代码运行结果（数值结论、图表）。\n"
        "5. 若提供了图表文件，用 Markdown 图片语法在正文相应位置引用，如 "
        "`![灵敏度分析](charts/sensitivity.png)`。\n"
        "6. 附录中附上完整求解代码。\n"
        "7. 只输出 Markdown 论文正文，不要附加任何额外说明或代码块包裹整篇文档。\n\n"
        f"=== 论文模板 ===\n{template}"
    )


def _build_user_prompt(
    problem_text: str,
    analysis: dict,
    model_result: dict,
    exec_result: dict | None,
    references: str | None = None,
) -> str:
    """组装发送给 LLM 的用户消息。

    Args:
        problem_text: 题目原文。
        analysis: 题目分析结果。
        model_result: 建模结果。
        exec_result: 代码执行结果，可为 None。
        references: 检索到的优秀论文参考片段，可为 None。

    Returns:
        提示文本。
    """
    parts = [
        f"题目原文：\n{problem_text}",
        f"分析结果（JSON）：\n{json.dumps(analysis, ensure_ascii=False, indent=2)}",
        f"数学模型：\n{model_result.get('model_description', '')}",
        f"求解代码：\n{model_result.get('solver_code', '')}",
    ]
    if exec_result:
        stdout = (exec_result.get("stdout") or "").strip()
        artifacts = exec_result.get("artifacts") or []
        parts.append(f"代码运行输出：\n{stdout if stdout else '（无标准输出）'}")
        if artifacts:
            parts.append("生成的图表文件：\n" + "\n".join(f"- {a}" for a in artifacts))
    if references and references.strip():
        parts.append(
            "以下为往年优秀论文的相关片段，可借鉴其行文结构与表述方式，"
            "不可照抄，须忠实于本题的模型与结果：\n" + references
        )
    return "\n\n".join(parts)


def _call_llm(system_prompt: str, user_prompt: str) -> str:
    """调用 DeepSeek 生成论文正文，带重试逻辑。

    Args:
        system_prompt: 系统提示。
        user_prompt: 用户提示。

    Returns:
        Markdown 论文正文。

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
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.4,
            )
            return response.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001 - 统一捕获后重试
            last_error = exc
            logger.warning("报告 LLM 调用失败（第 %d/%d 次）：%s", attempt, LLM_MAX_RETRIES, exc)
            if attempt < LLM_MAX_RETRIES:
                time.sleep(2 ** (attempt - 1))  # 指数退避：1s、2s、4s...

    raise RuntimeError(f"报告 LLM 调用失败，已重试 {LLM_MAX_RETRIES} 次") from last_error


def build_report(
    problem_text: str,
    analysis: dict,
    model_result: dict,
    exec_result: dict | None = None,
    references: str | None = None,
) -> str:
    """组装结构化论文报告。

    根据题目、分析结果、数学模型与代码执行结果，按国赛模板撰写完整论文。

    Args:
        problem_text: 题目原文。
        analysis: 题目分析 Agent 的输出。
        model_result: 建模 Agent 的输出（model_description、solver_code 等）。
        exec_result: 代码执行结果（stdout、artifacts 等），可选；
            提供时论文会结合数值结论与图表。
        references: 检索到的优秀论文参考片段，可选；提供时供 LLM 借鉴行文结构。

    Returns:
        Markdown 格式的论文正文。

    Raises:
        ValueError: 必要输入为空时抛出。
        RuntimeError: LLM 调用重试后仍失败时抛出。
    """
    if not problem_text or not problem_text.strip():
        raise ValueError("题目原文不能为空")
    if not analysis or not model_result:
        raise ValueError("分析结果与建模结果不能为空")

    logger.info("开始撰写论文报告")
    template = _load_template()
    system_prompt = _build_system_prompt(template)
    user_prompt = _build_user_prompt(problem_text, analysis, model_result, exec_result, references)
    report = _call_llm(system_prompt, user_prompt)
    logger.info("论文报告撰写完成：%d 字符", len(report))
    return report
