"""Lazy-loaded Hugging Face models used by the online ticket pipeline."""
from __future__ import annotations
from pathlib import Path
from typing import Any
import torch
import torch.nn.functional as F
from transformers import AutoModelForSequenceClassification, AutoTokenizer
from .config import ARTIFACTS_DIR


class ClassifierService:
    def __init__(self, device: str | None = None):
        # CPU is the default so an 8 GB GPU remains available to Ollama/Gemma.
        # Set SUPPORTPILOT_CLASSIFIER_DEVICE=cuda to benchmark GPU inference.
        import os
        requested = device or os.getenv("SUPPORTPILOT_CLASSIFIER_DEVICE", "cpu")
        self.device = torch.device("cuda" if requested == "cuda" and torch.cuda.is_available() else "cpu")
        self._models: dict[str, tuple[Any, Any]] = {}

    def _load(self, target: str):
        if target in self._models:
            return self._models[target]
        model_dir = ARTIFACTS_DIR / target
        if not (model_dir / "config.json").exists():
            return None
        tokenizer = AutoTokenizer.from_pretrained(model_dir, local_files_only=True)
        model = AutoModelForSequenceClassification.from_pretrained(model_dir, local_files_only=True)
        model.to(self.device).eval()
        self._models[target] = (tokenizer, model)
        return tokenizer, model

    def predict(self, target: str, text: str, max_length: int = 192) -> dict[str, Any]:
        loaded = self._load(target)
        if loaded is None:
            return {"label": None, "confidence": None, "available": False,
                    "detail": f"No trained model found at artifacts/{target}. Train it with training/train_classifier.py."}
        tokenizer, model = loaded
        inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=max_length)
        inputs = {key: value.to(self.device) for key, value in inputs.items()}
        with torch.inference_mode():
            logits = model(**inputs).logits
            probabilities = F.softmax(logits, dim=-1)[0]
        index = int(torch.argmax(probabilities).item())
        labels = model.config.id2label
        label = labels.get(index, labels.get(str(index), str(index)))
        return {"label": str(label), "confidence": round(float(probabilities[index].item()), 4),
                "available": True, "detail": None}

    def predict_tags(self, text: str, top_k: int = 3, max_length: int = 192) -> list[dict[str, Any]]:
        loaded = self._load("tags")
        if loaded is None:
            return []
        tokenizer, model = loaded
        inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=max_length)
        inputs = {key: value.to(self.device) for key, value in inputs.items()}
        with torch.inference_mode():
            probs = torch.sigmoid(model(**inputs).logits)[0]
        k = min(max(1, top_k), len(probs))
        values, indices = torch.topk(probs, k=k)
        result = []
        for value, idx in zip(values.tolist(), indices.tolist()):
            label = model.config.id2label.get(idx, model.config.id2label.get(str(idx), str(idx)))
            result.append({"tag": str(label), "confidence": round(float(value), 4)})
        return result

    def health(self) -> dict[str, Any]:
        available = {target: (ARTIFACTS_DIR / target / "config.json").exists()
                     for target in ("queue", "priority", "type", "tags")}
        return {"device": str(self.device), "available_models": available}
