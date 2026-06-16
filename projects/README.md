# projects/

每做一道题，在此新建一个子目录，存放该题的全部产物。

## 命名约定

`<年份><赛题号>_<简称>/`，例如：`2023A_定日镜/`、`2022C_供应链/`。

## 子目录结构

```
projects/2023A_定日镜/
├── problem.md        # 题目原文
├── analysis.json     # analyzer 输出（题目类型、关键变量、建议方法）
├── solver.py         # modeler 生成的求解代码
├── charts/           # 图表 PNG（git 忽略，可由代码重新生成）
└── paper.md          # 最终论文（docx/pdf 同样跟踪）
```

## 版本控制说明

- **跟踪**：题目、分析结果、代码、论文（含 docx/pdf）。
- **忽略**：图表等图片产物（`*.png/*.jpg/*.jpeg/*.svg/*.gif`），可由 `solver.py` 重新生成。详见根目录 `.gitignore`。
