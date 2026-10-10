"""集中配置：从环境变量/.env 读取，避免各模块散落 os.getenv。"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    # LLM (OpenAI 兼容，默认指向 DeepSeek)
    LLM_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    LLM_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "deepseek-chat")
    LLM_TIMEOUT: float = float(os.getenv("LLM_TIMEOUT", "30"))
    LLM_MAX_RETRIES: int = int(os.getenv("LLM_MAX_RETRIES", "1"))
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.2"))

    # Embedding (OpenAI 兼容；留空则自动使用本地 hash embedding 兜底)
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "")
    EMBEDDING_TIMEOUT: float = float(os.getenv("EMBEDDING_TIMEOUT", "30"))

    # RAG / 向量库
    CHROMA_PERSIST_DIR: Path = Path(
        os.getenv("CHROMA_PERSIST_DIR", str(BASE_DIR / "data" / "chroma"))
    )
    CHROMA_COLLECTION: str = os.getenv("CHROMA_COLLECTION", "knowledge_base")
    RAG_TOP_K: int = int(os.getenv("RAG_TOP_K", "4"))
    RAG_MIN_SCORE: float = float(os.getenv("RAG_MIN_SCORE", "0.25"))
    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "300"))
    CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "60"))
    DOCS_DIR: Path = Path(os.getenv("DOCS_DIR", str(BASE_DIR / "docs")))

    # 工单 / 会话 / 日志
    SQLITE_PATH: Path = Path(os.getenv("SQLITE_PATH", str(BASE_DIR / "data" / "app.db")))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # 阈值与策略
    CONFIDENCE_THRESHOLD: float = float(os.getenv("CONFIDENCE_THRESHOLD", "0.5"))
    EMBEDDING_FALLBACK_ON_ERROR: bool = _bool(
        os.getenv("EMBEDDING_FALLBACK_ON_ERROR", "true"), True
    )

    def llm_configured(self) -> bool:
        return bool(self.LLM_API_KEY)

    def embedding_configured(self) -> bool:
        return bool(self.EMBEDDING_MODEL)


settings = Settings()
