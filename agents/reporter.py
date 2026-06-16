"""报告 Agent。

将分析与建模结果组装为结构化 Markdown 报告。本文件为骨架，逻辑待实现。
"""

import logging

logger = logging.getLogger(__name__)


def build_report(analysis: dict, model_result: dict) -> str:
    """组装结构化报告。

    Args:
        analysis: 题目分析结果。
        model_result: 建模结果。

    Returns:
        Markdown 格式的报告内容。
    """
    raise NotImplementedError("报告组装逻辑待实现")
