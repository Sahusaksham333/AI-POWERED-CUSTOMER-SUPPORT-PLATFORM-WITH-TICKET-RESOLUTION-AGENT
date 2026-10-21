"""Persist the most recent held-out training metrics for the frontend dashboard."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
METRICS_PATH = ROOT / "training" / "model_metrics.json"


def _read() -> dict[str, Any]:
    if METRICS_PATH.exists():
        try:
            return json.loads(METRICS_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"report_title": "Recorded held-out test metrics", "models": []}


def update_metrics(model_key: str, *, accuracy: float | None = None,
                   macro_f1: float | None = None, weighted_f1: float | None = None,
                   top3_hit_rate: float | None = None, top3_overlap_ratio: float | None = None,
                   test_samples: int | None = None, architecture: str | None = None) -> None:
    """Update one model row after a successful held-out evaluation.

    Scores are stored as fractions (0..1), consistent with the dashboard JSON.
    """
    report = _read()
    models = report.setdefault("models", [])
    row = next((item for item in models if item.get("key") == model_key), None)
    if row is None:
        row = {"key": model_key, "name": model_key.replace("_", " ").title()}
        models.append(row)
    if architecture:
        row["architecture"] = architecture
    if accuracy is not None:
        row["accuracy"] = round(float(accuracy), 6)
        row["primary_metric"] = "accuracy"
    if macro_f1 is not None:
        row["macro_f1"] = round(float(macro_f1), 6)
    if weighted_f1 is not None:
        row["weighted_f1"] = round(float(weighted_f1), 6)
    if top3_hit_rate is not None:
        row["top3_hit_rate"] = round(float(top3_hit_rate), 6)
        row["primary_metric"] = "top3_hit_rate"
    if top3_overlap_ratio is not None:
        row["top3_overlap_ratio"] = round(float(top3_overlap_ratio), 6)
    if test_samples is not None:
        row["support"] = int(test_samples)
        report["test_samples"] = int(test_samples)
    row["source_log"] = "Latest local training run"
    row["last_updated"] = datetime.now(timezone.utc).isoformat()
    if model_key == "tags":
        row["assessment"] = (
            "Latest held-out multi-label results. Top-3 hit rate reports whether at least one relevant tag is found; "
            "inspect overlap ratio, precision/recall, and false positives before deployment."
        )
    else:
        row["assessment"] = (
            "Latest held-out evaluation from the most recent completed training run. "
            "Review the class-level report and confidence calibration before operational use."
        )
    report["source"] = "Most recent local training runs, with historical values retained for models not retrained."
    report["note"] = "Metrics are held-out test results from local training scripts. Artifact availability is checked separately."
    METRICS_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
