"""项目入口，负责编排建模 pipeline。

流程：题目分析 → 建模与求解代码 → 图表 → Markdown 报告。
本文件目前仅为骨架，业务逻辑待 Phase 1 实现。
"""

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_pipeline(problem_text: str) -> str:
    """运行完整建模 pipeline。

    Args:
        problem_text: 建模题目原文。

    Returns:
        生成的 Markdown 报告内容。
    """
    raise NotImplementedError("pipeline 编排逻辑待实现")


if __name__ == "__main__":
    raise NotImplementedError("入口逻辑待实现")
