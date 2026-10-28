
"""Lazy-loaded Hugging Face models used by the online ticket pipeline."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import torch
import torch.nn.functional as F
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
)

from .config import ARTIFACTS_DIR


class ClassifierService:
    """Load and run trained SupportPilot models on demand."""

    SUPPORTED_TARGETS = ("queue", "priority", "type", "tags")

    def __init__(self, device: str | None = None):
        # CPU by default, preserving GPU memory for Ollama/Gemma.
        # Set SUPPORTPILOT_CLASSIFIER_DEVICE=cuda to request GPU inference.
        requested = (
            device
            or os.getenv("SUPPORTPILOT_CLASSIFIER_DEVICE", "cpu")
        ).lower()

        self.device = torch.device(
            "cuda"
            if requested == "cuda" and torch.cuda.is_available()
            else "cpu"
        )

        self._models: dict[str, tuple[Any, Any]] = {}

    def _load(self, target: str):
        """Load and cache the tokenizer and model for one target."""

        if target not in self.SUPPORTED_TARGETS:
            raise ValueError(
                f"Unsupported target: {target!r}. "
                f"Supported targets: {self.SUPPORTED_TARGETS}"
            )

        if target in self._models:
            return self._models[target]

        model_dir = Path(ARTIFACTS_DIR) / target

        if not (model_dir / "config.json").is_file():
            return None

        # The artifacts identify themselves as XLM-RoBERTa.
        # This flag belongs on AutoTokenizer, NOT the model loader.
        # Explicitly disable the unrelated Mistral-specific correction.
        tokenizer = AutoTokenizer.from_pretrained(
            model_dir,
            local_files_only=True,
            fix_mistral_regex=False,
        )

        model = AutoModelForSequenceClassification.from_pretrained(
            model_dir,
            local_files_only=True,
        )

        model.to(self.device)
        model.eval()

        self._models[target] = (tokenizer, model)
        return tokenizer, model

    def predict(
        self,
        target: str,
        text: str,
        max_length: int = 192,
    ) -> dict[str, Any]:
        """Predict the queue, priority, or ticket type."""

        loaded = self._load(target)

        if loaded is None:
            return {
                "label": None,
                "confidence": None,
                "available": False,
                "detail": (
                    f"No trained model found at artifacts/{target}. "
                    "Check that the model artifacts are present."
                ),
            }

        tokenizer, model = loaded

        inputs = tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=max_length,
        )
        inputs = {
            key: value.to(self.device)
            for key, value in inputs.items()
        }

        with torch.inference_mode():
            logits = model(**inputs).logits
            probabilities = F.softmax(logits, dim=-1)[0]

        index = int(torch.argmax(probabilities).item())
        labels = model.config.id2label

        label = labels.get(
            index,
            labels.get(str(index), str(index)),
        )

        return {
            "label": str(label),
            "confidence": round(
                float(probabilities[index].item()),
                4,
            ),
            "available": True,
            "detail": None,
        }

    def predict_tags(
        self,
        text: str,
        top_k: int = 3,
        max_length: int = 192,
    ) -> list[dict[str, Any]]:
        """Return the top-scoring tags from the multi-label model."""

        loaded = self._load("tags")

        if loaded is None:
            return []

        tokenizer, model = loaded

        inputs = tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=max_length,
        )
        inputs = {
            key: value.to(self.device)
            for key, value in inputs.items()
        }

        with torch.inference_mode():
            probabilities = torch.sigmoid(
                model(**inputs).logits
            )[0]

        if probabilities.numel() == 0:
            return []

        k = min(max(1, top_k), probabilities.numel())
        values, indices = torch.topk(probabilities, k=k)
        labels = model.config.id2label

        results: list[dict[str, Any]] = []

        for value, index in zip(
            values.tolist(),
            indices.tolist(),
        ):
            label = labels.get(
                index,
                labels.get(str(index), str(index)),
            )

            results.append({
                "tag": str(label),
                "confidence": round(float(value), 4),
            })

        return results

    def health(self) -> dict[str, Any]:
        """Report device selection and the presence of model artifacts."""

        artifacts_dir = Path(ARTIFACTS_DIR)

        available = {
            target: (
                artifacts_dir / target / "config.json"
            ).is_file()
            for target in self.SUPPORTED_TARGETS
        }

        return {
            "device": str(self.device),
            "available_models": available,
        }
