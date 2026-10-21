"""Application configuration loaded from environment variables and .env."""
from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")


def _path_env(name: str, default: str) -> Path:
    value = Path(os.getenv(name, default)).expanduser()
    return value if value.is_absolute() else (ROOT_DIR / value).resolve()


DATA_PATH = _path_env(
    "SUPPORTPILOT_DATA_PATH", "data/aa_dataset-tickets-multi-lang-5-2-50-version.csv"
)
ARTIFACTS_DIR = _path_env("SUPPORTPILOT_ARTIFACTS_DIR", "artifacts")
KNOWLEDGE_DIR = _path_env("SUPPORTPILOT_KNOWLEDGE_DIR", "knowledge_base")
CHROMA_DIR = _path_env("SUPPORTPILOT_CHROMA_DIR", "artifacts/chroma")
DB_PATH = _path_env("SUPPORTPILOT_DB_PATH", "artifacts/supportpilot.db")
EMBEDDING_MODEL = os.getenv(
    "SUPPORTPILOT_EMBEDDING_MODEL",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
)
OLLAMA_URL = os.getenv("SUPPORTPILOT_OLLAMA_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("SUPPORTPILOT_OLLAMA_MODEL", "gemma3:4b")
TOP_K = int(os.getenv("SUPPORTPILOT_TOP_K", "4"))
MAX_NEW_TOKENS = int(os.getenv("SUPPORTPILOT_MAX_NEW_TOKENS", "512"))
MIN_CLASSIFIER_CONFIDENCE = float(os.getenv("SUPPORTPILOT_MIN_CLASSIFIER_CONFIDENCE", "0.55"))

for directory in (ARTIFACTS_DIR, CHROMA_DIR, DB_PATH.parent):
    directory.mkdir(parents=True, exist_ok=True)
