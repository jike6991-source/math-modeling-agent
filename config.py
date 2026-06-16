"""配置加载模块。

从 .env 读取敏感配置（API 密钥等），并定义项目级常量。
敏感信息一律从环境变量读取，不在代码中硬编码。
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

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

# ===== 执行参数 =====
CODE_EXEC_TIMEOUT: int = 30  # 生成代码的执行超时（秒）

if not DEEPSEEK_API_KEY:
    logger.warning("未检测到 DEEPSEEK_API_KEY，请在 .env 中配置后再调用 LLM。")
