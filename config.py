"""配置加载模块。

从 .env 读取敏感配置（API 密钥等），并定义项目级常量。
敏感信息一律从环境变量读取，不在代码中硬编码。
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

logger = logging.getLogger(__name__)

# 加载项目根目录下的 .env
BASE_DIR: Path = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# ===== DeepSeek / LLM 配置 =====
DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
# 对话/通用任务模型（可通过 .env 覆盖；注意：旧名 deepseek-reasoner 现已映射为 flash，勿再使用）
DEEPSEEK_CHAT_MODEL: str = os.getenv("DEEPSEEK_CHAT_MODEL", "deepseek-v4-pro")
# 强推理模型（数学建模与求解代码生成，推理能力强但更慢更贵）
DEEPSEEK_REASONER_MODEL: str = os.getenv("DEEPSEEK_REASONER_MODEL", "deepseek-v4-pro")
# 向后兼容别名：旧代码仍可引用 DEEPSEEK_MODEL（等同 chat 模型）
DEEPSEEK_MODEL: str = DEEPSEEK_CHAT_MODEL

# ===== 路径配置 =====
OUTPUTS_DIR: Path = BASE_DIR / "outputs"
TEMPLATES_DIR: Path = BASE_DIR / "templates"
PROJECTS_DIR: Path = BASE_DIR / "projects"  # 每道题一个子目录存放产物

# ===== 知识库 / RAG 配置（Phase 2）=====
KNOWLEDGE_DIR: Path = BASE_DIR / "knowledge"
PAPERS_DIR: Path = KNOWLEDGE_DIR / "papers"  # 原始 PDF（不入 git）
PROCESSED_DIR: Path = KNOWLEDGE_DIR / "processed"  # 切片+标注中间产物 JSON
CHROMA_DIR: Path = KNOWLEDGE_DIR / "chroma_db"  # ChromaDB 持久化目录（不入 git）
EMBEDDING_MODEL: str = "BAAI/bge-small-zh-v1.5"  # 中文 embedding 模型
CHROMA_COLLECTION: str = "cumcm_papers"  # 向量库 collection 名称

# ===== 执行参数 =====
CODE_EXEC_TIMEOUT: int = 480  # 生成代码的默认执行超时（秒），可在 run_code 调用时覆盖
LLM_TIMEOUT: int = 120  # LLM 请求超时（秒）
# 强推理模型（reasoner）响应较慢，单独放宽超时；可在 .env 覆盖
LLM_REASONER_TIMEOUT: int = int(os.getenv("LLM_REASONER_TIMEOUT", "300"))
LLM_MAX_RETRIES: int = 3  # LLM 调用失败重试次数

if not DEEPSEEK_API_KEY:
    logger.warning("未检测到 DEEPSEEK_API_KEY，请在 .env 中配置后再调用 LLM。")


def get_llm_client(model: str | None = None) -> OpenAI:
    """创建并返回配置好的 DeepSeek LLM 客户端。

    使用 openai SDK 连接 DeepSeek（openai 兼容接口），便于后续切换模型。
    API Key 从环境变量读取，不在代码中硬编码。

    注意：DeepSeek/OpenAI 接口在每次 ``chat.completions.create(model=...)`` 处指定
    模型，本函数的 ``model`` 参数仅用于按模型选择合适的请求超时——reasoner 模型
    响应更慢，会使用更长的 ``LLM_REASONER_TIMEOUT``，其余模型使用 ``LLM_TIMEOUT``。

    Args:
        model: 即将调用的模型名（如 DEEPSEEK_REASONER_MODEL），仅用于选择超时；
            为 None 时按普通超时处理。

    Returns:
        已配置 base_url、api_key 与超时的 OpenAI 客户端实例。

    Raises:
        RuntimeError: 未配置 DEEPSEEK_API_KEY 时抛出。
    """
    if not DEEPSEEK_API_KEY:
        raise RuntimeError("未配置 DEEPSEEK_API_KEY，请在 .env 中设置后重试。")
    timeout = LLM_REASONER_TIMEOUT if model == DEEPSEEK_REASONER_MODEL else LLM_TIMEOUT
    return OpenAI(
        api_key=DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_BASE_URL,
        timeout=timeout,
    )
