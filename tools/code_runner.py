"""代码执行工具。

用 subprocess 隔离执行 Agent 生成的 Python 代码，设超时保护。
代码在指定工作目录（默认 outputs/）下运行，便于图表等产物落盘。
"""

import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from config import CODE_EXEC_TIMEOUT, OUTPUTS_DIR

logger = logging.getLogger(__name__)


def run_code(code: str, timeout: int = CODE_EXEC_TIMEOUT, workdir: Path | None = None) -> dict:
    """隔离执行 Python 代码。

    将代码写入临时文件，用独立的 Python 子进程执行，设超时保护，
    捕获标准输出与错误输出。代码在 workdir 下运行（默认 outputs/），
    并记录执行前后新增的产物文件（如图表 PNG）。

    Args:
        code: 待执行的 Python 源码。
        timeout: 执行超时（秒），默认取配置值 CODE_EXEC_TIMEOUT。
        workdir: 代码运行的工作目录，默认 OUTPUTS_DIR。

    Returns:
        执行结果字典，包含：
        - success (bool): 是否执行成功（无异常、未超时、返回码为 0）
        - returncode (int | None): 子进程返回码，超时为 None
        - stdout (str): 标准输出
        - stderr (str): 错误输出
        - timeout (bool): 是否因超时被终止
        - artifacts (list[str]): 执行后新增的产物文件路径

    Raises:
        ValueError: 代码为空时抛出。
    """
    if not code or not code.strip():
        raise ValueError("待执行代码不能为空")

    run_dir = workdir or OUTPUTS_DIR
    run_dir.mkdir(parents=True, exist_ok=True)

    # 记录执行前已存在的文件，用于事后识别新增产物
    before = {p for p in run_dir.iterdir() if p.is_file()}

    # 代码写入工作目录内的临时文件，确保相对路径产物落在 run_dir
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", dir=run_dir, encoding="utf-8", delete=False
    ) as f:
        script_path = Path(f.name)
        f.write(code)

    result: dict = {
        "success": False,
        "returncode": None,
        "stdout": "",
        "stderr": "",
        "timeout": False,
        "artifacts": [],
    }

    # 强制 matplotlib 使用非交互式 Agg 后端：避免生成代码里的 plt.show() 在子进程中
    # 弹出阻塞窗口、等不到关闭而触发超时（图表仍可正常 savefig 落盘）。
    env = {**os.environ, "MPLBACKEND": "Agg"}

    try:
        logger.info("开始执行代码（超时 %d 秒，工作目录 %s）", timeout, run_dir)
        completed = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(run_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            env=env,
        )
        result["returncode"] = completed.returncode
        result["stdout"] = completed.stdout or ""
        result["stderr"] = completed.stderr or ""
        result["success"] = completed.returncode == 0
        if result["success"]:
            logger.info("代码执行成功")
        else:
            logger.warning("代码执行返回非零码 %d：%s", completed.returncode, result["stderr"][:500])
    except subprocess.TimeoutExpired as exc:
        result["timeout"] = True
        result["stdout"] = exc.stdout or "" if isinstance(exc.stdout, str) else ""
        result["stderr"] = (exc.stderr if isinstance(exc.stderr, str) else "") or f"执行超时（超过 {timeout} 秒）"
        logger.warning("代码执行超时（超过 %d 秒），已终止", timeout)
    except Exception as exc:  # noqa: BLE001 - 兜底捕获，避免执行器自身崩溃
        result["stderr"] = f"执行器异常：{exc}"
        logger.error("代码执行器异常：%s", exc)
    finally:
        # 清理临时脚本本身，避免被误判为产物
        script_path.unlink(missing_ok=True)

    # 识别新增的产物文件
    after = {p for p in run_dir.iterdir() if p.is_file()}
    result["artifacts"] = sorted(str(p) for p in (after - before))

    return result
