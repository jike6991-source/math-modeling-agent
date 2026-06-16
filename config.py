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
DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# ===== 路径配置 =====
OUTPUTS_DIR: Path = BASE_DIR / "outputs"
TEMPLATES_DIR: Path = BASE_DIR / "templates"
PROJECTS_DIR: Path = BASE_DIR / "projects"  # 每道题一个子目录存放产物

# ===== 执行参数 =====
CODE_EXEC_TIMEOUT: int = 180  # 生成代码的默认执行超时（秒），可在 run_code 调用时覆盖
LLM_TIMEOUT: int = 120  # LLM 请求超时（秒）
LLM_MAX_RETRIES: int = 3  # LLM 调用失败重试次数

if not DEEPSEEK_API_KEY:
    logger.warning("未检测到 DEEPSEEK_API_KEY，请在 .env 中配置后再调用 LLM。")


def get_llm_client() -> OpenAI:
    """创建并返回配置好的 DeepSeek LLM 客户端。

    使用 openai SDK 连接 DeepSeek（openai 兼容接口），便于后续切换模型。
    API Key 从环境变量读取，不在代码中硬编码。

    Returns:
        已配置 base_url 与 api_key 的 OpenAI 客户端实例。

    Raises:
        RuntimeError: 未配置 DEEPSEEK_API_KEY 时抛出。
    """
    if not DEEPSEEK_API_KEY:
        raise RuntimeError("未配置 DEEPSEEK_API_KEY，请在 .env 中设置后重试。")
    return OpenAI(
        api_key=DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_BASE_URL,
        timeout=LLM_TIMEOUT,
    )
