"""Lazy-loaded Hugging Face models used by the online ticket pipeline."""
from __future__ import annotations
from pathlib import Path
from typing import Any
import torch
from torch import nn
import torch.nn.functional as F
from transformers import AutoModelForSequenceClassification, AutoTokenizer
from .config import ARTIFACTS_DIR


class TextCNN(nn.Module):
    """Must remain architecture-compatible with training/train_textcnn.py."""
    def __init__(self, vocab_size: int, num_classes: int, pad_token_id: int,
                 embedding_dim: int = 128, channels: int = 128):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, embedding_dim, padding_idx=pad_token_id)
        self.convs = nn.ModuleList([
            nn.Conv1d(embedding_dim, channels, kernel_size=k, padding=k // 2)
            for k in (2, 3, 4)
        ])
        self.dropout = nn.Dropout(0.3)
        self.output = nn.Linear(channels * len(self.convs), num_classes)

    def forward(self, input_ids):
        x = self.embedding(input_ids).transpose(1, 2)
        pooled = [torch.amax(torch.relu(conv(x)), dim=2) for conv in self.convs]
        return self.output(self.dropout(torch.cat(pooled, dim=1)))


class ClassifierService:
    def __init__(self, device: str | None = None):
        # CPU is the default so an 8 GB GPU remains available to Ollama/Gemma.
        # Set SUPPORTPILOT_CLASSIFIER_DEVICE=cuda to benchmark GPU inference.
        import os
        requested = device or os.getenv("SUPPORTPILOT_CLASSIFIER_DEVICE", "cpu")
        self.device = torch.device("cuda" if requested == "cuda" and torch.cuda.is_available() else "cpu")
        self._models: dict[str, tuple[Any, Any]] = {}
        self._textcnn: tuple[Any, Any, dict[str, Any]] | None = None
        self._textcnn_attempted = False
        self._textcnn_error: str | None = None

    def _load(self, target: str):
        if target in self._models:
            return self._models[target]
        model_dir = ARTIFACTS_DIR / target
        if not (model_dir / "config.json").exists():
            return None
        tokenizer = AutoTokenizer.from_pretrained(
            model_dir,
            local_files_only=True,
            fix_mistral_regex=False,
        )
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

    def _load_textcnn(self):
        if self._textcnn is not None:
            return self._textcnn
        if self._textcnn_attempted:
            return None
        self._textcnn_attempted = True
        model_dir = ARTIFACTS_DIR / "textcnn_queue"
        checkpoint_path = model_dir / "textcnn.pt"
        tokenizer_dir = model_dir / "tokenizer"
        if not checkpoint_path.is_file() or not tokenizer_dir.is_dir():
            self._textcnn_error = f"TextCNN checkpoint/tokenizer not found under {model_dir}"
            return None
        try:
            try:
                checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
            except TypeError:  # Backward compatibility with older supported PyTorch builds.
                checkpoint = torch.load(checkpoint_path, map_location="cpu")
            tokenizer = AutoTokenizer.from_pretrained(
                tokenizer_dir,
                local_files_only=True,
                fix_mistral_regex=False,
            )
            model = TextCNN(
                vocab_size=int(checkpoint["vocab_size"]),
                num_classes=int(checkpoint["num_classes"]),
                pad_token_id=int(checkpoint["pad_token_id"]),
                embedding_dim=int(checkpoint.get("embedding_dim", 128)),
                channels=int(checkpoint.get("channels", 128)),
            )
            model.load_state_dict(checkpoint["state_dict"])
            model.to(self.device).eval()
            meta = {"classes": checkpoint["classes"], "max_length": int(checkpoint.get("max_length", 192))}
            self._textcnn = (tokenizer, model, meta)
            return self._textcnn
        except Exception as exc:
            self._textcnn_error = f"Could not load TextCNN checkpoint: {exc}"
            return None

    def predict_textcnn(self, text: str) -> dict[str, Any]:
        loaded = self._load_textcnn()
        if loaded is None:
            return {"label": None, "confidence": None, "available": False,
                    "detail": self._textcnn_error or "TextCNN model unavailable"}
        tokenizer, model, meta = loaded
        encoded = tokenizer(
            text, truncation=True, padding="max_length", max_length=meta["max_length"],
            return_tensors="pt",
        )
        inputs = encoded["input_ids"].to(self.device)
        with torch.inference_mode():
            probabilities = F.softmax(model(inputs), dim=-1)[0]
        index = int(torch.argmax(probabilities).item())
        classes = meta["classes"]
        return {"label": str(classes[index]), "confidence": round(float(probabilities[index].item()), 4),
                "available": True, "detail": None}

    def health(self) -> dict[str, Any]:
        available = {target: (ARTIFACTS_DIR / target / "config.json").exists()
                     for target in ("queue", "priority", "type", "tags")}
        textcnn_dir = ARTIFACTS_DIR / "textcnn_queue"
        available["textcnn_queue"] = (textcnn_dir / "textcnn.pt").is_file() and (textcnn_dir / "tokenizer").is_dir()
        return {"device": str(self.device), "available_models": available,
                "textcnn_error": self._textcnn_error}
