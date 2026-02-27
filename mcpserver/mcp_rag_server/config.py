"""
RAG 配置 - 全部从环境变量加载
"""
import os


class Config:
    """RAG 配置"""

    # Embedding
    embedding_api_key = os.getenv("EMBEDDING_API_KEY", "")
    embedding_base_url = os.getenv("EMBEDDING_BASE_URL", "https://yunwu.ai/v1")
    embedding_model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

    # Pinecone
    pinecone_api_key = os.getenv("PINECONE_API_KEY", "")
    pinecone_host = os.getenv("PINECONE_HOST", "")
    pinecone_index = os.getenv("PINECONE_INDEX", "philosophy2")

    # LLM (query rewrite / rerank)
    llm_api_key = os.getenv("LLM_API_KEY", "")
    llm_base_url = os.getenv("LLM_BASE_URL", "https://yunwu.ai/v1")
    llm_model = os.getenv("LLM_MODEL", "gemini-3-flash-preview")

    # NVIDIA Reranker
    nvidia_api_key = os.getenv("NVIDIA_API_KEY", "")
    nvidia_rerank_url = os.getenv("NVIDIA_RERANK_URL", "https://ai.api.nvidia.com/v1/retrieval/nvidia/reranking")
    nvidia_rerank_model = os.getenv("NVIDIA_RERANK_MODEL", "nvidia/rerank-qa-mistral-4b")

    # RAG 参数
    default_top_k = int(os.getenv("RAG_DEFAULT_TOP_K", "30"))
    rerank_candidate_multiplier = int(os.getenv("RAG_RERANK_MULTIPLIER", "5"))

    # 跳过 Query Rewrite (设为 true 或者没配置 LLM_API_KEY 时自动跳过)
    skip_rewrite = os.getenv("RAG_SKIP_REWRITE", "").lower() in ("true", "1", "yes") or not os.getenv("LLM_API_KEY", "")

    # 跳过 Rerank (设为 true 时跳过 LLM 重排序，直接用融合分数排序)
    skip_rerank = os.getenv("RAG_SKIP_RERANK", "").lower() in ("true", "1", "yes")


config = Config()
