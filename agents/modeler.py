"""建模 Agent — 两阶段生成：方法规划（JSON验证）→ 代码生成（方法已锁定）。"""

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


# ── 第一阶段：方法规划 ────────────────────────────────────────────────────────

_PLAN_SYSTEM_PROMPT: str = (
    "你是数学建模方法规划专家。根据题目和分析结果，选择最合适的求解方案。\n\n"
    "只输出纯 JSON，不要任何其他文字、Markdown围栏或解释：\n"
    "{\n"
    '  "solver": "pulp" | "scipy" | "statsmodels" | "sklearn" | "networkx" | "cpsat",\n'
    '  "variable_design": "aggregate_integer" | "continuous" | "not_applicable",\n'
    '  "sub_problems": ["子问题1简述", "子问题2简述"],\n'
    '  "estimated_total_vars": 预估总变量数（整数）,\n'
    '  "approach_summary": "一句话说明整体求解思路"\n'
    "}\n\n"
    "方法选择指南：\n"
    "- 排班/调度/指派/选址/背包/切割等组合优化 → solver: pulp, variable_design: aggregate_integer\n"
    "- 连续优化/参数拟合/非线性规划 → solver: scipy, variable_design: continuous\n"
    "- 时间序列预测/ARIMA → solver: statsmodels, variable_design: not_applicable\n"
    "- 分类/回归/聚类/机器学习 → solver: sklearn, variable_design: not_applicable\n"
    "- 图论/网络流/最短路 → solver: networkx, variable_design: not_applicable\n"
    "- 纯约束满足问题（排课/数独/无优化目标）→ solver: cpsat, variable_design: not_applicable\n\n"
    "关键约束：\n"
    "- 有优化目标的排班/调度问题必须选 pulp，不要选 cpsat\n"
    "- 选 pulp 时 variable_design 必须为 aggregate_integer（聚合整数变量，非逐个体二进制变量）\n"
    "- estimated_total_vars 不应超过 5000，超过说明建模方式有问题需要简化\n"
    "- 禁止使用：列生成、分支定价、Benders分解、Dantzig-Wolfe分解\n"
)


def _validate_plan(plan: dict, analysis: dict) -> list[str]:
    """验证规划方案的合理性，返回错误列表（空列表表示通过）。

    Args:
        plan: LLM 返回的规划 JSON。
        analysis: 题目分析结果。

    Returns:
        错误描述列表，空列表表示验证通过。
    """
    errors: list[str] = []
    analysis_text = json.dumps(analysis, ensure_ascii=False).lower()

    scheduling_keywords = ["排班", "调度", "指派", "排程", "轮班", "人员分配", "工人", "临时工"]
    is_scheduling = any(kw in analysis_text for kw in scheduling_keywords)

    if is_scheduling:
        if plan.get("solver") == "cpsat":
            errors.append(
                "检测到排班/调度类问题但选择了cpsat。"
                "有优化目标的排班问题必须使用pulp（聚合整数规划），而非cpsat。"
                "请将solver改为pulp，variable_design改为aggregate_integer"
            )
        if plan.get("variable_design") not in ("aggregate_integer", None):
            errors.append(
                "排班/调度类问题的variable_design必须为aggregate_integer（聚合整数变量）。"
                "禁止为每个工人/个体创建独立的二进制变量"
            )

    est_vars = plan.get("estimated_total_vars", 0)
    if isinstance(est_vars, (int, float)) and est_vars > 10000:
        errors.append(
            f"预估变量数{est_vars}过多（上限5000），说明建模方式有问题。"
            "请改用聚合变量减少规模"
        )

    valid_solvers = {"pulp", "scipy", "statsmodels", "sklearn", "networkx", "cpsat"}
    if plan.get("solver") not in valid_solvers:
        errors.append(f"solver必须为以下之一：{valid_solvers}")

    return errors


