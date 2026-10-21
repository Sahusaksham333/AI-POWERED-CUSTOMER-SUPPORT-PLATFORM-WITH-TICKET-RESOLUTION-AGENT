# SupportPilot — Milestone 1 README

## Ticket Processing and Classification (Weeks 1–2)

SupportPilot is a local-first, multilingual IT support-ticket triage application. Milestone 1 focuses on capturing a ticket, predicting its queue/type/priority and tags, recording it, and displaying ticket status and basic analytics. This README documents the implemented scope and the evaluation scores in the supplied training logs.

> **Evaluation transparency:** Scores below are copied from the supplied held-out evaluation logs. They are historical test results, not a live benchmark. The model acceptance targets in the project brief are listed separately from measured results. Do not interpret a model score as a guarantee for an individual ticket.

## 1. Milestone 1 objectives

The project brief lists these Week 1–2 requirements:

- Implement ticket submission and intake.
- Develop an AI-based ticket classification engine.
- Generate severity and priority scores.
- Target: successfully classify at least 90% of support tickets.
- Target: severity-prediction accuracy of at least 85%.

### Scope implemented in the current codebase

- Ticket creation through the web form.
- Prediction of queue, ticket type, and priority using saved XLM-RoBERTa classifiers when those artifacts are available.
- Multi-label ticket tagging using the trained tag model when available.
- Optional TextCNN queue-classification benchmark.
- Ticket persistence in local SQLite, ticket retrieval, status updates, and dashboard analytics.
- FastAPI endpoints for prediction and downstream resolution drafting.
- A frontend with Overview, All Tickets, Create Ticket, Priority Queue, and Model Performance views.

The knowledge-retrieval and generated-response workflow is part of the wider project. It is not required to claim Milestone 1 classification targets as achieved.

## 2. Dataset and evaluation setup

| Item | Value |
|---|---|
| Dataset | `aa_dataset-tickets-multi-lang-5-2-50-version.csv` |
| Total rows reported in training logs | 28,587 |
| Training split | 22,869 rows |
| Validation split | 2,859 rows |
| Held-out test split | 2,859 rows |
| Split proportions | Approximately 80% / 10% / 10% |
| Main classifier | `FacebookAI/xlm-roberta-base` fine-tuned for each single-label target |
| Tag classifier | XLM-RoBERTa multi-label model, restricted to the top 30 tags in this run |
| Baseline | Custom TextCNN queue classifier |
| Evaluation source | `train.txt`, `train1.txt`, `train2.txt`, `train3.txt`, and `train4.txt` |

All single-label test reports below use the same reported test-set size of 2,859 examples. The target fields are `queue`, `type`, and `priority`. The CSV does not provide a separately verified `severity` label; therefore, priority classification is **not** reported as severity accuracy.

## 3. Held-out test results — summary

| Task | Model | Accuracy / primary metric | Macro F1 | Weighted F1 / overlap | Status |
|---|---|---:|---:|---:|---|
| Queue classification | XLM-RoBERTa-base | 48.00% accuracy | 37.00% | 46.00% weighted F1 | Needs improvement |
| Priority classification | XLM-RoBERTa-base | 51.00% accuracy | 45.00% | 49.00% weighted F1 | Needs improvement |
| Ticket-type classification | XLM-RoBERTa-base | 85.00% accuracy | 85.00% | 84.00% weighted F1 | Strongest single-label result |
| Multi-label tags (top 30) | XLM-RoBERTa-base | 98.98% top-3 hit rate | Not reported | 62.84% top-3 overlap ratio | Interpret carefully |
| Queue benchmark | TextCNN | 46.00% accuracy | 37.00% | 43.00% weighted F1 | Below XLM-R queue model |

**Metric caveat for tags:** the 98.98% top-3 hit rate does **not** mean 98.98% of every predicted tag is correct. It describes the specific top-3-hit metric used by the supplied training script. The reported top-3 overlap ratio is 62.84%.

## 4. XLM-RoBERTa — queue classification

### Training/validation progression

| Epoch | Validation loss | Validation accuracy | Validation macro F1 | Validation weighted F1 |
|---:|---:|---:|---:|---:|
| 1 | 1.5863 | 41.62% | 28.73% | 39.21% |
| 2 | 1.5023 | 44.74% | 33.31% | 41.87% |
| 3 | 1.4824 | 46.03% | 35.90% | 43.54% |

### Held-out per-class metrics

| Queue class | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| Billing and Payments | 79% | 71% | 75% | 279 |
| Customer Service | 37% | 37% | 37% | 427 |
| General Inquiry | 0% | 0% | 0% | 40 |
| Human Resources | 75% | 5% | 10% | 58 |
| IT Support | 37% | 26% | 30% | 343 |
| Product Support | 41% | 41% | 41% | 525 |
| Returns and Exchanges | 70% | 18% | 29% | 144 |
| Sales and Pre-Sales | 47% | 15% | 23% | 92 |
| Service Outages and Maintenance | 67% | 69% | 68% | 115 |
| Technical Support | 48% | 70% | 57% | 836 |
| **Overall accuracy** |  |  | **48%** | **2,859** |
| **Macro average** | **50%** | **35%** | **37%** | **2,859** |
| **Weighted average** | **48%** | **48%** | **46%** | **2,859** |

