"""Knowledge ingestion: loaders, manifest and the persistence pipeline."""

from shopmate_ecommerce_assistant.rag.ingest.loaders import LoadedDocument, load_document
from shopmate_ecommerce_assistant.rag.ingest.manifest import Manifest, SourceSpec, load_manifest
from shopmate_ecommerce_assistant.rag.ingest.pipeline import IngestOutcome, ingest_source

__all__ = [
    "IngestOutcome",
    "LoadedDocument",
    "Manifest",
    "SourceSpec",
    "ingest_source",
    "load_document",
    "load_manifest",
]
