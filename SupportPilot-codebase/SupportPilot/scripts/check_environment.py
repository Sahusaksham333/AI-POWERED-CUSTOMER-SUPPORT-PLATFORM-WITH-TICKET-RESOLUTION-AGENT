"""Print dependency, GPU and local Ollama diagnostics without loading an LLM."""
from __future__ import annotations
import sys
import importlib
from pathlib import Path
import requests
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.supportpilot.config import OLLAMA_URL, OLLAMA_MODEL, DATA_PATH

MODULES = ["torch", "transformers", "datasets", "sentence_transformers", "chromadb", "fastapi", "streamlit"]

def main():
    print(f"Python: {sys.version.split()[0]}")
    print(f"Dataset exists: {DATA_PATH.exists()} ({DATA_PATH})")
    for name in MODULES:
        try:
            module = importlib.import_module(name)
            print(f"{name}: OK {getattr(module, '__version__', '')}")
            if name == "torch":
                import torch
                print(f"  CUDA available: {torch.cuda.is_available()}")
                print(f"  CUDA build: {torch.version.cuda}")
                if torch.cuda.is_available():
                    print(f"  GPU: {torch.cuda.get_device_name(0)}")
        except Exception as exc:
            print(f"{name}: ERROR {exc}")
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        response.raise_for_status()
        names = [m.get("name") for m in response.json().get("models", [])]
        print(f"Ollama: reachable at {OLLAMA_URL}")
        print(f"Configured model ({OLLAMA_MODEL}) present: {any(n == OLLAMA_MODEL or (n and n.split(':')[0] == OLLAMA_MODEL.split(':')[0]) for n in names)}")
        print(f"Installed models: {names}")
    except Exception as exc:
        print(f"Ollama: unavailable ({exc})")

if __name__ == "__main__":
    main()
