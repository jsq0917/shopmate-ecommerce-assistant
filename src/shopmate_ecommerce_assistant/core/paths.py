"""Stable filesystem locations for data and generated artefacts."""

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[3]

DATA_DIR = PROJECT_ROOT / "data"
KNOWLEDGE_DIR = DATA_DIR / "knowledge"
EVAL_DIR = DATA_DIR / "eval"
SYNTHETIC_DIR = DATA_DIR / "synthetic"

MANIFEST_PATH = KNOWLEDGE_DIR / "manifest.json"
FAQ_PATH = KNOWLEDGE_DIR / "faq.jsonl"
EVAL_QUESTIONS_PATH = EVAL_DIR / "eval_questions.jsonl"