**Interpretation:** queue accuracy is substantially below the project target of 90%. Human Resources and General Inquiry are particularly weak, and recall varies markedly by class. Predictions should be used as triage suggestions with human oversight.

## 5. XLM-RoBERTa — priority classification

### Training/validation progression

| Epoch | Validation loss | Validation accuracy | Validation macro F1 | Validation weighted F1 |
|---:|---:|---:|---:|---:|
| 1 | 1.0347 | 46.41% | 34.12% | 40.67% |
| 2 | 1.0041 | 48.13% | 35.76% | 42.59% |
| 3 | 0.9852 | 50.75% | 45.35% | 49.03% |

### Held-out per-class metrics

| Priority | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| High | 60% | 59% | 60% | 1,118 |
| Low | 40% | 16% | 23% | 589 |
| Medium | 47% | 61% | 53% | 1,152 |
| **Overall accuracy** |  |  | **51%** | **2,859** |
| **Macro average** | **49%** | **46%** | **45%** | **2,859** |
| **Weighted average** | **50%** | **51%** | **49%** | **2,859** |

**Interpretation:** priority accuracy is 51%. Recall for Low priority is only 16%, so the model may miss low-priority cases or confuse them with other classes. Priority scores are not calibrated operational-risk probabilities. This metric does not validate the brief's separate severity-accuracy target.

## 6. XLM-RoBERTa — ticket-type classification

### Training/validation progression

| Epoch | Validation loss | Validation accuracy | Validation macro F1 | Validation weighted F1 |
|---:|---:|---:|---:|---:|
| 1 | 0.3756 | 81.08% | 83.16% | 81.33% |
| 2 | 0.3520 | 82.65% | 83.86% | 82.56% |
| 3 | 0.3661 | 84.47% | 85.45% | 84.29% |

### Held-out per-class metrics

| Ticket type | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| Change | 98% | 98% | 98% | 292 |
| Incident | 80% | 83% | 82% | 1,147 |
| Problem | 66% | 60% | 63% | 601 |
| Request | 99% | 99% | 99% | 819 |
| **Overall accuracy** |  |  | **85%** | **2,859** |
| **Macro average** | **86%** | **85%** | **85%** | **2,859** |
| **Weighted average** | **84%** | **85%** | **84%** | **2,859** |

**Interpretation:** ticket type is the strongest single-label classifier in the supplied logs. Its held-out accuracy is approximately 85%, but this is still below the brief's 90% classification target if that target is interpreted as accuracy across all tickets. Per-class performance should be monitored after deployment.

## 7. Multi-label tag classifier

The tag model was trained for the 30 most frequent tags selected by the supplied training script:

`Tech Support`, `IT`, `Performance`, `Feedback`, `Bug`, `Security`, `Feature`, `Documentation`, `Disruption`, `Outage`, `Network`, `Product`, `Recovery`, `Sales`, `Hardware`, `Billing`, `Support`, `Payment`, `Marketing`, `Maintenance`, `Crash`, `Software`, `Integration`, `Virus`, `Account`, `Strategy`, `Refund`, `Alert`, `Compliance`, `Campaign`.

| Metric | Validation result at epoch 3 | Held-out test result |
|---|---:|---:|
| Evaluation loss | 0.1492 | Not reported as a separate test metric |
| Top-3 hit rate | 98.88% | 98.98% |
| Top-3 overlap ratio | 62.35% | 62.84% |

The tag run used 22,869 training examples, 2,859 validation examples, and 2,859 test examples. These custom multi-label metrics are not equivalent to exact-match accuracy, micro-F1, or macro-F1. Those metrics should be added if a more complete comparison is required.

## 8. TextCNN — queue-classification benchmark

### Epoch progression

| Epoch | Training loss | Validation accuracy | Validation macro F1 |
|---:|---:|---:|---:|
| 1 | 1.9343 | 39.49% | 21.87% |
| 2 | 1.7302 | 42.67% | 30.18% |
| 3 | 1.5532 | 43.62% | 35.50% |
| 4 | 1.3105 | 44.74% | 37.06% |

### Held-out per-class metrics

| Queue class | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| Billing and Payments | 73% | 75% | 74% | 279 |
| Customer Service | 58% | 16% | 25% | 427 |
| General Inquiry | 23% | 23% | 23% | 40 |
| Human Resources | 100% | 16% | 27% | 58 |
| IT Support | 48% | 20% | 29% | 343 |
| Product Support | 32% | 58% | 41% | 525 |
| Returns and Exchanges | 77% | 14% | 24% | 144 |
| Sales and Pre-Sales | 50% | 7% | 12% | 92 |
| Service Outages and Maintenance | 64% | 66% | 65% | 115 |
| Technical Support | 47% | 65% | 55% | 836 |
| **Overall accuracy** |  |  | **46%** | **2,859** |
| **Macro average** | **57%** | **36%** | **37%** | **2,859** |
| **Weighted average** | **52%** | **46%** | **43%** | **2,859** |

