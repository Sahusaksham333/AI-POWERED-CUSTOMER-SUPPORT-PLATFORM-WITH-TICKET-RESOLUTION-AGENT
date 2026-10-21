"""Train a TextCNN baseline for a single target using XLM-R tokenizer IDs.

This benchmark lets the project compare a CNN architecture with a transformer.
It is a text CNN, not an image CNN. Run:
    python training/train_textcnn.py --target queue --epochs 4
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import train_test_split
from transformers import AutoTokenizer, set_seed
from app.supportpilot.config import ARTIFACTS_DIR, DATA_PATH
from app.supportpilot.data_utils import TARGET_COLUMNS, load_tickets

MODEL_NAME = "FacebookAI/xlm-roberta-base"

class TextCNN(nn.Module):
    def __init__(self, vocab_size: int, num_classes: int, pad_token_id: int, embedding_dim: int = 128, channels: int = 128):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, embedding_dim, padding_idx=pad_token_id)
        self.convs = nn.ModuleList([nn.Conv1d(embedding_dim, channels, kernel_size=k, padding=k // 2) for k in (2, 3, 4)])
        self.dropout = nn.Dropout(0.3)
        self.output = nn.Linear(channels * len(self.convs), num_classes)

    def forward(self, input_ids):
        x = self.embedding(input_ids).transpose(1, 2)
        pooled = [torch.amax(torch.relu(conv(x)), dim=2) for conv in self.convs]
        return self.output(self.dropout(torch.cat(pooled, dim=1)))


def tokenize_batch(texts, tokenizer, max_length):
    encoded = tokenizer(texts, truncation=True, padding="max_length", max_length=max_length, return_tensors="pt")
    return encoded["input_ids"]


def evaluate(model, loader, device):
    model.eval()
    truth, preds = [], []
    with torch.inference_mode():
        for input_ids, labels in loader:
            logits = model(input_ids.to(device))
            preds.extend(logits.argmax(-1).cpu().tolist())
            truth.extend(labels.tolist())
    return np.asarray(truth), np.asarray(preds)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=TARGET_COLUMNS, default="queue")
    parser.add_argument("--data", type=Path, default=DATA_PATH)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--epochs", type=int, default=4)
    parser.add_argument("--max-length", type=int, default=192)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--learning-rate", type=float, default=2e-3)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    set_seed(args.seed)
    df = load_tickets(args.data).dropna(subset=[args.target]).copy()
    classes = sorted(df[args.target].astype(str).unique().tolist())
    label2id = {label: idx for idx, label in enumerate(classes)}
    y = df[args.target].astype(str).map(label2id).to_numpy()
    train_val_idx, test_idx = train_test_split(np.arange(len(df)), test_size=0.1, random_state=args.seed, stratify=y)
    train_idx, val_idx = train_test_split(train_val_idx, test_size=1/9, random_state=args.seed, stratify=y[train_val_idx])
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    x_train = tokenize_batch(df.iloc[train_idx]["text"].tolist(), tokenizer, args.max_length)
    x_val = tokenize_batch(df.iloc[val_idx]["text"].tolist(), tokenizer, args.max_length)
    x_test = tokenize_batch(df.iloc[test_idx]["text"].tolist(), tokenizer, args.max_length)
    y_tensor = torch.tensor(y, dtype=torch.long)
    train_loader = DataLoader(TensorDataset(x_train, y_tensor[train_idx]), batch_size=args.batch_size, shuffle=True)
    val_loader = DataLoader(TensorDataset(x_val, y_tensor[val_idx]), batch_size=args.batch_size)
    test_loader = DataLoader(TensorDataset(x_test, y_tensor[test_idx]), batch_size=args.batch_size)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = TextCNN(len(tokenizer), len(classes), tokenizer.pad_token_id).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=0.01)
    criterion = nn.CrossEntropyLoss()
    best_f1, best_state = -1.0, None
    for epoch in range(1, args.epochs + 1):
        model.train()
        running_loss = 0.0
        for input_ids, labels in train_loader:
            input_ids, labels = input_ids.to(device), labels.to(device)
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(model(input_ids), labels)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            running_loss += loss.item()
        y_val, p_val = evaluate(model, val_loader, device)
        macro_f1 = f1_score(y_val, p_val, average="macro", zero_division=0)
        print(f"epoch={epoch} loss={running_loss / max(1, len(train_loader)):.4f} val_accuracy={accuracy_score(y_val,p_val):.4f} val_macro_f1={macro_f1:.4f}")
        if macro_f1 > best_f1:
            best_f1 = macro_f1
            best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
    if best_state is not None:
        model.load_state_dict(best_state)
    y_test, p_test = evaluate(model, test_loader, device)
    print("\nHeld-out test report:")
    print(classification_report(y_test, p_test, labels=list(range(len(classes))), target_names=classes, zero_division=0))
    out = (args.output_dir or (ARTIFACTS_DIR / f"textcnn_{args.target}")).resolve()
    out.mkdir(parents=True, exist_ok=True)
    torch.save({"state_dict": model.cpu().state_dict(), "vocab_size": len(tokenizer), "num_classes": len(classes),
                "pad_token_id": tokenizer.pad_token_id, "embedding_dim": 128, "channels": 128,
                "max_length": args.max_length, "classes": classes, "target": args.target}, out / "textcnn.pt")
    tokenizer.save_pretrained(out / "tokenizer")
    (out / "training_metadata.json").write_text(json.dumps({"target": args.target, "classes": classes,
        "test_accuracy": float(accuracy_score(y_test, p_test)), "test_macro_f1": float(f1_score(y_test, p_test, average="macro", zero_division=0))}, indent=2), encoding="utf-8")
    print(f"Saved TextCNN model: {out}")

if __name__ == "__main__":
    main()
