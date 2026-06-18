"""项目入口，负责编排建模 pipeline。

流程：检索参考论文 → 题目分析 → 建模与求解代码 → 执行代码出图 → 撰写论文 → 导出 Word。
全部产物按题目存入 projects/<题目名>/ 目录。
"""

import argparse
import json
import logging
from pathlib import Path

from agents.analyzer import analyze
from agents.modeler import build_model
from agents.reporter import build_report
from config import CODE_EXEC_TIMEOUT, PROJECTS_DIR
from rag.retriever import collect_methods, format_references, retrieve
from tools.code_runner import run_code

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# 检索参考论文片段的数量
_REFERENCE_TOP_K: int = 6


def _retrieve_references(problem_text: str, top_k: int = _REFERENCE_TOP_K) -> tuple[str, list[str]]:
    """根据题目原文从知识库检索相关论文片段。

    检索在 analyze 之前执行，method_floor 可随即传入 analyze 作为方法推荐下限。
    检索失败（如知识库为空或向量库不可用）不阻断 pipeline，返回空结果。

    Args:
        problem_text: 建模题目原文（取前 500 字作为检索 query，BGE 自行处理长度）。
        top_k: 检索片段数量。

    Returns:
        二元组 (参考文本, 方法下限列表)；无结果或失败时为 ("", [])。
    """
    try:
        results = retrieve(problem_text[:500], top_k=top_k)
        logger.info("检索到 %d 条参考论文片段", len(results))
        return format_references(results), collect_methods(results)
    except Exception as exc:  # noqa: BLE001 - 检索失败降级为无参考，不阻断 pipeline
        logger.warning("参考论文检索失败，跳过参考：%s", exc)
        return "", []


def _relativize_artifacts(exec_result: dict, base_dir: Path) -> dict:
    """将执行产物路径转为相对 base_dir 的路径，便于论文图片引用。

    Args:
        exec_result: run_code 的返回结果。
        base_dir: 题目项目根目录。

    Returns:
        artifacts 改为相对路径的执行结果副本。
    """
    rel = dict(exec_result)
    rel_artifacts = []
    for a in exec_result.get("artifacts") or []:
        try:
            rel_artifacts.append(Path(a).relative_to(base_dir).as_posix())
        except ValueError:
            rel_artifacts.append(a)
    rel["artifacts"] = rel_artifacts
    return rel


def run_pipeline(
    problem_text: str,
    project_name: str,
    exec_timeout: int = CODE_EXEC_TIMEOUT,
    data_files: list[str] | None = None,
) -> dict:
    """运行完整建模 pipeline 并将产物存入 projects/<project_name>/。

    Args:
        problem_text: 建模题目原文。
        project_name: 题目项目名（作为 projects/ 下的子目录名）。
        exec_timeout: 求解代码执行超时（秒）。
        data_files: 题目附带数据文件的绝对路径列表，可选；提供时建模代码读取真实数据。

    Returns:
        结果摘要字典，包含各产物文件路径与执行结果。
    """
    if not problem_text or not problem_text.strip():
        raise ValueError("题目原文不能为空")
    if not project_name or not project_name.strip():
        raise ValueError("项目名不能为空")

    project_dir = PROJECTS_DIR / project_name
    charts_dir = project_dir / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)
    logger.info("项目目录：%s", project_dir)

    # 0. 保存题目原文
    (project_dir / "problem.md").write_text(problem_text, encoding="utf-8")

    # 1. 检索优秀论文参考片段（先于分析，以便将 method_floor 传入 analyzer）
    references, method_floor = _retrieve_references(problem_text)
    if references:
        (project_dir / "references.md").write_text(references, encoding="utf-8")

    # 2. 题目分析（传入 method_floor 作为方法推荐下限）
    analysis = analyze(problem_text, method_floor=method_floor)
    (project_dir / "analysis.json").write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 3. 建模与求解代码（参考检索片段、真实数据、方法下限）
    abs_data_files = [str(Path(p).resolve()) for p in (data_files or [])]
    model = build_model(
        problem_text, analysis, references, data_files=abs_data_files, method_floor=method_floor
    )
    (project_dir / "solver.py").write_text(model["solver_code"], encoding="utf-8")
    (project_dir / "model.md").write_text(model["model_description"], encoding="utf-8")

    # 4. 执行求解代码（图表落在 charts/ 下）
    exec_result = run_code(model["solver_code"], timeout=exec_timeout, workdir=charts_dir)
    if exec_result["success"]:
        logger.info("求解代码执行成功，产物 %d 个", len(exec_result["artifacts"]))
    elif exec_result["timeout"]:
        logger.warning("求解代码执行超时（%d 秒），将基于已有输出撰写论文", exec_timeout)
    else:
        logger.warning("求解代码执行失败：%s", (exec_result["stderr"] or "").strip()[:300])

    # 5. 撰写论文（图表用相对路径引用）
    report_exec = _relativize_artifacts(exec_result, project_dir)
    report = build_report(problem_text, analysis, model, report_exec, references)
    paper_path = project_dir / "paper.md"
    paper_path.write_text(report, encoding="utf-8")
    logger.info("Markdown 论文已保存：%s", paper_path)

    # 6. 导出 Word 论文
    docx_path: Path | None = None
    try:
        from tools.docx_exporter import export_docx
        docx_path = project_dir / "paper.docx"
        export_docx(report, docx_path, base_dir=project_dir)
        logger.info("Word 论文已保存：%s", docx_path)
    except Exception as exc:
        logger.warning("docx 导出失败（不影响 md 论文）：%s", exc)
        docx_path = None

    logger.info("pipeline 完成，论文已保存：%s", paper_path)
    return {
        "project_dir": str(project_dir),
        "analysis": analysis,
        "exec_success": exec_result["success"],
        "artifacts": exec_result["artifacts"],
        "paper_path": str(paper_path),
        "paper_docx_path": str(docx_path) if docx_path else None,
    }


def main() -> None:
    """命令行入口：从文件读取题目并运行 pipeline。"""
    parser = argparse.ArgumentParser(description="数学建模自动化 Agent")
    parser.add_argument("name", help="题目项目名，如 2023A_定日镜")
    parser.add_argument("problem_file", help="题目原文文件路径（.txt/.md）")
    parser.add_argument(
        "--timeout", type=int, default=CODE_EXEC_TIMEOUT, help="求解代码执行超时（秒）"
    )
    parser.add_argument(
        "--data",
        action="append",
        default=None,
        metavar="DATA_FILE",
        help="题目附带数据文件路径（CSV/Excel），可多次指定",
    )
    args = parser.parse_args()

    problem_text = Path(args.problem_file).read_text(encoding="utf-8")
    summary = run_pipeline(
        problem_text, args.name, exec_timeout=args.timeout, data_files=args.data
    )

    print("\n=== pipeline 完成 ===")
    print(f"题目类型：{summary['analysis']['problem_type']}")
    print(f"代码执行成功：{summary['exec_success']}")
    print(f"图表产物：{summary['artifacts']}")
    print(f"论文（md）：{summary['paper_path']}")
    if summary.get("paper_docx_path"):
        print(f"论文（docx）：{summary['paper_docx_path']}")


if __name__ == "__main__":
    main()