**Comparison:** XLM-R queue classification achieved 48% held-out accuracy and 46% weighted F1, versus TextCNN's 46% accuracy and 43% weighted F1. Based on these reported metrics, the TextCNN is a benchmark rather than the preferred queue model.

## 9. Milestone 1 acceptance check

| Project-brief criterion | Target | Evidence currently available | Assessment |
|---|---|---|---|
| Ticket intake | Submission and ingestion functional | Web form and FastAPI ticket endpoints are present in the codebase | Verify with an end-to-end run |
| Ticket classification | At least 90% of tickets classified | Queue accuracy 48%; type accuracy 85%; priority accuracy 51% | **Not demonstrated at target level** if interpreted as model accuracy |
| Severity prediction | At least 85% accuracy | Dataset/model logs report priority, not a separately labeled severity target | **Not verified** |
| Priority scoring | Assign a priority label | Priority model test accuracy 51% | Implemented, but model quality needs improvement |
| Persist tickets and track status | Persist records and lifecycle changes | SQLite and status endpoints/UI are included in the project code | Verify with end-to-end tests |

The phrase “successfully classify at least 90% of support tickets” could mean classification coverage rather than accuracy. The logs establish predictive accuracy, not the percentage of incoming requests successfully processed by the API. Report coverage separately once measured in an end-to-end test.

## 10. Run the project locally (Windows PowerShell)

Run the commands from the directory containing the `app`, `training`, and `frontend` directories.

### Create and activate the environment

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
```

Install a PyTorch build compatible with the installed Python version and NVIDIA driver, then install project dependencies:

```powershell
python -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu130
python -m pip install -r requirements.txt
```

If the CUDA wheel index above is not compatible with the local configuration, use the installer selector at <https://pytorch.org/get-started/locally/> to choose the correct command.

### Configure the dataset

Copy the CSV to `data/aa_dataset-tickets-multi-lang-5-2-50-version.csv`, then create `.env` from the template:

```powershell
Copy-Item .env.example .env
```

Set or verify:

```dotenv
SUPPORTPILOT_DATA_PATH=data/aa_dataset-tickets-multi-lang-5-2-50-version.csv
SUPPORTPILOT_OLLAMA_MODEL=gemma3:4b
```

### Train or reuse the saved classifiers

To reproduce the reported training runs, use:

```powershell
python training/train_classifier.py --target queue --epochs 3 --batch-size 4
python training/train_classifier.py --target priority --epochs 3 --batch-size 4
python training/train_classifier.py --target type --epochs 3 --batch-size 4
python training/train_tags.py --top-tags 30 --epochs 3 --batch-size 4
python training/train_textcnn.py --target queue --epochs 4 --batch-size 32
```

Training overwrites or recreates output artifacts depending on each script's configuration. If you already have the trained folders, reuse them instead of retraining. The reported logs saved checkpoints under `artifacts/queue`, `artifacts/priority`, `artifacts/type`, `artifacts/tags`, and `artifacts/textcnn_queue`.

If your existing artifacts live elsewhere, configure the `SUPPORTPILOT_ARTIFACTS_DIR` variable in `.env` to point to that directory and restart the app. Source-code archives may not include model weight files.

### Start FastAPI

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Open:

- Frontend: <http://127.0.0.1:8000/>
- API documentation: <http://127.0.0.1:8000/docs>
- Health check: <http://127.0.0.1:8000/health>

The exact routes available depend on the checked-out backend version. Use `/docs` to inspect the running API. If the UI's Model Performance page reports a missing metrics file, check the backend route's expected metrics path and the `training/model_metrics.json` file. Recorded metrics and installed model artifacts are separate: a metric can be present while its weights are missing.

## 11. Current limitations and next actions

1. **Improve queue and priority classifiers.** Inspect label quality, class imbalance, text construction from subject/body, duplicate leakage, and class-wise recall. Compare macro-F1 and confusion matrices in addition to accuracy.
2. **Do not claim the severity target is met.** Obtain or define a separate severity label and evaluate that task independently.
3. **Report tag metrics comprehensively.** Add micro/macro precision, recall, F1, and exact-match ratio where appropriate; keep the custom top-3 metrics clearly named.
4. **Measure API coverage and latency.** Record how many valid tickets the service processes successfully and how often model artifacts are unavailable.
5. **Verify integration end to end.** Create a ticket, confirm the database record, retrieve it, update its status, and verify dashboard counts.
6. **Keep human review enabled.** The measured queue and priority scores are not adequate for autonomous ticket routing or critical operational decisions.

## 12. Evidence files used for the score tables

The scores in this README were transcribed from these supplied logs:

- `train.txt` — XLM-RoBERTa queue classifier.
- `train1.txt` — XLM-RoBERTa priority classifier.
- `train2.txt` — XLM-RoBERTa priority and ticket-type classifier runs.
- `train3.txt` — multi-label tag classifier.
- `train4.txt` — TextCNN queue benchmark.

The project brief supplies Milestone 1 requirements and evaluation targets. No additional metrics have been inferred beyond formatting the logged proportions as percentages.
