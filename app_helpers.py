"""Streamlit 前端辅助函数：PDF 提取、RAG 查询、pipeline 分阶段执行等。"""
import json
import logging
from pathlib import Path

import streamlit as st

from agents.analyzer import analyze
from agents.modeler import build_model
from agents.reporter import build_report
from config import CODE_EXEC_TIMEOUT, PROJECTS_DIR
from tools.code_runner import run_code

logger = logging.getLogger(__name__)


def extract_pdf_text(uploaded_file) -> str:
    """从上传的 PDF 文件提取纯文本。"""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
        return "\n".join(page.get_text() for page in doc)
    except Exception as exc:
        raise ValueError(f"PDF 解析失败：{exc}") from exc


def get_rag_chunk_count() -> int | None:
    """获取 ChromaDB 已索引片段数；不可用时返回 None。"""
    try:
        from rag.store import get_collection
        return get_collection().count()
    except Exception:
        return None


def get_project_list() -> list[str]:
    """返回 projects/ 下子目录名称，按修改时间倒序。"""
    try:
        dirs = [p for p in PROJECTS_DIR.iterdir() if p.is_dir()]
        dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return [p.name for p in dirs]
    except Exception:
        return []


def save_data_files(uploaded_files: list, project_dir: Path) -> list[Path]:
    """将上传的 CSV/Excel 写到 project_dir/data/，返回路径列表。"""
    data_dir = project_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for uf in uploaded_files:
        dest = data_dir / uf.name
        dest.write_bytes(uf.getvalue())
        saved.append(dest)
        logger.info("已保存数据附件：%s", dest)
    return saved


def _relativize_artifacts(exec_result: dict, base_dir: Path) -> dict:
    """将产物绝对路径转为相对 base_dir 的路径，便于论文图片引用。"""
    rel = dict(exec_result)
    rel_artifacts: list[str] = []
    for a in exec_result.get("artifacts") or []:
        try:
            rel_artifacts.append(Path(a).relative_to(base_dir).as_posix())
        except ValueError:
            rel_artifacts.append(a)
    rel["artifacts"] = rel_artifacts
    return rel


def run_pipeline_staged(
    problem_text: str,
    project_name: str,
    project_dir: Path,
    uploaded_data_files: list,
    status,
) -> dict:
    """分阶段执行建模 pipeline，通过 status 更新进度，返回结果 dict。"""
    # 保存数据附件，记录绝对路径供建模代码读取真实数据
    saved_data_paths: list[str] = []
    if uploaded_data_files:
        saved_data_paths = [str(p.resolve()) for p in save_data_files(uploaded_data_files, project_dir)]

    # 阶段 1：题目分析
    status.update(label="阶段 1/5：分析题目…")
    try:
        analysis: dict = analyze(problem_text)
        (project_dir / "analysis.json").write_text(
            json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        st.write(f"✓ 题目分析完成：{analysis['problem_type']}，"
                 f"识别变量 {len(analysis['key_variables'])} 个")
    except Exception as exc:
        logger.exception("题目分析失败")
        status.update(label="题目分析失败", state="error")
        st.error(f"题目分析失败：{exc}")
        return {}

    # 阶段 2：检索参考论文（失败静默降级），并提取方法下限
    status.update(label="阶段 2/5：检索参考论文…")
    references = ""
    method_floor: list[str] = []
    try:
        from rag.retriever import collect_methods, format_references, retrieve
        query = f"{analysis['problem_type']} {' '.join(analysis['key_variables'][:3])}"
        results = retrieve(query, top_k=6)
        references = format_references(results)
        method_floor = collect_methods(results)
        if references:
            (project_dir / "references.md").write_text(references, encoding="utf-8")
        st.write(f"✓ 检索到 {len(results)} 条参考片段")
    except Exception as exc:
        logger.warning("RAG 检索失败（降级为空）：%s", exc)
        st.write("⚠ 知识库不可用，跳过参考检索")

    # 阶段 3：建立数学模型
    status.update(label="阶段 3/5：建立数学模型…")
    try:
        model_result: dict = build_model(
            problem_text,
            analysis,
            references or None,
            data_files=saved_data_paths or None,
            method_floor=method_floor or None,
        )
        (project_dir / "solver.py").write_text(
            model_result["solver_code"], encoding="utf-8"
        )
        (project_dir / "model.md").write_text(
            model_result["model_description"], encoding="utf-8"
        )
        st.write("✓ 数学模型建立完成，已生成求解代码")
    except Exception as exc:
        logger.exception("建模失败")
        status.update(label="建模失败", state="error")
        st.error(f"建模失败：{exc}")
        return {}

    # 阶段 4：执行求解代码
    status.update(label="阶段 4/5：执行求解代码…")
    charts_dir = project_dir / "charts"
    charts_dir.mkdir(exist_ok=True)
    try:
        exec_result: dict = run_code(
            model_result["solver_code"],
            timeout=CODE_EXEC_TIMEOUT,
            workdir=charts_dir,
        )
        if exec_result["timeout"]:
            st.write("⚠ 求解代码执行超时")
        elif not exec_result["success"]:
            st.write("⚠ 求解代码执行失败（见论文附录）")
        else:
            st.write(f"✓ 代码执行成功，生成图表 {len(exec_result['artifacts'])} 张")
    except Exception as exc:
        logger.exception("代码执行异常")
        exec_result = {"success": False, "stdout": "", "stderr": str(exc),
                       "artifacts": [], "timeout": False, "returncode": None}
        st.write(f"⚠ 代码执行异常：{exc}")

    # 阶段 5：撰写论文
    status.update(label="阶段 5/5：撰写论文…")
    try:
        report_exec = _relativize_artifacts(exec_result, project_dir)
        paper = build_report(problem_text, analysis, model_result, report_exec,
                             references or None)
        paper_path = project_dir / "paper.md"
        paper_path.write_text(paper, encoding="utf-8")
        st.write("✓ 论文撰写完成")
    except Exception as exc:
        logger.exception("论文生成失败")
        status.update(label="论文生成失败", state="error")
        st.error(f"论文生成失败：{exc}")
        return {}

    status.update(label="建模完成", state="complete")
    return {
        "project_dir": project_dir,
        "paper_path": project_dir / "paper.md",
        "solver_path": project_dir / "solver.py",
        "artifacts": exec_result.get("artifacts", []),
        "exec_success": exec_result.get("success", False),
    }


def load_project(project_name: str) -> dict:
    """加载历史项目的题目原文、论文内容与图表路径。"""
    project_dir = PROJECTS_DIR / project_name
    problem = (project_dir / "problem.md").read_text(encoding="utf-8") \
        if (project_dir / "problem.md").exists() else "（题目文件不存在）"
    paper = (project_dir / "paper.md").read_text(encoding="utf-8") \
        if (project_dir / "paper.md").exists() else "（论文文件不存在）"
    charts = sorted((project_dir / "charts").glob("*.png")) \
        if (project_dir / "charts").exists() else []
    return {"problem": problem, "paper": paper, "charts": charts}
