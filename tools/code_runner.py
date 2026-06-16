"""代码执行工具。

用 subprocess 隔离执行 Agent 生成的 Python 代码，设超时保护。
本文件为骨架，逻辑待实现。
"""

import logging

from config import CODE_EXEC_TIMEOUT

logger = logging.getLogger(__name__)


def run_code(code: str, timeout: int = CODE_EXEC_TIMEOUT) -> dict:
    """隔离执行 Python 代码。

    Args:
        code: 待执行的 Python 源码。
        timeout: 执行超时（秒），默认取配置值。

    Returns:
        执行结果字典（stdout、stderr、返回码等）。
    """
    raise NotImplementedError("代码执行逻辑待实现")
