"""Markdown → Word（.docx）导出，国赛论文格式。"""

import logging
import re
import tempfile
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

from tools.formula_render import render_formula

logger = logging.getLogger(__name__)

_BODY_PT = 12  # 小四号
_H_PT = {1: 18, 2: 16, 3: 14, 4: 13}

def _font(run, size: float = _BODY_PT) -> None:
    """设置中文宋体、西文 Times New Roman。"""
    run.font.name = "Times New Roman"
    run.font.size = Pt(size)
    rPr = run._r.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.insert(0, rFonts)
    rFonts.set(qn("w:eastAsia"), "SimSun")

def _setup(doc: Document) -> None:
    """设置页边距、正文行距与默认字号。"""
    sec = doc.sections[0]
    sec.top_margin = sec.bottom_margin = Cm(2.54)
    sec.left_margin = sec.right_margin = Cm(3.17)
    nml = doc.styles["Normal"]
    nml.font.size = Pt(_BODY_PT)
    nml.paragraph_format.space_after = Pt(6)
    pPr = nml.element.get_or_add_pPr()
    sp = OxmlElement("w:spacing")
    sp.set(qn("w:line"), "360")
    sp.set(qn("w:lineRule"), "auto")
    pPr.append(sp)

def _inline(para, text: str, bold: bool = False) -> None:
    """解析 **bold** 与 $inline$ 后将文本分段添加为 runs。"""
    for part in re.split(r"(\*\*.*?\*\*|\$[^$]+\$)", text):
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            run = para.add_run(part[2:-2])
            run.bold = True
        elif part.startswith("$") and part.endswith("$") and len(part) > 2:
            run = para.add_run(part[1:-1])
            run.italic = True
        else:
            run = para.add_run(part)
        if bold:
            run.bold = True
        _font(run)

def _heading(doc: Document, text: str, level: int) -> None:
    """添加各级加粗标题段落。"""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    run = p.add_run(text)
    run.bold = True
    _font(run, _H_PT.get(level, _BODY_PT))

def _table(doc: Document, rows: list[list[str]]) -> None:
    """添加带边框的表格，首行加粗（使用 Table Grid 内置样式）。"""
    if not rows:
        return
    ncols = max(len(r) for r in rows)
    t = doc.add_table(rows=len(rows), cols=ncols)
    t.style = "Table Grid"
    for ri, rd in enumerate(rows):
        for ci, ct in enumerate(rd):
            if ci < ncols:
                cell = t.rows[ri].cells[ci]
                cell.paragraphs[0].clear()
                _inline(cell.paragraphs[0], ct.strip(), bold=(ri == 0))

def _formula(doc: Document, latex: str, fdir: Path) -> None:
    """渲染显示公式为居中图片，失败则插入居中斜体原文本。"""
    img = fdir / f"f{abs(hash(latex)) % 10 ** 9}.png"
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if render_formula(latex, img):
        p.add_run().add_picture(str(img), width=Cm(10))
    else:
        run = p.add_run(latex.strip())
        run.italic = True
        _font(run)

def _image(doc: Document, img_path: Path, caption: str) -> None:
    """插入居中图片与居中加粗图注。"""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if img_path.exists():
        try:
            p.add_run().add_picture(str(img_path), width=Cm(14))
        except Exception:
            p.add_run(f"[图片不可用：{img_path.name}]")
    else:
        p.add_run(f"[图片缺失：{img_path}]")
    if caption:
        cp = doc.add_paragraph()
        cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = cp.add_run(caption)
        run.bold = True
        _font(run)

def export_docx(markdown: str, out_path: Path, base_dir: Path) -> Path:
    """将 Markdown 论文转为国赛格式 Word 文档（宋体/Times，A4 页边距，1.5 倍行距）。"""
    doc = Document()
    _setup(doc)

    with tempfile.TemporaryDirectory() as tmp:
        fdir = Path(tmp)
        lines = markdown.splitlines()
        i, n = 0, len(lines)
        in_code, in_fml = False, False
        code_buf: list[str] = []
        fml_buf: list[str] = []

        while i < n:
            line = lines[i]
            raw = line.strip()

            # 围栏代码块
            if raw.startswith("```"):
                if in_code:
                    p = doc.add_paragraph()
                    run = p.add_run("\n".join(code_buf))
                    run.font.name = "Courier New"
                    run.font.size = Pt(9)
                    code_buf = []
                    in_code = False
                else:
                    in_code = True
                i += 1
                continue
            if in_code:
                code_buf.append(line)
                i += 1
                continue

            # 显示公式 \[ ... \]
            if raw.startswith(r"\["):
                inner = raw[2:].rstrip()
                if inner.endswith(r"\]"):
                    _formula(doc, inner[:-2].strip(), fdir)
                    i += 1
                    continue
                in_fml = True
                fml_buf = [inner] if inner else []
                i += 1
                continue
            if in_fml:
                if raw == r"\]":
                    _formula(doc, " ".join(fml_buf), fdir)
                    fml_buf = []
                    in_fml = False
                else:
                    fml_buf.append(raw)
                i += 1
                continue

            # 表格（连续 | 开头的行）
            if raw.startswith("|"):
                trows: list[list[str]] = []
                while i < n and lines[i].strip().startswith("|"):
                    cells = [c for c in lines[i].strip().split("|") if c.strip()]
                    if not all(re.match(r"^[-:]+$", c.strip()) for c in cells):
                        trows.append(cells)
                    i += 1
                _table(doc, trows)
                continue

            # 图片 ![alt](path)，下一非空行若是 **caption** 则用作图注
            m = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", raw)
            if m:
                img_path = base_dir / m.group(2)
                i += 1
                j = i
                while j < n and not lines[j].strip():
                    j += 1
                cap = ""
                if j < n:
                    cl = lines[j].strip()
                    if cl.startswith("**") and cl.endswith("**") and len(cl) > 4:
                        cap = cl[2:-2]
                        i = j + 1
                _image(doc, img_path, cap)
                continue

            # 标题
            hm = re.match(r"^(#{1,4})\s+(.*)", raw)
            if hm:
                _heading(doc, hm.group(2), len(hm.group(1)))
                i += 1
                continue

            # 空行 / 水平分割线
            if not raw or re.match(r"^[-*_]{3,}$", raw):
                i += 1
                continue

            # 普通段落
            p = doc.add_paragraph()
            _inline(p, raw)
            i += 1

    doc.save(str(out_path))
    return out_path
