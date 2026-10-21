"""Fine-tune multilingual XLM-RoBERTa as a multi-label tag classifier.

Example:
    python training/train_tags.py --top-tags 30 --epochs 3
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
from datasets import Dataset
from sklearn.model_selection import train_test_split
from transformers import (
    AutoModelForSequenceClassification, AutoTokenizer, DataCollatorWithPadding,
    Trainer, TrainingArguments, set_seed,
)
from app.supportpilot.config import ARTIFACTS_DIR, DATA_PATH
from app.supportpilot.data_utils import build_tag_lists, load_tickets, top_tag_vocabulary

MODEL_NAME = "FacebookAI/xlm-roberta-base"


def label_matrix(tag_lists: list[list[str]], vocabulary: list[str]) -> np.ndarray:
    indices = {tag: idx for idx, tag in enumerate(vocabulary)}
    matrix = np.zeros((len(tag_lists), len(vocabulary)), dtype=np.float32)
    for row_idx, tags in enumerate(tag_lists):
        for tag in tags:
            if tag in indices:
                matrix[row_idx, indices[tag]] = 1.0
    return matrix


def make_dataset(texts, labels, tokenizer, max_length):
    ds = Dataset.from_dict({"text": texts, "labels": labels.tolist()})
    ds = ds.map(lambda batch: tokenizer(batch["text"], truncation=True, max_length=max_length), batched=True)
    return ds.remove_columns(["text"])


def metrics(eval_pred):
    logits, labels = eval_pred
    probs = 1.0 / (1.0 + np.exp(-np.clip(logits, -40, 40)))
    k = min(3, probs.shape[1])
    top_idx = np.argsort(probs, axis=1)[:, -k:]
    hit_scores, overlaps = [], []
    for i, true_row in enumerate(labels):
        true = set(np.flatnonzero(true_row > 0.5).tolist())
        if not true:
            continue
        pred = set(top_idx[i].tolist())
        overlap = len(true & pred)
        hit_scores.append(float(overlap > 0))
        overlaps.append(overlap / len(true))
    return {"top3_hit_rate": float(np.mean(hit_scores)) if hit_scores else 0.0,
            "top3_overlap_ratio": float(np.mean(overlaps)) if overlaps else 0.0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DATA_PATH)
    parser.add_argument("--output-dir", type=Path, default=ARTIFACTS_DIR / "tags")
    parser.add_argument("--top-tags", type=int, default=30)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--max-length", type=int, default=192)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    set_seed(args.seed)

    df = load_tickets(args.data)
    tags = build_tag_lists(df)
    indices = np.arange(len(df))
    train_val_idx, test_idx = train_test_split(indices, test_size=0.10, random_state=args.seed)
    train_idx, val_idx = train_test_split(train_val_idx, test_size=1/9, random_state=args.seed)
    train_tags = [tags[i] for i in train_idx]
    vocabulary = top_tag_vocabulary(train_tags, limit=args.top_tags)
    if len(vocabulary) < 2:
        raise ValueError("Not enough tags found. Check tag_1 through tag_8 in the dataset.")
    print(f"Rows: train={len(train_idx)}, val={len(val_idx)}, test={len(test_idx)}; tags={len(vocabulary)}")
    print("Tags:", vocabulary)

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    train_y = label_matrix([tags[i] for i in train_idx], vocabulary)
    val_y = label_matrix([tags[i] for i in val_idx], vocabulary)
    test_y = label_matrix([tags[i] for i in test_idx], vocabulary)
    train_ds = make_dataset(df.iloc[train_idx]["text"].tolist(), train_y, tokenizer, args.max_length)
    val_ds = make_dataset(df.iloc[val_idx]["text"].tolist(), val_y, tokenizer, args.max_length)
    test_ds = make_dataset(df.iloc[test_idx]["text"].tolist(), test_y, tokenizer, args.max_length)
    label2id = {label: idx for idx, label in enumerate(vocabulary)}
    id2label = {idx: label for idx, label in enumerate(vocabulary)}
    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_NAME, num_labels=len(vocabulary), id2label=id2label, label2id=label2id,
        problem_type="multi_label_classification",
    )
    out = args.output_dir.resolve()
    train_args = TrainingArguments(
        output_dir=str(out), learning_rate=2e-5, num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size, per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=4, weight_decay=0.01,
        fp16=torch.cuda.is_available(), gradient_checkpointing=torch.cuda.is_available(),
        eval_strategy="epoch", save_strategy="epoch", save_total_limit=2,
        load_best_model_at_end=True, metric_for_best_model="top3_overlap_ratio",
        greater_is_better=True, logging_steps=50, report_to="none", seed=args.seed,
        dataloader_num_workers=0,
    )
    trainer = Trainer(
        model=model, args=train_args, train_dataset=train_ds, eval_dataset=val_ds,
        data_collator=DataCollatorWithPadding(tokenizer=tokenizer), processing_class=tokenizer,
        compute_metrics=metrics,
    )
    trainer.train()
    test_result = trainer.predict(test_ds)
    test_metrics = metrics((test_result.predictions, test_result.label_ids))
    print("Held-out test metrics:", json.dumps(test_metrics, indent=2))
    out.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(out))
    tokenizer.save_pretrained(out)
    (out / "tag_vocabulary.json").write_text(json.dumps(vocabulary, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "training_metadata.json").write_text(json.dumps({
        "model_name": MODEL_NAME, "task": "multi_label_classification", "labels": vocabulary,
        "test_metrics": test_metrics, "rows": {"total": len(df), "train": len(train_idx), "validation": len(val_idx), "test": len(test_idx)},
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved tag classifier to: {out}")

if __name__ == "__main__":
    main()
