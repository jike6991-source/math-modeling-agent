"""数学建模Agent — Streamlit 前端界面。"""
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from app_helpers import (
    extract_pdf_text,
    get_project_list,
    get_rag_chunk_count,
    load_project,
    run_pipeline_staged,
)
from config import CODE_EXEC_TIMEOUT, PROJECTS_DIR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(page_title="数学建模Agent", layout="wide")


def render_sidebar() -> None:
    """渲染侧边栏，显示知识库状态与已完成项目数。"""
    st.sidebar.title("数学建模Agent")
    st.sidebar.markdown("---")
    chunk_count = get_rag_chunk_count()
    st.sidebar.metric(
        "RAG 知识库片段",
        value=chunk_count if chunk_count is not None else "不可用",
    )
    st.sidebar.metric("已完成项目", value=len(get_project_list()))
    st.sidebar.markdown("---")
    st.sidebar.caption(f"代码执行超时：{CODE_EXEC_TIMEOUT} 秒")


def render_input_section() -> str:
    """渲染题目输入区，支持文本输入与 PDF 上传，返回当前题目文本。"""
    st.subheader("题目输入")
    pdf_file = st.file_uploader("上传题目 PDF（自动提取文本）", type=["pdf"])
    if pdf_file is not None:
        try:
            extracted = extract_pdf_text(pdf_file)
            st.session_state["problem_text"] = extracted
            st.success(f"PDF 解析成功，共提取 {len(extracted)} 字符")
        except ValueError as exc:
            st.error(str(exc))

    text = st.text_area(
        "题目原文",
        value=st.session_state.get("problem_text", ""),
        height=280,
        placeholder="请粘贴题目内容，或上传 PDF 自动提取…",
        key="problem_text",
    )
    return text


def render_data_section() -> list:
    """渲染数据附件上传区，预览前5行，返回 UploadedFile 列表。"""
    st.subheader("数据附件（可选）")
    uploaded = st.file_uploader(
        "上传 CSV / Excel 数据文件",
        type=["csv", "xlsx", "xls"],
        accept_multiple_files=True,
    )
    if uploaded:
        for uf in uploaded:
            st.markdown(f"**{uf.name}**")
            try:
                if uf.name.endswith(".csv"):
                    df = pd.read_csv(uf)
                else:
                    df = pd.read_excel(uf)
                st.dataframe(df.head(5), use_container_width=True)
            except Exception as exc:
                st.warning(f"无法预览 {uf.name}：{exc}")
    return uploaded or []


def render_results_section(result: dict) -> None:
    """渲染建模结果区：论文、图表、下载按钮。"""
    st.markdown("---")
    st.subheader("建模结果")

    paper_path: Path = result["paper_path"]
    solver_path: Path = result["solver_path"]

    if not result.get("exec_success"):
        st.warning("求解代码执行失败或超时，图表可能不完整，论文仍已生成。")

    # 下载按钮
    col1, col2 = st.columns(2)
    with col1:
        paper_bytes = paper_path.read_bytes() if paper_path.exists() else b""
        st.download_button(
            "下载论文 paper.md",
            data=paper_bytes,
            file_name="paper.md",
            mime="text/markdown",
        )
    with col2:
        code_bytes = solver_path.read_bytes() if solver_path.exists() else b""
        st.download_button(
            "下载代码 solver.py",
            data=code_bytes,
            file_name="solver.py",
            mime="text/plain",
        )

    # 图表
    artifacts: list[str] = result.get("artifacts", [])
    project_dir: Path = result["project_dir"]
    png_paths = [project_dir / a for a in artifacts if a.endswith(".png")]
    if not png_paths:
        png_paths = sorted(project_dir.glob("charts/*.png"))
    if png_paths:
        st.subheader("生成图表")
        cols = st.columns(min(len(png_paths), 3))
        for idx, p in enumerate(png_paths):
            if p.exists():
                cols[idx % 3].image(str(p), use_container_width=True)

    # 论文正文
    st.subheader("论文正文")
    if paper_path.exists():
        st.markdown(paper_path.read_text(encoding="utf-8"))
    else:
        st.error("论文文件未找到。")


def render_history_tab() -> None:
    """渲染历史项目标签页，支持查看以往题目与论文。"""
    projects = get_project_list()
    if not projects:
        st.info("暂无历史项目。完成一次建模后会在此显示。")
        return

    selected = st.selectbox("选择历史项目", projects)
    if selected:
        data = load_project(selected)
        with st.expander("题目原文", expanded=False):
            st.markdown(data["problem"])
        if data["charts"]:
            st.subheader("图表")
            cols = st.columns(min(len(data["charts"]), 3))
            for idx, p in enumerate(data["charts"]):
                cols[idx % 3].image(str(p), use_container_width=True)
        st.subheader("论文")
        st.markdown(data["paper"])


def main() -> None:
    """Streamlit 应用主入口。"""
    render_sidebar()

    tab_main, tab_history = st.tabs(["建模", "历史项目"])

    with tab_main:
        st.title("数学建模Agent")
        problem_text = render_input_section()
        st.markdown("---")
        data_files = render_data_section()

        st.markdown("---")
        run_disabled = not bool(problem_text.strip())
        if st.button("开始建模", type="primary", disabled=run_disabled):
            project_name = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            project_dir = PROJECTS_DIR / project_name
            project_dir.mkdir(parents=True, exist_ok=True)
            (project_dir / "problem.md").write_text(problem_text, encoding="utf-8")

            with st.status("正在建模…", expanded=True) as status:
                result = run_pipeline_staged(
                    problem_text, project_name, project_dir, data_files, status
                )

            if result:
                st.session_state["pipeline_result"] = result
                st.success(f"建模完成！项目：{project_name}")
            else:
                st.error("建模过程中出现错误，请查看上方详情。")

        if st.session_state.get("pipeline_result"):
            render_results_section(st.session_state["pipeline_result"])

    with tab_history:
        render_history_tab()


main()
