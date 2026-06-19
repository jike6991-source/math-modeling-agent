"""建模 Agent。

根据题目原文与分析结果，调用 DeepSeek 生成数学模型和可执行的求解代码。
"""

import json
import logging
import time
from pathlib import Path

from config import DEEPSEEK_REASONER_MODEL, LLM_MAX_RETRIES, get_llm_client

logger = logging.getLogger(__name__)

# 数据文件预览的最大行数，用于让模型据实编写正确的读取/解析逻辑
_DATA_PREVIEW_ROWS: int = 15


def _preview_data_file(path: str, max_rows: int = _DATA_PREVIEW_ROWS) -> str:
    """读取数据文件前若干行的原始内容预览（header=None），供模型据实编写解析逻辑。

    用 header=None 展示真实排版（含可能的标题/表头行），避免模型臆测文件结构。
    读取失败不抛出，返回带错误说明的文本。

    Args:
        path: 数据文件绝对路径（CSV/Excel）。
        max_rows: 预览的最大行数。

    Returns:
        预览文本（含形状与前若干行）；失败时为错误说明。
    """
    try:
        import pandas as pd

        suffix = Path(path).suffix.lower()
        if suffix == ".csv":
            df = pd.read_csv(path, header=None, nrows=max_rows)
            shape_note = f"（前 {max_rows} 行预览）"
        else:
            full = pd.read_excel(path, header=None)
            df = full.head(max_rows)
            shape_note = f"（完整形状 {full.shape}，前 {max_rows} 行预览）"
        return f"{shape_note}\n{df.to_string(max_cols=30)}"
    except Exception as exc:  # noqa: BLE001 - 预览失败不应阻断建模
        logger.warning("数据文件预览失败 %s：%s", path, exc)
        return f"（预览失败：{exc}）"

_SYSTEM_PROMPT: str = (
    "你是数学建模竞赛（CUMCM）的资深建模专家。"
    "请根据用户给出的题目原文及其分析结果，建立完整的数学模型，并编写可直接运行的 Python 求解代码。\n"
    "硬性要求：\n"
    "1. 必须采用分析结果中 recommended_methods 给出的正式数学方法和 recommended_libraries"
    "给出的库；严禁用简单的贪心、暴力枚举、随机搜索来替代正式的数学建模方法"
    "（如线性/整数规划、动态规划、ARIMA、AHP/TOPSIS/熵权法、聚类/判别分析等）。\n"
    "2. 数学模型用 Markdown 表述，包含模型假设、符号说明、目标函数、约束条件、求解思路。\n"
    "3. 求解代码必须自包含、可独立运行，且结构完整，依次包含：\n"
    "   (a) 数据加载与预处理；(b) 模型定义（明确目标函数与约束条件）；"
    "(c) 模型求解；(d) 结果验证（如约束满足性检查、与实际数据回代对比）；"
    "(e) 至少 5 张不同类型的可视化图表（如分布图、相关性热力图、收敛曲线、"
    "结果对比图、灵敏度分析图等），每张图各自用 plt.savefig 保存为独立 PNG 文件。\n"
    "4. 若用户提供了数据文件路径，必须读取这些真实数据进行建模与求解，"
    "严禁用 np.random 等手段编造模拟数据；只有在完全没有提供数据文件时，"
    "才可使用合理的模拟数据并在注释中说明。\n"
    "5. 若用户提供了参考论文使用的方法（方法下限），所建模型的方法层次不得低于这些参考方法。\n"
    "6. 代码中 matplotlib 图表须设置中文字体（plt.rcParams['font.sans-serif']=['SimHei']，"
    "plt.rcParams['axes.unicode_minus']=False），用 plt.savefig 将图表保存为 PNG 文件，"
    "不要调用 plt.show()（在无界面环境会阻塞）。图表须直接保存到当前工作目录，"
    "使用相对文件名（如 plt.savefig('图1_需求热力图.png')），不要创建子目录、"
    "也不要用绝对路径保存图片；且这 5 张图必须无条件生成（不要放在可能不满足的"
    "条件分支里）。\n"
    "7. 代码必须在 150 秒内整体运行完成：若使用 pulp/scipy 等求解器，须为每个子问题"
    "设置较短的求解时间上限（如 PULP_CBC_CMD(msg=False, timeLimit=20)），求解器到时返回"
    "当前可行解即可继续；避免规模过大或无时限的精确求解导致超时拿不到任何图表。\n"
    "8. 代码结构须支持图表自动修复（严格遵守）：\n"
    "   (a) 求解阶段完成后，立即用 pickle 序列化所有求解结果到当前目录的 _results.pkl：\n"
    "       import pickle\n"
    "       _results = {'N1': N1, 'N2_val': N2_val, ...}  # 把所有后续画图需要的变量都放进去\n"
    "       with open('_results.pkl', 'wb') as _f: pickle.dump(_results, _f)\n"
    "   (b) 每张图的生成代码用独立的 try-except 包裹，成功时 print('[CHART_OK:文件名.png]')，"
    "失败时 print('[CHART_FAIL:文件名.png]') 后紧接着 print(traceback.format_exc())；"
    "需要在文件头 import traceback。\n"
    "   (c) 示例模板：\n"
    "       try:\n"
    "           plt.figure(...)\n"
    "           # ... 画图逻辑 ...\n"
    "           plt.savefig('图1_需求热力图.png', dpi=150, bbox_inches='tight')\n"
    "           plt.close()\n"
    "           print('[CHART_OK:图1_需求热力图.png]')\n"
    "       except Exception as _e:\n"
    "           plt.close('all')\n"
    "           print('[CHART_FAIL:图1_需求热力图.png]')\n"
    "           print(traceback.format_exc())\n"
    "请严格按以下分段格式输出（不要用 JSON，不要给代码加 Markdown 围栏），"
    "三个标记行各自独占一行，顺序固定：\n"
    "===MODEL_DESCRIPTION===\n"
    "（此处为 Markdown 格式的数学模型）\n"
    "===SOLVER_CODE===\n"
    "（此处为完整的 Python 求解代码，纯代码，不要任何 ``` 围栏）\n"
    "===EXPECTED_OUTPUTS===\n"
    "（此处为预期产出说明，每行一条，以 - 开头）"
)

