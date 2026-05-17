"""Application configuration via environment variables (pydantic-settings)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. All values are read from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- LLM (Yandex Eliza, OpenAI-compatible) ---
    soy_token: str | None = Field(default=None, alias="SOY_TOKEN")
    llm_base_url: str = Field(
        default="https://api.eliza.yandex.net/raw/openai/v1",
        alias="LLM_BASE_URL",
    )
    llm_model: str = Field(default="gpt-5.4-nano", alias="LLM_MODEL")
    llm_timeout_s: float = Field(default=60.0, alias="LLM_TIMEOUT_S")
    llm_max_tokens: int = Field(default=1200, alias="LLM_MAX_TOKENS")
    llm_ca_bundle: str | None = Field(default=None, alias="LLM_CA_BUNDLE")

    # --- Embeddings ---
    embedding_model: str = Field(
        default="intfloat/multilingual-e5-small",
        alias="EMBEDDING_MODEL",
    )

    # --- Paths ---
    graph_path: Path = Field(default=Path("out/LearningChunkGraph_longrange.json"), alias="GRAPH_PATH")
    concept_dict_path: Path = Field(default=Path("out/ConceptDictionary.json"), alias="CONCEPT_DICT_PATH")
    theory_md_path: Path = Field(default=Path("theory_economics.md"), alias="THEORY_MD_PATH")
    chroma_path: Path = Field(default=Path("data/chroma"), alias="CHROMA_PATH")
    topics_path: Path = Field(default=Path("data/topics.json"), alias="TOPICS_PATH")
    data_dir: Path = Field(default=Path("data"), alias="DATA_DIR")
    exams_dir: Path = Field(default=Path("data/exams"), alias="EXAMS_DIR")

    # --- Topics ---
    n_topics: int = Field(default=15, alias="N_TOPICS", ge=2, le=50)
    perfect_score_topics_limit: int = Field(default=8, alias="PERFECT_SCORE_TOPICS_LIMIT")

    # --- Graph BFS ---
    graph_bfs_depth: int = Field(default=2, alias="GRAPH_BFS_DEPTH", ge=1, le=4)
    study_plan_related_limit: int = Field(default=8, alias="STUDY_PLAN_RELATED_LIMIT")

    # --- Retrieval ---
    retriever_top_k_graph: int = Field(default=4, alias="RETRIEVER_TOP_K_GRAPH")
    retriever_top_k_md: int = Field(default=4, alias="RETRIEVER_TOP_K_MD")
    md_chunk_target_tokens: int = Field(default=800, alias="MD_CHUNK_TARGET_TOKENS")
    md_chunk_overlap_tokens: int = Field(default=100, alias="MD_CHUNK_OVERLAP_TOKENS")

    # --- Reranker (optional) ---
    enable_reranker: bool = Field(default=True, alias="ENABLE_RERANKER")
    reranker_model: str = Field(
        default="cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
        alias="RERANKER_MODEL",
    )
    reranker_top_k_in: int = Field(default=20, alias="RERANKER_TOP_K_IN")
    reranker_top_k_out: int = Field(default=10, alias="RERANKER_TOP_K_OUT")
    # 0.5 blend: equal weight to CE relevance and original (graph+vector) score.
    # Pure CE (1.0) tends to drop high-precision graph hits when the question
    # phrasing is generic; 0.5 keeps the best of both worlds in our domain.
    reranker_score_blend: float = Field(default=0.5, alias="RERANKER_SCORE_BLEND")

    # --- App ---
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO", alias="LOG_LEVEL")

    # --- Test/CI helpers ---
    skip_llm: bool = Field(default=False, alias="SKIP_LLM")
    """If True, generator skips real LLM calls (for unit tests)."""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
