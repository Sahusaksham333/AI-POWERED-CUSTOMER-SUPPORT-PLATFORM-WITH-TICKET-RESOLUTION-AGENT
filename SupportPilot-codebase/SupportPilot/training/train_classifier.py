"""Fine-tune XLM-RoBERTa for one single-label target: queue, type, or priority.

Example:
    python training/train_classifier.py --target queue --epochs 3
    python training/train_classifier.py --target priority --epochs 3
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import torch
from datasets import Dataset
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import train_test_split
from transformers import (
    AutoModelForSequenceClassification, AutoTokenizer, DataCollatorWithPadding,
    Trainer, TrainingArguments, set_seed,
)
from app.supportpilot.config import ARTIFACTS_DIR, DATA_PATH
from app.supportpilot.data_utils import TARGET_COLUMNS, load_tickets

MODEL_NAME = "FacebookAI/xlm-roberta-base"


def to_dataset(texts: list[str], labels: list[int], tokenizer, max_length: int) -> Dataset:
    ds = Dataset.from_dict({"text": texts, "labels": labels})
    ds = ds.map(lambda batch: tokenizer(batch["text"], truncation=True, max_length=max_length), batched=True)
    return ds.remove_columns(["text"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=TARGET_COLUMNS, default="queue")
    parser.add_argument("--data", type=Path, default=DATA_PATH)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--max-length", type=int, default=192)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    set_seed(args.seed)
    df = load_tickets(args.data).dropna(subset=[args.target]).copy()
    df[args.target] = df[args.target].astype(str)
    label_names = sorted(df[args.target].unique().tolist())
    label2id = {label: idx for idx, label in enumerate(label_names)}
    df["label_id"] = df[args.target].map(label2id).astype(int)

    # 80/10/10 split: the held-out test set is not used for checkpoint selection.
    train_val, test = train_test_split(
        df, test_size=0.10, random_state=args.seed, stratify=df["label_id"]
    )
    train, val = train_test_split(
        train_val, test_size=1 / 9, random_state=args.seed, stratify=train_val["label_id"]
    )
    print(f"Rows: total={len(df)}, train={len(train)}, validation={len(val)}, test={len(test)}")
    print(f"Target={args.target}; classes={len(label_names)}; CUDA={torch.cuda.is_available()}")

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    train_ds = to_dataset(train["text"].tolist(), train["label_id"].tolist(), tokenizer, args.max_length)
    val_ds = to_dataset(val["text"].tolist(), val["label_id"].tolist(), tokenizer, args.max_length)
    test_ds = to_dataset(test["text"].tolist(), test["label_id"].tolist(), tokenizer, args.max_length)
    id2label = {i: label for i, label in enumerate(label_names)}
    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_NAME, num_labels=len(label_names), id2label=id2label, label2id=label2id
    )

    output_dir = args.output_dir or (ARTIFACTS_DIR / args.target)
    output_dir = output_dir.resolve()
    training_args = TrainingArguments(
        output_dir=str(output_dir),
        learning_rate=args.learning_rate,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=4,
        weight_decay=0.01,
        fp16=torch.cuda.is_available(),
        gradient_checkpointing=torch.cuda.is_available(),
        eval_strategy="epoch",
        save_strategy="epoch",
        save_total_limit=2,
        load_best_model_at_end=True,
        metric_for_best_model="f1_macro",
        greater_is_better=True,
        logging_steps=50,
        report_to="none",
        seed=args.seed,
        dataloader_num_workers=0,
    )

    def compute_metrics(eval_pred):
        logits, labels = eval_pred
        predictions = np.argmax(logits, axis=-1)
        return {
            "accuracy": accuracy_score(labels, predictions),
            "f1_macro": f1_score(labels, predictions, average="macro", zero_division=0),
            "f1_weighted": f1_score(labels, predictions, average="weighted", zero_division=0),
        }

    trainer = Trainer(
        model=model, args=training_args, train_dataset=train_ds, eval_dataset=val_ds,
        data_collator=DataCollatorWithPadding(tokenizer=tokenizer),
        processing_class=tokenizer, compute_metrics=compute_metrics,
    )
    trainer.train()
    test_result = trainer.predict(test_ds)
    test_pred = np.argmax(test_result.predictions, axis=1)
    print("\nHeld-out test results:")
    print(classification_report(test_result.label_ids, test_pred, labels=list(range(len(label_names))),
                                target_names=label_names, zero_division=0))
    output_dir.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(output_dir))
    tokenizer.save_pretrained(output_dir)
    (output_dir / "training_metadata.json").write_text(json.dumps({
        "target": args.target, "model_name": MODEL_NAME, "labels": label_names,
        "test_metrics": compute_metrics((test_result.predictions, test_result.label_ids)),
        "rows": {"total": len(df), "train": len(train), "validation": len(val), "test": len(test)},
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved model to: {output_dir}")

if __name__ == "__main__":
    main()
