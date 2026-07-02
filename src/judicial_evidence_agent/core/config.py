"""Application configuration — 从环境变量加载。"""

from pathlib import Path

from dotenv import load_dotenv

# 加载 .env 中的所有变量（包括无 JEA_ 前缀的如 LANGCHAIN_*）
# 从项目根目录加载（config.py 在 src/judicial_evidence_agent/core/ 下 → 上溯 4 层）
_env_path = Path(__file__).resolve().parent.parent.parent.parent / ".env"
load_dotenv(_env_path)
del _env_path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置，全部从环境变量或 .env 读取。"""

    # 数据库
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/judicial_evidence"

    # Chroma（本地向量库）
    chroma_persist_dir: str = "data/chroma_index"
    chroma_collection_name: str = "judicial_corpus"

    # LLM — 从 ANTHROPIC_AUTH_TOKEN 环境变量读取（DeepSeek API 走 Anthropic 协议）
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.deepseek.com/anthropic"
    anthropic_model: str = "deepseek-v4-pro[1m]"

    # Embedding
    embedding_model: str = "BAAI/bge-small-zh-v1.5"

    # 向量库后端: numpy | chroma | pgvector | milvus
    vector_backend: str = "numpy"

    # MinIO
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "judicial-materials"
    minio_secure: bool = False

    # 应用
    app_name: str = "司法多模态证据链 Agent"
    debug: bool = True
    log_level: str = "INFO"

    model_config = {"env_prefix": "JEA_", "env_file": ".env"}


settings = Settings()
