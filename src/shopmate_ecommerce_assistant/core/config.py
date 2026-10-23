"""Environment-backed application settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Provider presets used by :meth:`Settings._fill_llm_profile`.
#:
#: * ``deepseek`` — **the baseline** for production, development and evaluation.
#: * ``qwen`` — kept only to align with the course brief (Alibaba DashScope
#:   OpenAI-compatible endpoint); not used by default.
#: * ``local`` — **offline smoke test only** (Ollama on 127.0.0.1); never an evaluation
#:   baseline. Kept so an air-gapped check of the chat path still works.
LLM_PROFILES: dict[str, dict[str, str]] = {
    "deepseek": {"base_url": "https://api.deepseek.com", "model": "deepseek-flash"},
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-max",
    },
    "local": {"base_url": "http://127.0.0.1:11434/v1", "model": "qwen2.5:7b"},
}


class Settings(BaseSettings):
    """Runtime settings with safe local-development defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "ShopMate API"
    app_env: Literal["development", "test", "demo", "production"] = "demo"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    database_url: str = "postgresql+asyncpg://shopmate:change-me-local-only@localhost:5432/shopmate"
    redis_url: str = "redis://:change-me-local-only@localhost:6379/0"
    milvus_health_url: str = "http://localhost:9091/healthz"
    readiness_timeout_seconds: float = Field(default=2.0, gt=0, le=30)

    # Knowledge ingestion (stage 5) and retrieval (stage 7).
    milvus_uri: str = "http://localhost:19530"
    milvus_collection: str = "shopmate_knowledge_chunks"
    parent_chunk_chars: int = Field(default=1500, ge=400, le=4000)
    child_chunk_chars: int = Field(default=480, ge=150, le=1200)
    milvus_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    knowledge_upload_max_bytes: int = Field(default=20 * 1024 * 1024, gt=0)

    # Embeddings (stage 7). Dense *and* sparse vectors come from one local BGE-M3
    # forward pass. Weights are never baked into the image: either a mounted directory
    # (EMBEDDING_MODEL_PATH) or the Hugging Face cache is used.
    embedding_dimension: int = Field(default=1024, gt=0, le=4096)
    embedding_model_name: str = "BAAI/bge-m3"
    embedding_model_revision: str = ""
    # Project-relative by default; override with EMBEDDING_MODEL_PATH (e.g. /models/bge-m3
    # inside the container). Weights are mounted, never baked into the image.
    embedding_model_path: str = "models/bge-m3"
    embedding_cache_dir: str = ""
    embedding_device: str = "cpu"
    embedding_batch_size: int = Field(default=4, ge=1, le=64)
    embedding_max_length: int = Field(default=512, ge=32, le=8192)
    embedding_threads: int = Field(default=4, ge=1, le=64)

    # Hybrid retrieval: dense top-N + sparse top-N fused with RRF.
    retrieval_dense_limit: int = Field(default=30, ge=1, le=200)
    retrieval_sparse_limit: int = Field(default=30, ge=1, le=200)
    retrieval_rrf_k: int = Field(default=60, ge=1, le=200)
    retrieval_candidate_limit: int = Field(default=30, ge=1, le=200)
    retrieval_min_chunks: int = Field(default=4, ge=1, le=8)
    retrieval_max_chunks: int = Field(default=8, ge=1, le=8)
    retrieval_context_token_budget: int = Field(default=2400, ge=200, le=8000)
    retrieval_max_chunks_per_document: int = Field(default=3, ge=1, le=8)
    # Evidence gate: minimum dense cosine similarity of the best chunk. This is a
    # calibrated heuristic, not a probability (see ADR-0002: RRF scores are not
    # confidence values). Calibrated on data/eval/retrieval_cases.jsonl:
    # unrelated questions topped out at 0.5836, answerable ones started at 0.6961.
    policy_min_evidence_similarity: float = Field(default=0.62, ge=0.0, le=1.0)
    reranker_enabled: bool = False

    # Intent routing and query rewriting (stage 8). ``intent_min_confidence`` is the
    # engineering baseline from docs/03-architecture.md §6; below it the router asks a
    # clarifying question instead of guessing, and writes are never allowed.
    intent_min_confidence: float = Field(default=0.70, ge=0.0, le=1.0)
    # Knowledge fallback (stage 18). Rule scoring only recognises phrasings that were
    # written down; long-tail policy questions ("分期退款手续费会退吗") scored zero and fell
    # through to smalltalk, so they never reached the evidence gate. When no business
    # intent matched, a domain-word / interrogative / question-mark turn now goes to the
    # policy RAG path and lets PolicyQAService decide answer-vs-refuse. The switch exists
    # for ablation runs; ``weak_intent`` additionally covers turns whose only match is a
    # weak (score <= 2) pattern such as "支持…吗".
    knowledge_fallback_enabled: bool = True
    knowledge_fallback_weak_intent_enabled: bool = True
    max_user_input_chars: int = Field(default=2000, ge=1, le=20000)
    query_rewrite_max_keywords: int = Field(default=6, ge=0, le=20)
    query_rewrite_max_subqueries: int = Field(default=3, ge=1, le=3)

    # Conversational rephrasing (stage 17). Deterministic answers stay the source of truth;
    # the LLM only rewrites the wording and its output is rejected unless every digit it
    # contains already exists in the draft. Disabled automatically when no model is set.
    chat_persona_enabled: bool = True
    chat_persona_timeout_seconds: float = Field(default=8.0, gt=0, le=30)

    # FAQ high-confidence cache (stage 8). Only grounded, low-risk policy answers are
    # stored; the key embeds shop/region/locale/knowledge-base/knowledge-version.
    faq_cache_enabled: bool = True
    faq_cache_key_prefix: str = "shopmate:faq:v1"
    faq_cache_ttl_seconds: int = Field(default=3600, ge=60, le=7 * 24 * 3600)
    faq_min_match_confidence: float = Field(default=0.86, ge=0.5, le=1.0)

    # Answer model for policy QA (stage 13/18). **DeepSeek is the production, development
    # and evaluation baseline** (OpenAI-compatible endpoint). Explicit ``LLM_BASE_URL`` /
    # ``LLM_MODEL`` always win; ``LLM_PROFILE`` only fills the blanks, so switching the
    # whole stack to another provider is one variable.
    #
    # ``local`` is an **offline smoke-test only** profile (Ollama on 127.0.0.1) — it is
    # NOT an evaluation baseline and must never be quoted as a quality number. The retired
    # qwen2.5:7b numbers in docs/eval-report.md are marked as history for that reason.
    # When ``LLM_BASE_URL`` / ``LLM_MODEL`` are empty the service returns citations and
    # refuses to fabricate an answer (retrieval-only mode).
    llm_profile: Literal["deepseek", "qwen", "local"] = "deepseek"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_timeout_seconds: float = Field(default=60.0, gt=0, le=180)
    llm_temperature: float = Field(default=0.1, ge=0.0, le=1.0)
    #: ``0`` keeps the provider default (the parameter is simply not sent).
    llm_max_tokens: int = Field(default=0, ge=0, le=8192)
    #: Hard ceiling for a *per-conversation* ``max_tokens`` override (stage 19). The chat
    #: page lets a shopper cap the answer length, but an unbounded value could stall a turn
    #: and burn quota, so the write path rejects anything above this and the read path
    #: clamps stale rows to it. ``LLM_MAX_TOKENS`` (the operator default) is unaffected.
    llm_max_tokens_cap: int = Field(default=4096, ge=256, le=8192)

    @model_validator(mode="after")
    def _fill_llm_profile(self) -> "Settings":
        """Fill provider defaults from ``LLM_PROFILE`` without overriding explicit values."""
        preset = LLM_PROFILES.get(self.llm_profile)
        if preset is None:
            return self
        if not self.llm_base_url.strip():
            object.__setattr__(self, "llm_base_url", preset["base_url"])
        if not self.llm_model.strip():
            object.__setattr__(self, "llm_model", preset["model"])
        return self

    # Eligibility tokens (stage 9). The signing key must never be committed; the default
    # is a placeholder for local development, exactly like the database password above.
    # Override with TOOL_TOKEN_SECRET in production/demo deployments.
    tool_token_secret: str = "shopmate-dev-token-secret-change-me"
    eligibility_token_ttl_seconds: int = Field(default=600, ge=60, le=3600)

    # Auth (stage 10). ``jwt_secret`` is a local-development placeholder; override in any
    # shared or production deployment. Never commit a real value.
    jwt_secret: str = "shopmate-dev-jwt-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_ttl_seconds: int = Field(default=900, ge=60, le=86400)
    refresh_token_ttl_seconds: int = Field(default=7 * 24 * 3600, ge=3600, le=30 * 24 * 3600)
    captcha_ttl_seconds: int = Field(default=300, ge=60, le=3600)
    refresh_cookie_name: str = "shopmate_refresh"
    csrf_cookie_name: str = "shopmate_csrf"

    # Rate limiting (stage 10). Keys are scoped per user/IP; the limiter is Redis-backed
    # with a deterministic in-memory fallback for tests.
    rate_limit_auth_per_minute: int = Field(default=10, ge=1, le=1000)
    rate_limit_chat_per_minute: int = Field(default=20, ge=1, le=1000)

    # SSE (stage 10).
    sse_keepalive_seconds: int = Field(default=15, ge=1, le=60)
    sse_total_timeout_seconds: int = Field(default=120, ge=10, le=600)

    api_cors_origins: str = "http://localhost:3000"

    # Reverse-proxy / production hardening (stage 14). Empty string keeps the middleware
    # disabled, which is what local development and the test suite rely on.
    trusted_hosts: str = ""

    @property
    def cors_origins(self) -> list[str]:
        """Return configured CORS origins as a normalized list."""
        return [origin.strip() for origin in self.api_cors_origins.split(",") if origin.strip()]

    @property
    def allowed_hosts(self) -> list[str]:
        """Return the ``Host`` header allow-list, or an empty list when disabled."""
        return [host.strip() for host in self.trusted_hosts.split(",") if host.strip()]

    def ensure_production_secrets(self) -> None:
        """Refuse to serve production traffic with the repository's development secrets.

        ``jwt_secret`` / ``tool_token_secret`` ship with ``shopmate-dev-`` placeholders so a
        fresh clone can run locally. Those values are published in the repository, so anyone
        could forge access tokens or return-eligibility tokens. Deployment artefacts always
        inject real values; this guard exists so that a misconfigured deploy fails at start-up
        instead of silently trusting guessable keys.

        Raises:
            RuntimeError: when ``app_env`` is ``production`` and a secret is a placeholder.
        """
        if self.app_env != "production":
            return
        offenders = [
            name
            for name, value in (
                ("JWT_SECRET", self.jwt_secret),
                ("TOOL_TOKEN_SECRET", self.tool_token_secret),
            )
            if value.startswith("shopmate-dev-")
        ]
        if offenders:
            raise RuntimeError(
                "Refusing to start with the development placeholder for "
                f"{', '.join(offenders)} while APP_ENV=production. "
                "Generate a random value (see .env.prod.example) and inject it as an "
                "environment variable."
            )


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()
