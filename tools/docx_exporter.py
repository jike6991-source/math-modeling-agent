"""Markdown → Word（.docx）导出，调用 pandoc 生成原生公式和图片。"""

import logging
import os
import re
import subprocess
import uuid
from pathlib import Path

from config import TEMPLATES_DIR

logger = logging.getLogger(__name__)


def _preprocess_math(text: str) -> str:
    """统一公式分隔符并修复被 Markdown 吞掉的下标下划线。

    1. \\[...\\] → $$...$$，\\(...\\) → $...$（pandoc 对 $$ 识别最稳定）
    2. 在数学块内，将 \\cmd { 恢复为 \\cmd_{ —— Markdown 将 _ 当斜体标记吞掉后
       留下的痕迹是命令与 { 之间多了一个空格。
    """
    # 步骤1：转换分隔符
    text = re.sub(r'\\\[(.+?)\\\]', r'$$\1$$', text, flags=re.DOTALL)
    text = re.sub(r'\\\((.+?)\\\)', r'$\1$', text, flags=re.DOTALL)

    # 步骤2：修复下划线，仅在数学块内应用
    def _fix_underscores(content: str) -> str:
        return re.sub(r'(\\[a-zA-Z]+) \{', r'\1_{', content)

    # 先处理独立公式块 $$...$$，再处理行内公式 $...$
    segments = re.split(r'(\$\$.*?\$\$)', text, flags=re.DOTALL)
    rebuilt: list[str] = []
    for seg in segments:
        if seg.startswith('$$') and seg.endswith('$$') and len(seg) > 4:
            rebuilt.append('$$' + _fix_underscores(seg[2:-2]) + '$$')
        else:
            # 行内公式（不跨行）
            sub = re.split(r'(\$[^$\n]+?\$)', seg)
            for s in sub:
                if s.startswith('$') and s.endswith('$') and len(s) > 2:
                    rebuilt.append('$' + _fix_underscores(s[1:-1]) + '$')
                else:
                    rebuilt.append(s)
    return ''.join(rebuilt)


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
        tmp_md.write_text(_preprocess_math(markdown), encoding="utf-8")

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

        # ---- 后处理：修复表格跨页断裂 ----
        try:
            from docx import Document
            from docx.oxml.ns import qn
            from lxml import etree

            doc = Document(str(out_path))

            for table in doc.tables:
                for row in table.rows:
                    tr = row._tr
                    trPr = tr.find(qn('w:trPr'))
                    if trPr is None:
                        trPr = etree.SubElement(tr, qn('w:trPr'))
                        tr.insert(0, trPr)
                    cant_split = trPr.find(qn('w:cantSplit'))
                    if cant_split is None:
                        etree.SubElement(trPr, qn('w:cantSplit'))

            body = doc.element.body
            elements = list(body)
            for i, el in enumerate(elements):
                if el.tag == qn('w:tbl') and i > 0:
                    prev = elements[i - 1]
                    if prev.tag == qn('w:p'):
                        pPr = prev.find(qn('w:pPr'))
                        if pPr is None:
                            pPr = etree.SubElement(prev, qn('w:pPr'))
                            prev.insert(0, pPr)
                        keep_next = pPr.find(qn('w:keepNext'))
                        if keep_next is None:
                            etree.SubElement(pPr, qn('w:keepNext'))

            doc.save(str(out_path))
            logger.info("表格跨页修复完成")
        except Exception as exc:
            logger.warning("表格跨页修复失败（不影响主流程）：%s", exc)

        return out_path

    finally:
        if tmp_md.exists():
            tmp_md.unlink()