# 分段输出的标记
_MARK_MODEL: str = "===MODEL_DESCRIPTION==="
_MARK_CODE: str = "===SOLVER_CODE==="
_MARK_OUTPUTS: str = "===EXPECTED_OUTPUTS==="


def _build_user_prompt(
    problem_text: str,
    analysis: dict,
    references: str | None = None,
    data_files: list[str] | None = None,
    method_floor: list[str] | None = None,
) -> str:
    """组装发送给 LLM 的用户消息。

    Args:
        problem_text: 建模题目原文。
        analysis: 题目分析 Agent 的输出。
        references: 检索到的优秀论文参考片段，可为 None。
        data_files: 题目附带数据文件的绝对路径列表，可为 None；
            非空时要求代码读取真实数据、禁止模拟数据。
        method_floor: RAG 参考论文使用的方法列表，作为方法下限，可为 None。

    Returns:
        包含题目、分析结果、数据文件、方法下限与参考片段的提示文本。
    """
    recommended_methods = analysis.get("recommended_methods") or []
    recommended_libraries = analysis.get("recommended_libraries") or []
    parts = [
        f"题目原文：\n{problem_text}",
        f"分析结果（JSON）：\n{json.dumps(analysis, ensure_ascii=False, indent=2)}",
    ]
    if recommended_methods:
        # 兼容 list[{"method","reason"}]（新格式）与 list[str]（旧格式）
        method_parts: list[str] = []
        for m in recommended_methods:
            if isinstance(m, dict):
                name = m.get("method", "")
                reason = m.get("reason", "")
                method_parts.append(f"{name}（{reason}）" if reason else name)
            else:
                method_parts.append(str(m))
        parts.append("必须采用的数学方法（recommended_methods）：" + "、".join(method_parts))
    if recommended_libraries:
        parts.append(
            "应优先使用的 Python 库（recommended_libraries）：" + "、".join(recommended_libraries)
        )
    if data_files:
        file_lines = "\n".join(f"- {p}" for p in data_files)
        parts.append(
            "本题提供了以下真实数据文件（绝对路径），代码必须读取这些数据进行建模与求解，"
            "严禁使用 np.random 等编造模拟数据：\n" + file_lines
        )
        previews = []
        for p in data_files:
            previews.append(f"【{p}】\n{_preview_data_file(p)}")
        parts.append(
            "数据文件内容预览（以 header=None 原样读取，请据此真实排版编写正确的"
            "读取与解析逻辑，注意可能存在的标题行/表头行/合并单元格）：\n"
            + "\n\n".join(previews)
        )
    if method_floor:
        parts.append(
            "参考论文使用的建模方法（方法下限，所用方法层次不得低于此）："
            + "、".join(method_floor)
        )
    if references and references.strip():
        parts.append(
            "以下为往年优秀论文的相关片段，仅供借鉴建模思路与方法，"
            "不可照抄，须结合本题实际：\n" + references
        )
    return "\n\n".join(parts)


