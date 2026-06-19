"""Markdown → Word（.docx）导出，调用 pandoc 生成原生公式和图片。"""

import logging
import os
import subprocess
import uuid
from pathlib import Path

from config import TEMPLATES_DIR

logger = logging.getLogger(__name__)


def export_docx(markdown: str, out_path: Path, base_dir: Path) -> Path:
    """将 Markdown 论文通过 pandoc 转为 Word 文档。

    pandoc 自动将 LaTeX 公式转为 Word 原生 OOXML Math（可编辑），
    处理图片插入与表格排版。图片路径须相对于 base_dir（即 paper.md 所在目录）。

    Args:
        markdown: Markdown 格式的论文正文。
        out_path: 输出 .docx 文件路径（绝对路径）。
        base_dir: 项目目录，pandoc 以此为工作目录解析相对图片路径。

    Returns:
        out_path（与输入相同，方便链式调用）。

    Raises:
        RuntimeError: pandoc 调用失败时抛出，包含 stderr 信息。
    """
    base_dir = base_dir.resolve()
    out_path = out_path if out_path.is_absolute() else base_dir / out_path
    tmp_md = base_dir / f"_tmp_{uuid.uuid4().hex}.md"
    try:
        tmp_md.write_text(markdown, encoding="utf-8")

        cmd = ["pandoc", str(tmp_md), "-o", str(out_path)]

        ref_doc = TEMPLATES_DIR / "cumcm_template.docx"
        if ref_doc.exists():
            cmd += [f"--reference-doc={ref_doc}"]

        env = os.environ.copy()
        env["MIKTEX_AUTOINSTALL"] = "1"

        result = subprocess.run(
            cmd,
            cwd=str(base_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"pandoc 导出失败（exit {result.returncode}）：{result.stderr.strip()}"
            )

        if result.stderr:
            logger.warning("pandoc stderr: %s", result.stderr.strip())

        logger.info("docx 导出完成：%s", out_path)
        return out_path

    finally:
        if tmp_md.exists():
            tmp_md.unlink()
