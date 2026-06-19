# Math Modeling Agent - CLAUDE.md

## 项目概述
数学建模自动化Agent。输入建模题目，输出完整的建模分析报告（含代码、图表、论文）。
目标比赛：全国大学生数学建模竞赛（CUMCM），9月。

## 技术栈
- Python 3.11+
- LLM: DeepSeek API（openai兼容格式，base_url: https://api.deepseek.com）
  - 模型：`deepseek-v4-pro`（强推理，建模/代码生成）/ `deepseek-v4-flash`（快速，轻量任务）
  - 注意：旧模型名 `deepseek-reasoner` 已映射为 flash，不再使用
- RAG: ChromaDB + BGE-small-zh-v1.5 embeddings（Phase 2）
- 图表: matplotlib（中文显示用 SimHei 字体）
- 论文输出: python-docx 或 LaTeX（Phase 2）
- 配置管理: python-dotenv，敏感信息放 .env

## 目录结构
```
math-modeling-agent/
├── CLAUDE.md              # 本文件
├── .env                   # API密钥（不提交git）
├── .gitignore
├── requirements.txt
├── config.py              # 配置加载
├── main.py                # 入口，pipeline编排
├── agents/
│   ├── analyzer.py        # 题目分析Agent：识别题型、提取变量、确定建模方向
│   ├── modeler.py         # 建模Agent：生成数学模型和求解代码
│   └── reporter.py        # 报告Agent：组装分析结果为结构化报告
├── tools/
│   ├── code_runner.py     # 安全执行Agent生成的Python代码
│   └── chart_generator.py # 调用matplotlib生成图表，保存到outputs/
├── rag/                   # Phase 2
│   ├── indexer.py         # 论文切片和入库
│   └── retriever.py       # 检索相似论文片段
├── templates/             # 论文模板
│   └── cumcm_template.md  # 国赛论文Markdown模板
├── outputs/               # 临时生成的报告和图表（不提交git）
├── projects/              # 每道题一个子目录，存放该题全部产物
│   ├── README.md          # 子目录命名约定与结构说明
│   └── 2023A_定日镜/      # 示例：题目原文、分析结果、代码、图表、论文
└── tests/
    └── test_pipeline.py   # 端到端测试用例
```

> projects/ 下：题目、分析结果(json)、代码、论文(含docx/pdf)纳入git；图表(png/jpg等)忽略，可由代码重新生成。

## 代码规范
- 所有函数写中文docstring
- 类型注解必须加（def func(text: str) -> dict:）
- 用 logging 模块记录关键步骤，不要用 print
- 异步统一用 asyncio，不用 threading
- API调用必须有 try-except 和重试逻辑

## 不要做的事
- 不要自行安装新依赖，先告诉我确认
- 不要修改 .env 文件
- 不要在代码中硬编码 API Key
- 不要一次性写超过200行的单个文件，拆分模块
- 不要跳过错误处理直接写happy path

## 关键设计决策
- DeepSeek API 用 openai SDK 调用，方便后续切换其他模型
- Agent之间通过字典传递中间结果，不用复杂的消息队列
- 代码执行用 subprocess 隔离，默认超时180秒（可在 run_code 调用时覆盖）
- 图表统一保存为 PNG 到 outputs/ 目录

## 测试
- 用一道往年国赛题作为基准测试用例
- 每个Agent模块可独立测试
- 跑测试：python -m pytest tests/ -v

## 当前阶段
Phase 1：最小pipeline跑通（题目分析 → 建模代码 → 图表 → Markdown报告）