def _call_llm(
    problem_text: str,
    analysis: dict,
    references: str | None = None,
    data_files: list[str] | None = None,
    method_floor: list[str] | None = None,
) -> str:
    """调用 DeepSeek（reasoner）获取建模结果原始文本，带重试逻辑。

    使用 deepseek-reasoner 强推理模型。该模型不支持 response_format=json_object，
    故以分段文本返回，由 _parse_and_validate 按标记解析。

    Args:
        problem_text: 建模题目原文。
        analysis: 题目分析结果。
        references: 检索到的参考片段，可为 None。
        data_files: 数据文件绝对路径列表，可为 None。
        method_floor: RAG 参考方法下限列表，可为 None。

    Returns:
        LLM 返回的原始文本（应包含 JSON）。

    Raises:
        RuntimeError: 多次重试后仍失败时抛出。
    """
    client = get_llm_client(DEEPSEEK_REASONER_MODEL)
    user_prompt = _build_user_prompt(problem_text, analysis, references, data_files, method_floor)
    last_error: Exception | None = None

    for attempt in range(1, LLM_MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=DEEPSEEK_REASONER_MODEL,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            )
            return response.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001 - 统一捕获后重试
            last_error = exc
            logger.warning("建模 LLM 调用失败（第 %d/%d 次）：%s", attempt, LLM_MAX_RETRIES, exc)
            if attempt < LLM_MAX_RETRIES:
                time.sleep(2 ** (attempt - 1))  # 指数退避：1s、2s、4s...

    raise RuntimeError(f"建模 LLM 调用失败，已重试 {LLM_MAX_RETRIES} 次") from last_error


def _strip_code_fence(code: str) -> str:
    """去除代码两端可能存在的 Markdown 围栏（```python ... ```）。

    Args:
        code: 可能含围栏的代码文本。

    Returns:
        去除围栏后的代码。
    """
    text = code.strip()
    if text.startswith("```"):
        # 去掉首行围栏（``` 或 ```python）
        text = text.split("\n", 1)[-1] if "\n" in text else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text.strip("\n")


def _parse_and_validate(raw: str) -> dict:
    """解析并校验 LLM 返回的分段文本。

    采用 ===MODEL_DESCRIPTION===/===SOLVER_CODE===/===EXPECTED_OUTPUTS=== 分段格式
    （而非 JSON）：reasoner 无法保证将大段 Python 代码安全转义进 JSON 字符串，
    分段格式可避免转义破坏导致的解析失败。

    Args:
        raw: LLM 返回的原始分段文本。

    Returns:
        规范化后的建模结果字典。

    Raises:
        ValueError: 缺少必要分段或字段为空时抛出。
    """
    code_idx = raw.find(_MARK_CODE)
    if code_idx == -1:
        raise ValueError(f"建模返回缺少 {_MARK_CODE} 分段：{raw[:300]!r}")

    model_idx = raw.find(_MARK_MODEL)
    outputs_idx = raw.find(_MARK_OUTPUTS)

    # 模型描述：MODEL 标记之后到 CODE 标记之前；无 MODEL 标记则取 CODE 之前全部
    desc_start = (model_idx + len(_MARK_MODEL)) if model_idx != -1 else 0
    model_description = raw[desc_start:code_idx].strip()

    # 求解代码：CODE 标记之后到 OUTPUTS 标记之前（若有）
    code_start = code_idx + len(_MARK_CODE)
    code_end = outputs_idx if outputs_idx != -1 else len(raw)
    solver_code = _strip_code_fence(raw[code_start:code_end])

    # 预期产出：OUTPUTS 标记之后，按行解析（去除 - 前缀）
    expected_outputs: list[str] = []
    if outputs_idx != -1:
        for line in raw[outputs_idx + len(_MARK_OUTPUTS):].splitlines():
            item = line.strip().lstrip("-*").strip()
            if item:
                expected_outputs.append(item)

    if not model_description:
        raise ValueError("model_description 缺失或为空")
    if not solver_code:
        raise ValueError("solver_code 缺失或为空")

    return {
        "model_description": model_description,
        "solver_code": solver_code,
        "expected_outputs": expected_outputs,
    }


def build_model(
    problem_text: str,
    analysis: dict,
    references: str | None = None,
    data_files: list[str] | None = None,
    method_floor: list[str] | None = None,
) -> dict:
    """生成数学模型与求解代码。

    根据题目原文与分析结果，调用 DeepSeek（reasoner）建立数学模型并编写求解代码。

    Args:
        problem_text: 建模题目原文。
        analysis: 题目分析 Agent 的输出（problem_type、key_variables、
            recommended_methods、recommended_libraries 等）。
        references: 检索到的优秀论文参考片段，可选；提供时供 LLM 借鉴建模思路。
        data_files: 题目附带数据文件的绝对路径列表，可选；非空时要求代码读取
            真实数据、禁止使用模拟数据。
        method_floor: RAG 参考论文使用的方法列表，作为方法下限，可选。

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

    logger.info(
        "开始建模：题目类型=%s，数据文件 %d 个，方法下限 %d 项",
        analysis.get("problem_type", "未知"),
        len(data_files or []),
        len(method_floor or []),
    )
    raw = _call_llm(problem_text, analysis, references, data_files, method_floor)
    result = _parse_and_validate(raw)
    logger.info("建模完成：模型描述 %d 字符，代码 %d 字符", len(result["model_description"]), len(result["solver_code"]))
    return result