def _plan_approach(problem_text: str, analysis: dict) -> dict:
    """第一阶段：调用 LLM 规划求解方案，带验证重试（最多3次）。

    Args:
        problem_text: 题目原文。
        analysis: 题目分析结果。

    Returns:
        通过验证的规划方案 dict；3次均未通过则返回安全默认方案。
    """
    client = get_llm_client(DEEPSEEK_REASONER_MODEL)
    error_feedback = ""

    for attempt in range(1, 4):
        user_content = (
            f"题目摘要（前800字）：\n{problem_text[:800]}\n\n"
            f"分析结果：\n{json.dumps(analysis, ensure_ascii=False, indent=2)}\n"
        )
        if error_feedback:
            user_content += f"\n⚠ 你上一次的方案有问题：{error_feedback}\n请修正后重新输出JSON。"

        try:
            response = client.chat.completions.create(
                model=DEEPSEEK_REASONER_MODEL,
                messages=[
                    {"role": "system", "content": _PLAN_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
            )
            raw = (response.choices[0].message.content or "").strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1]
                if raw.rstrip().endswith("```"):
                    raw = raw.rstrip()[:-3]
            plan = json.loads(raw.strip())
        except Exception as exc:  # noqa: BLE001
            logger.warning("规划阶段第%d次解析失败：%s", attempt, exc)
            error_feedback = f"JSON解析失败({exc})，请确保输出纯JSON"
            continue

        errors = _validate_plan(plan, analysis)
        if not errors:
            logger.info("规划阶段通过（第%d次）：%s", attempt, plan)
            return plan

        error_feedback = "；".join(errors)
        logger.warning("规划阶段第%d次未通过：%s", attempt, error_feedback)

    logger.warning("规划阶段3次均未通过，使用默认方案")
    return {
        "solver": "pulp",
        "variable_design": "aggregate_integer",
        "sub_problems": [],
        "estimated_total_vars": 500,
        "approach_summary": "默认聚合整数规划方案",
    }


# ── 第二阶段：代码生成 ────────────────────────────────────────────────────────

_CODE_SYSTEM_PROMPT_TEMPLATE: str = (
    "【已确认的求解方案 — 不可更改】\n"
    "{locked_plan}\n"
    "你必须严格按照上述已确认方案实现代码，不得更换求解器或变量设计方式。\n\n"
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
    "   特别注意：排班/调度/指派类 MILP 总二进制变量数必须控制在 5000 以内，"
    "用聚合整数变量而非逐个体二进制变量（详见已确认方案），否则 CBC 在 60 秒内不可能求解。\n"
    "9. 代码结构须支持图表自动修复（严格遵守）：\n"
    "   (a) 求解阶段完成后，立即用 pickle 序列化所有求解结果到当前目录的 _results.pkl：\n"
    "       import pickle\n"
    "       _results = {'N1': N1, 'N2_val': N2_val, ...}  # 把所有后续画图需要的变量都放进去\n"
    "       with open('_results.pkl', 'wb') as _f: pickle.dump(_results, _f)\n"
    "   (b) 每张图的生成代码用独立的 try-except 包裹，成功时 print('[CHART_OK:文件名.png]')，"
    "失败时 print('[CHART_FAIL:文件名.png]') 后紧接着 print(traceback.format_exc())；"
    "需要在文件头 import traceback。\n"
    "   (d) 纯数据分析的图表（需求热力图、数据分布、相关性矩阵等）必须放在所有求解代码之前生成，"
    "这是硬性要求而非建议——这些图不依赖求解结果，应作为代码的第一批 savefig 输出，"
    "确保即使求解全部超时也至少有数据分析图可用。\n"
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
    "11. _results.pkl 增量写入（必须严格遵守，违反等同于代码 bug）：\n"
    "   - 代码最开头就创建 _results 字典并写入基础数据（demand 等），在任何求解之前就 pickle.dump 一次\n"
    "   - 每个子问题求解完毕后立即追加该问题结果并重新 pickle.dump\n"
    "   - 每个子问题的图表在该问题求解后立即生成，不要堆到代码末尾\n"
    "   必须遵守的代码结构模板：\n"
    "       import pickle\n"
    "       _results = {'demand': demand}\n"
    "       with open('_results.pkl','wb') as f: pickle.dump(_results, f)\n"
    "       # --- 数据分析图表（在求解之前）---\n"
    "       try: 热力图/分布图... savefig... except: ...\n"
    "       # --- 问题1 ---\n"
    "       ...求解...\n"
    "       _results['problem1'] = {...}\n"
    "       with open('_results.pkl','wb') as f: pickle.dump(_results, f)\n"
    "       try: 问题1图表... except: ...\n"
    "       # --- 问题2 ---\n"
    "       ...求解...\n"
    "       _results['problem2'] = {...}\n"
    "       with open('_results.pkl','wb') as f: pickle.dump(_results, f)\n"
    "       try: 问题2图表... except: ...\n"
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
    system_prompt: str,
    problem_text: str,
    analysis: dict,
    references: str | None = None,
    data_files: list[str] | None = None,
    method_floor: list[str] | None = None,
) -> str:
    """调用 DeepSeek（reasoner）获取建模结果原始文本，带重试逻辑。

    Args:
        system_prompt: 本次调用使用的 system prompt（已注入 locked_plan）。
        problem_text: 建模题目原文。
        analysis: 题目分析结果。
        references: 检索到的参考片段，可为 None。
        data_files: 数据文件绝对路径列表，可为 None。
        method_floor: RAG 参考方法下限列表，可为 None。

    Returns:
        LLM 返回的原始文本。

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
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            return response.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001 - 统一捕获后重试
            last_error = exc
            logger.warning("建模 LLM 调用失败（第 %d/%d 次）：%s", attempt, LLM_MAX_RETRIES, exc)
            if attempt < LLM_MAX_RETRIES:
                time.sleep(2 ** (attempt - 1))

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
        text = text.split("\n", 1)[-1] if "\n" in text else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text.strip("\n")


def _parse_and_validate(raw: str) -> dict:
    """解析并校验 LLM 返回的分段文本。

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

    desc_start = (model_idx + len(_MARK_MODEL)) if model_idx != -1 else 0
    model_description = raw[desc_start:code_idx].strip()

    code_start = code_idx + len(_MARK_CODE)
    code_end = outputs_idx if outputs_idx != -1 else len(raw)
    solver_code = _strip_code_fence(raw[code_start:code_end])

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
    """两阶段生成数学模型与求解代码。

    第一阶段：调用 LLM 规划求解方案（JSON），代码层面验证合理性，不通过则带错误原因重试。
    第二阶段：将验证通过的方案注入 system prompt，再调用 LLM 生成完整求解代码。

    Args:
        problem_text: 建模题目原文。
        analysis: 题目分析 Agent 的输出。
        references: 检索到的优秀论文参考片段，可选。
        data_files: 题目附带数据文件的绝对路径列表，可选。
        method_floor: RAG 参考论文使用的方法列表，作为方法下限，可选。

    Returns:
        建模结果字典，包含：
        - model_description (str): Markdown 格式的数学模型
        - solver_code (str): 可独立运行的 Python 求解代码
        - expected_outputs (list[str]): 代码预期产出说明
        - plan (dict): 第一阶段确认的方法规划

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

    # 第一阶段：规划
    plan = _plan_approach(problem_text, analysis)

    # 第二阶段：注入已锁定方案，生成代码
    locked_plan_text = (
        f"- 求解器：{plan['solver']}\n"
        f"- 变量设计：{plan['variable_design']}\n"
        f"- 子问题：{plan.get('sub_problems', [])}\n"
        f"- 预估变量数：{plan.get('estimated_total_vars', '未知')}\n"
        f"- 思路：{plan.get('approach_summary', '')}\n"
    )
    system_prompt = _CODE_SYSTEM_PROMPT_TEMPLATE.replace("{locked_plan}", locked_plan_text)

    raw = _call_llm(system_prompt, problem_text, analysis, references, data_files, method_floor)
    result = _parse_and_validate(raw)
    result["plan"] = plan

    logger.info(
        "建模完成：模型描述 %d 字符，代码 %d 字符，求解器=%s",
        len(result["model_description"]),
        len(result["solver_code"]),
        plan["solver"],
    )
    return result
