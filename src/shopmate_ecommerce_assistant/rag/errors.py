"""Stable, user-safe error types for the knowledge ingestion path."""

from __future__ import annotations


class IngestionError(Exception):
    """Raised when a document cannot be ingested.

    ``code`` is a stable machine code stored in ``ingestion_jobs.error_code``; the
    message is safe to persist and display because it never contains a stack trace,
    absolute path or document content.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class UnsupportedDocumentType(IngestionError):
    """Raised for a file extension the loader does not support."""

    def __init__(self, suffix: str) -> None:
        super().__init__("UNSUPPORTED_DOC_TYPE", f"不支持的文件类型：{suffix or '无扩展名'}")


class DocumentTooLarge(IngestionError):
    """Raised when the source file exceeds the configured upload limit."""

    def __init__(self, size_bytes: int, limit_bytes: int) -> None:
        super().__init__(
            "DOCUMENT_TOO_LARGE",
            f"文档大小 {size_bytes} 字节超过上限 {limit_bytes} 字节",
        )


class EmptyDocument(IngestionError):
    """Raised when parsing produced no usable text."""

    def __init__(self) -> None:
        super().__init__("EMPTY_DOCUMENT", "文档解析后没有可用文本")


class DocumentParseFailed(IngestionError):
    """Raised when the parser cannot read the file."""

    def __init__(self, detail: str) -> None:
        super().__init__("PARSE_FAILED", f"文档解析失败：{detail}")


class UnsupportedEncoding(IngestionError):
    """Raised when a plain-text file is not valid UTF-8."""

    def __init__(self) -> None:
        super().__init__("UNSUPPORTED_ENCODING", "文本文件不是有效的 UTF-8 编码")


class UnsafeSourcePath(IngestionError):
    """Raised when a source path escapes the project's controlled data directory."""

    def __init__(self) -> None:
        super().__init__("UNSAFE_SOURCE_PATH", "文档路径超出受控目录")


class VectorStoreUnavailable(IngestionError):
    """Raised when Milvus cannot be reached or rejects a write."""

    def __init__(self, detail: str) -> None:
        super().__init__("VECTOR_STORE_UNAVAILABLE", f"向量库不可用：{detail}")


class CollectionSchemaMismatch(IngestionError):
    """Raised when the existing collection does not match the current schema.

    Stage 5 wrote 384-dimensional hashing vectors into a dense-only collection. Mixing
    them with 1024-dimensional BGE-M3 vectors is not recoverable in place, so the store
    refuses to operate and points at the rebuild script instead of writing garbage.
    """

    def __init__(self, detail: str) -> None:
        super().__init__(
            "COLLECTION_SCHEMA_MISMATCH",
            f"向量集合结构不匹配，需要重建：{detail}",
        )


class EmbeddingConfigError(IngestionError):
    """Raised when embedding settings contradict the fixed BGE-M3 contract."""

    def __init__(self, detail: str) -> None:
        super().__init__("EMBEDDING_CONFIG_INVALID", detail)


class EmbeddingModelUnavailable(IngestionError):
    """Raised when the local BGE-M3 weights cannot be loaded."""

    def __init__(self, detail: str) -> None:
        super().__init__("EMBEDDING_MODEL_UNAVAILABLE", detail)


class InvalidEmbeddingError(IngestionError):
    """Raised when a batch produced vectors that must not be indexed.

    Carries an explicit ``retryable`` flag so callers can mark the batch failed and offer
    a retry path instead of writing partially invalid data.
    """

    def __init__(self, code: str, message: str, *, retryable: bool = True) -> None:
        super().__init__(code, message)
        self.retryable = retryable


class RetrievalError(Exception):
    """Retrieval failure with a stable code and an auditable reason.

    Every branch failure surfaces here: the service never silently degrades a hybrid
    query to dense-only, because that would hide a broken sparse index from operators and
    from the evaluation report.
    """

    def __init__(self, code: str, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class NoEvidenceError(RetrievalError):
    """Raised when the knowledge base cannot support an answer."""

    def __init__(self, detail: str = "知识库中没有足够依据") -> None:
        super().__init__("NO_EVIDENCE", detail, retryable=False)
