"""项目入口，负责编排建模 pipeline。

流程：题目分析 → 建模与求解代码 → 执行代码出图 → 撰写论文。
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
from rag.retriever import format_references, retrieve
from tools.code_runner import run_code

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# 检索参考论文片段的数量
_REFERENCE_TOP_K: int = 6


def _retrieve_references(analysis: dict, top_k: int = _REFERENCE_TOP_K) -> str:
    """根据题目分析结果从知识库检索相关论文片段，渲染为参考文本。

    检索失败（如知识库为空或向量库不可用）不阻断 pipeline，返回空字符串。

    Args:
        analysis: 题目分析 Agent 的输出。
        top_k: 检索片段数量。

    Returns:
        渲染后的参考文本；无结果或失败时为空字符串。
    """
    query = "；".join(
        filter(
            None,
            [
                f"{analysis.get('problem_type', '')}问题",
                "关键变量：" + "、".join(analysis.get("key_variables", [])),
                "建模方法：" + "、".join(analysis.get("suggested_methods", [])),
            ],
        )
    )
    try:
        results = retrieve(query, top_k=top_k)
        logger.info("检索到 %d 条参考论文片段", len(results))
        return format_references(results)
    except Exception as exc:  # noqa: BLE001 - 检索失败降级为无参考，不阻断 pipeline
        logger.warning("参考论文检索失败，跳过参考：%s", exc)
        return ""


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


def run_pipeline(problem_text: str, project_name: str, exec_timeout: int = CODE_EXEC_TIMEOUT) -> dict:
    """运行完整建模 pipeline 并将产物存入 projects/<project_name>/。

    Args:
        problem_text: 建模题目原文。
        project_name: 题目项目名（作为 projects/ 下的子目录名）。
        exec_timeout: 求解代码执行超时（秒）。

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

    # 1. 题目分析
    analysis = analyze(problem_text)
    (project_dir / "analysis.json").write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 1.5 检索优秀论文参考片段（供建模与写作借鉴）
    references = _retrieve_references(analysis)
    if references:
        (project_dir / "references.md").write_text(references, encoding="utf-8")

    # 2. 建模与求解代码（参考检索片段）
    model = build_model(problem_text, analysis, references)
    (project_dir / "solver.py").write_text(model["solver_code"], encoding="utf-8")
    (project_dir / "model.md").write_text(model["model_description"], encoding="utf-8")

    # 3. 执行求解代码（图表落在 charts/ 下）
    exec_result = run_code(model["solver_code"], timeout=exec_timeout, workdir=charts_dir)
    if exec_result["success"]:
        logger.info("求解代码执行成功，产物 %d 个", len(exec_result["artifacts"]))
    elif exec_result["timeout"]:
        logger.warning("求解代码执行超时（%d 秒），将基于已有输出撰写论文", exec_timeout)
    else:
        logger.warning("求解代码执行失败：%s", (exec_result["stderr"] or "").strip()[:300])

    # 4. 撰写论文（图表用相对路径引用）
    report_exec = _relativize_artifacts(exec_result, project_dir)
    report = build_report(problem_text, analysis, model, report_exec, references)
    paper_path = project_dir / "paper.md"
    paper_path.write_text(report, encoding="utf-8")

    logger.info("pipeline 完成，论文已保存：%s", paper_path)
    return {
        "project_dir": str(project_dir),
        "analysis": analysis,
        "exec_success": exec_result["success"],
        "artifacts": exec_result["artifacts"],
        "paper_path": str(paper_path),
    }


def main() -> None:
    """命令行入口：从文件读取题目并运行 pipeline。"""
    parser = argparse.ArgumentParser(description="数学建模自动化 Agent")
    parser.add_argument("name", help="题目项目名，如 2023A_定日镜")
    parser.add_argument("problem_file", help="题目原文文件路径（.txt/.md）")
    parser.add_argument(
        "--timeout", type=int, default=CODE_EXEC_TIMEOUT, help="求解代码执行超时（秒）"
    )
    args = parser.parse_args()

    problem_text = Path(args.problem_file).read_text(encoding="utf-8")
    summary = run_pipeline(problem_text, args.name, exec_timeout=args.timeout)

    print("\n=== pipeline 完成 ===")
    print(f"题目类型：{summary['analysis']['problem_type']}")
    print(f"代码执行成功：{summary['exec_success']}")
    print(f"图表产物：{summary['artifacts']}")
    print(f"论文：{summary['paper_path']}")


if __name__ == "__main__":
    main()
