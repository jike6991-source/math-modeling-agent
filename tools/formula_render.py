"""公式渲染：用 matplotlib mathtext 将 LaTeX 片段渲染为 PNG 图片。"""

import logging
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

logger = logging.getLogger(__name__)


def render_formula(latex: str, out_path: Path) -> bool:
    """将 LaTeX 公式渲染为 PNG 图片。

    Args:
        latex: 不含 $...$ 定界符的 LaTeX 表达式（如 r"\\min N_g"）。
        out_path: 输出 PNG 文件路径。

    Returns:
        渲染成功为 True，异常时为 False。
    """
    try:
        formula = f"${latex.strip()}$"
        fig = plt.figure(figsize=(6, 1))
        ax = fig.add_axes([0, 0, 1, 1])
        ax.axis("off")
        ax.text(
            0.5, 0.5, formula,
            fontsize=14, ha="center", va="center",
            transform=ax.transAxes,
        )
        fig.savefig(
            str(out_path),
            dpi=150,
            bbox_inches="tight",
            transparent=True,
            pad_inches=0.15,
        )
        plt.close(fig)
        return True
    except Exception as exc:
        logger.warning("公式渲染失败 %r：%s", latex[:60], exc)
        plt.close("all")
        return False
