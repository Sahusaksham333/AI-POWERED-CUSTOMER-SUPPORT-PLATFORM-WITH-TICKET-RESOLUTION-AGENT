# SupportPilot — AI-Powered Customer Support Platform with Ticket Resolution Agent

SupportPilot is a local-first, multilingual IT support-ticket application. It combines a web interface, FastAPI backend, SQLite persistence, supervised ticket classification, multi-label tagging, retrieval-augmented generation (RAG), and human-reviewed AI response drafting.

> **Project status and safety:** This repository is an MVP/scaffold, not a certified enterprise helpdesk. Predictions and generated responses are advisory and require human review. The system does not autonomously change production systems or close tickets. Jira and email actions are optional and only execute when their endpoints are explicitly called.

## Contents

- [Project objectives and milestones](#project-objectives-and-milestones)
- [Current repository structure](#current-repository-structure)
- [Architecture and capabilities](#architecture-and-capabilities)
- [Dataset and evaluation protocol](#dataset-and-evaluation-protocol)
- [Recorded model scores](#recorded-model-scores)
- [Milestone 1 acceptance review](#milestone-1-acceptance-review)
- [Requirements](#requirements)
- [Windows installation](#windows-installation)
- [Configuration](#configuration)
- [Training and model artifacts](#training-and-model-artifacts)
- [Knowledge-base indexing and RAG](#knowledge-base-indexing-and-rag)
- [Run SupportPilot](#run-supportpilot)
- [API endpoints](#api-endpoints)
- [Optional Jira and email integrations](#optional-jira-and-email-integrations)
- [Testing and code quality](#testing-and-code-quality)
- [Limitations and next steps](#limitations-and-next-steps)

## Project objectives and milestones

The supplied project brief defines the following four milestones.

| Milestone | Schedule | Intended scope |
|---|---|---|
| **1 — Ticket processing and classification** | Weeks 1–2 | Ticket submission, category/type/priority prediction, intake, and classification scores |
| **2 — Knowledge retrieval and response generation** | Weeks 3–4 | Knowledge-base search, RAG, grounded troubleshooting guidance, cited sources, and draft responses |
| **3 — Multi-agent workflows and integrations** | Weeks 5–6 | Coordinated diagnosis/retrieval/resolution flow, Jira ticket management, and email automation |
| **4 — Dashboard and optimization** | Weeks 7–8 | Analytics, escalation monitoring, end-to-end testing, performance optimization, and deployment preparation |

The brief's evaluation targets are requirements, not measured results: at least **90% ticket-classification success**, at least **85% severity-prediction accuracy**, working knowledge retrieval with source references, functioning Jira/email integrations, average response generation below five seconds, and a user-satisfaction score of at least 85%. The supplied logs do not establish that all these targets have been met.

## Current repository structure

The service modules in this version live under `app/supportpilot/`. This is the actual layout of this repository; it differs slightly from a conceptual structure that places these modules in `app/services/`.

```text
SupportPilot/
├── app/
│   ├── main.py                       # FastAPI entry point and frontend serving
│   ├── dashboard.py                  # Optional Streamlit developer dashboard
│   └── supportpilot/
│       ├── schemas.py                # Pydantic request/response schemas
│       ├── pipeline.py               # Ticket classification/resolution pipeline
│       ├── classifier.py             # Saved-model inference and model health
│       ├── generator.py              # Ollama response generation
│       ├── retriever.py              # Knowledge retrieval and Chroma search
│       ├── db.py                     # SQLite persistence and analytics
│       ├── config.py                 # Environment-based configuration
│       ├── data_utils.py             # Dataset/text preprocessing helpers
│       ├── policy.py                 # Escalation and safety-related decisions
│       └── integrations.py           # Optional Jira and SMTP integrations
├── training/
│   ├── train_classifier.py           # Single-label XLM-R classifier training
│   ├── train_tags.py                 # Multi-label tag-model training
│   ├── train_textcnn.py              # TextCNN queue baseline
│   ├── metrics_registry.py            # Evaluation-metric helpers
│   └── model_metrics.json             # Recorded historical test scores
├── frontend/
│   ├── index.html                    # Main SupportPilot UI
│   ├── style.css                     # Responsive frontend styles
│   └── script.js                     # API calls and UI behavior
├── artifacts/                        # Model checkpoints, SQLite DB, vector index
├── data/                             # Local dataset location (not bundled)
├── knowledge_base/                   # Approved troubleshooting source documents
├── scripts/
│   ├── check_environment.py          # Environment checks
│   └── index_knowledge_base.py        # Index documents for RAG retrieval
├── tests/                            # Automated tests
├── .env.example                      # Configuration template; no real secrets
├── requirements.txt                  # Python dependencies
├── pyproject.toml                    # Tool/test configuration
└── README.md
```

## Architecture and capabilities

### Ticket intake and classification

The HTML/CSS/JavaScript frontend is served by FastAPI so requests can use same-origin API paths. A ticket can include a subject, description, language, requester details, business-impact selection, and preferred contact method. The pipeline can use saved XLM-RoBERTa models for `queue`, `priority`, and `type`, plus a multi-label tag model where compatible artifacts are available.

### Retrieval and response drafts

The retrieval layer indexes knowledge-base documents into a persistent Chroma collection using multilingual sentence embeddings. The generation layer calls a local Ollama model to prepare a response draft. Retrieved sources should be reviewed and approved; the sample knowledge-base article is illustrative, not authoritative company policy.

### Persistence, monitoring, and integrations

Ticket records and workflow status are stored in SQLite. The backend exposes ticket listing, retrieval, status updates, analytics, health checks, and a historical model-performance endpoint. Jira Cloud and SMTP are optional integrations requiring explicit configuration and endpoint calls.

## Dataset and evaluation protocol

The recorded experiments used `aa_dataset-tickets-multi-lang-5-2-50-version.csv`. Training logs report **28,587 rows** split into **22,869 training**, **2,859 validation**, and **2,859 held-out test** examples (approximately 80/10/10). The source schema includes fields such as `subject`, `body`, `answer`, `type`, `queue`, `priority`, `language`, and `tag_1` through `tag_8`.

The single-label experiments use `FacebookAI/xlm-roberta-base` for `queue`, `priority`, and `type`. The tag experiment predicts a restricted set of the 30 most frequent tags. TextCNN is a separate queue-classification benchmark. The scores below are transcribed into `training/model_metrics.json` from the supplied training logs. They are historical evaluations—not a live benchmark—and should not be treated as a guarantee for future tickets.

## Recorded model scores

All single-label test reports below use the same reported held-out test set of **2,859 examples**.

| Task | Model | Accuracy / primary metric | Macro F1 | Weighted F1 / overlap | Assessment |
|---|---|---:|---:|---:|---|
| Queue classification | XLM-RoBERTa-base | **48.00% accuracy** | 37.00% | 46.00% weighted F1 | Needs improvement; uneven class recall |
| Priority classification | XLM-RoBERTa-base | **51.00% accuracy** | 45.00% | 49.00% weighted F1 | Needs improvement; low-priority recall is weak |
| Ticket-type classification | XLM-RoBERTa-base | **85.00% accuracy** | 85.00% | 84.00% weighted F1 | Strongest reported single-label result |
| Multi-label tags (top 30) | XLM-RoBERTa-base | **98.98% top-3 hit rate** | Not reported | 62.84% top-3 overlap ratio | Interpret metric definitions carefully |
| Queue benchmark | TextCNN | **46.00% accuracy** | 37.00% | 43.00% weighted F1 | Baseline; below XLM-R queue accuracy |

### Important interpretation of tag metrics

The reported **98.98% top-3 hit rate does not mean 98.98% of all predicted tags are correct**. It means the supplied evaluation metric found at least one relevant tag within the top three predictions. The separate top-3 overlap ratio is **62.84%**. The logs do not provide tag macro-F1, micro-F1, exact-match accuracy, or per-label average precision, so those metrics should not be inferred from the two reported numbers.

### Queue classifier — validation and per-class test results

Validation progression:

| Epoch | Validation loss | Validation accuracy | Validation macro F1 | Validation weighted F1 |
|---:|---:|---:|---:|---:|
| 1 | 1.5863 | 41.62% | 28.73% | 39.21% |
| 2 | 1.5023 | 44.74% | 33.31% | 41.87% |
| 3 | 1.4824 | 46.03% | 35.90% | 43.54% |

Held-out per-class results:

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
| **Macro average** | **50%** | **35%** | **37%** | **2,859** |
| **Weighted average** | **48%** | **48%** | **46%** | **2,859** |

General Inquiry and Human Resources have especially weak recall. Queue results should remain advisory, with a human reviewing uncertain or consequential cases.

### Priority classifier — validation and per-class test results

Validation progression:

| Epoch | Validation loss | Validation accuracy | Validation macro F1 | Validation weighted F1 |
|---:|---:|---:|---:|---:|
| 1 | 1.0347 | 46.41% | 34.12% | 40.67% |
| 2 | 1.0041 | 48.13% | 35.76% | 42.59% |
| 3 | 0.9852 | 50.75% | 45.35% | 49.03% |

Held-out per-class results:

| Priority | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| High | 60% | 59% | 60% | 1,118 |
| Low | 40% | 16% | 23% | 589 |
| Medium | 47% | 61% | 53% | 1,152 |
| **Macro average** | **49%** | **46%** | **45%** | **2,859** |
| **Weighted average** | **50%** | **51%** | **49%** | **2,859** |

Low-priority recall is 16%, suggesting substantial class confusion. The score is not a calibrated business-risk or severity probability.

### Ticket-type classifier — validation and per-class test results

Validation progression:

| Epoch | Validation loss | Validation accuracy | Validation macro F1 | Validation weighted F1 |
|---:|---:|---:|---:|---:|
| 1 | 0.3756 | 81.08% | 83.16% | 81.33% |
| 2 | 0.3520 | 82.65% | 83.86% | 82.56% |
| 3 | 0.3661 | 84.47% | 85.45% | 84.29% |

Held-out per-class results:

| Ticket type | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| Change | 98% | 98% | 98% | 292 |
| Incident | 80% | 83% | 82% | 1,147 |
| Problem | 66% | 60% | 63% | 601 |
| Request | 99% | 99% | 99% | 819 |
| **Macro average** | **86%** | **85%** | **85%** | **2,859** |
| **Weighted average** | **84%** | **85%** | **84%** | **2,859** |

Ticket type is the best-performing reported single-label model. Some classes (especially Problem) still trail Change and Request.

### Multi-label tags — top-30 model

| Metric | Validation epoch 3 | Held-out test |
|---|---:|---:|
| Evaluation loss | 0.1492 | Not separately reported |
| Top-3 hit rate | 98.88% | 98.98% |
| Top-3 overlap ratio | 62.35% | 62.84% |

The run used 22,869 train, 2,859 validation, and 2,859 test examples. The top-30 tag vocabulary for this run was: `Tech Support`, `IT`, `Performance`, `Feedback`, `Bug`, `Security`, `Feature`, `Documentation`, `Disruption`, `Outage`, `Network`, `Product`, `Recovery`, `Sales`, `Hardware`, `Billing`, `Support`, `Payment`, `Marketing`, `Maintenance`, `Crash`, `Software`, `Integration`, `Virus`, `Account`, `Strategy`, `Refund`, `Alert`, `Compliance`, and `Campaign`.

### TextCNN queue benchmark — validation and per-class test results

| Epoch | Training loss | Validation accuracy | Validation macro F1 |
|---:|---:|---:|---:|
| 1 | 1.9343 | 39.49% | 21.87% |
| 2 | 1.7302 | 42.67% | 30.18% |
| 3 | 1.5532 | 43.62% | 35.50% |
| 4 | 1.3105 | 44.74% | 37.06% |

Held-out per-class results:

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
| **Macro average** | **57%** | **36%** | **37%** | **2,859** |
| **Weighted average** | **52%** | **46%** | **43%** | **2,859** |

For this experiment, XLM-R queue classification outperformed TextCNN on accuracy (48% vs. 46%) and weighted F1 (46% vs. 43%). TextCNN is retained as a baseline comparison, not the preferred online queue model.

## Milestone 1 acceptance review

| Criterion from project brief | Target | Available evidence | Assessment |
|---|---|---|---|
| Ticket submission/intake | Submission and ingestion work | Form and FastAPI endpoints are present; run end-to-end tests locally | Needs runtime verification |
| Ticket classification | ≥90% successful classification | Queue accuracy 48%; type accuracy 85%; priority accuracy 51% | Not demonstrated if interpreted as prediction accuracy |
| Severity prediction | ≥85% severity accuracy | Logs evaluate `priority`; no separate verified severity label/model is reported | Not verified |
| Priority assignment | Assign priority to a ticket | Priority classifier test accuracy 51% | Feature exists; quality needs improvement |
| Ticket tracking | Persist tickets and workflow status | SQLite and status-update endpoint are included | Verify against the local database |

The brief's phrase “successfully classify ≥90% of support tickets” may refer to processing coverage, while the model logs report prediction accuracy. These are different measures. Measure API coverage separately rather than equating it with model accuracy. The dataset contains `priority`, not a separately verified `severity` target; therefore, the priority scores do not prove that the severity target is met.

## Requirements

- Windows 10/11 or another supported Python environment
- Python 3.11 recommended
- PyTorch version compatible with the Python version and NVIDIA driver, if training on GPU
- NVIDIA GPU is optional; CPU inference/training may be slower
- Ollama installed separately for local LLM response generation
- Dataset file supplied separately

The Python package `ollama`/LangChain client libraries do not install the Ollama server itself. Install the server from <https://ollama.com/download/windows>.

## Windows installation

Run PowerShell in the folder containing `app`, `training`, and `frontend`.

### 1. Create the virtual environment

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
```

If `py -3.11` is unavailable, install Python 3.11 first, reopen PowerShell, and check `py --list`.

### 2. Install PyTorch and dependencies

Choose a PyTorch wheel compatible with your actual system at <https://pytorch.org/get-started/locally/>. The following is an example only; use a different index if it is not compatible with your driver/runtime:

```powershell
python -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu130
python -m pip install -r requirements.txt
```

Check the environment:

```powershell
python scripts/check_environment.py
python -c "import torch; print('PyTorch:', torch.__version__); print('CUDA available:', torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU mode')"
```

### 3. Add the dataset and local configuration

Copy `aa_dataset-tickets-multi-lang-5-2-50-version.csv` into `data/` (or set a different path). Create the local `.env` file:

```powershell
Copy-Item .env.example .env
```

Do not commit `.env` or put real credentials into it in shared repositories.

## Configuration

The `.env.example` file documents supported values. Common settings:

```dotenv
SUPPORTPILOT_DATA_PATH=data/aa_dataset-tickets-multi-lang-5-2-50-version.csv
SUPPORTPILOT_ARTIFACTS_DIR=artifacts
SUPPORTPILOT_KNOWLEDGE_DIR=knowledge_base
SUPPORTPILOT_CHROMA_DIR=artifacts/chroma
SUPPORTPILOT_DB_PATH=artifacts/supportpilot.db
SUPPORTPILOT_EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
SUPPORTPILOT_OLLAMA_URL=http://localhost:11434
SUPPORTPILOT_OLLAMA_MODEL=gemma3:4b
SUPPORTPILOT_TOP_K=4
SUPPORTPILOT_MAX_NEW_TOKENS=512
SUPPORTPILOT_MIN_CLASSIFIER_CONFIDENCE=0.55
```

Relative paths resolve from the project root. To reuse previously trained model directories, set `SUPPORTPILOT_ARTIFACTS_DIR` to the full path of the old `artifacts` directory, then restart FastAPI. Use forward slashes in Windows `.env` paths to avoid escaping issues, for example:

```dotenv
SUPPORTPILOT_ARTIFACTS_DIR=S:/A Projects/AI-Powered Customer Support Platform with Ticket Resolution Agent/SupportPilot-codebase/SupportPilot/artifacts
```

## Training and model artifacts

If you already have compatible trained model weights, copy them or configure the artifacts path; retraining is not required merely to run the frontend. To reproduce the logged training runs, execute one model at a time:

```powershell
python training/train_classifier.py --target queue --epochs 3 --batch-size 4
python training/train_classifier.py --target priority --epochs 3 --batch-size 4
python training/train_classifier.py --target type --epochs 3 --batch-size 4
python training/train_tags.py --top-tags 30 --epochs 3 --batch-size 4
python training/train_textcnn.py --target queue --epochs 4 --batch-size 32
```

Model artifacts are expected beneath:

```text
artifacts/
├── queue/             # XLM-R model/tokenizer/config
├── priority/          # XLM-R model/tokenizer/config
├── type/              # XLM-R model/tokenizer/config
├── tags/              # Multi-label tag model and label metadata
├── textcnn_queue/     # TextCNN benchmark checkpoint and tokenizer
└── chroma/            # Persistent knowledge-base vector index
```

The TextCNN checkpoint is a benchmark and is not the online queue classifier in the current pipeline. A model score recorded in `training/model_metrics.json` does not mean the corresponding model weights are present. The Model Performance view separates historical scores from live artifact availability.

**GPU memory guidance:** XLM-RoBERTa-base fine-tuning can consume substantial memory. Start with batch size 4, reduce to 2 or shorten sequence length if necessary, and avoid training a transformer while running a generative model on the same 8 GB GPU. Inspect the training scripts' CLI options before changing settings. The test scores listed here should not be attributed to a run with different data splits or hyperparameters without re-evaluation.

## Knowledge-base indexing and RAG

Replace the sample article in `knowledge_base/` with approved, maintained internal troubleshooting documents. The indexer supports `.md`, `.txt`, `.pdf`, and `.docx` according to the included script; scanned PDFs without text extraction are not automatically OCRed.

```powershell
ollama pull gemma3:4b
python scripts/index_knowledge_base.py --reset
```

Start Ollama and confirm it responds at `http://localhost:11434`. The first embedding-model run may download model files. Re-run the indexer after updating knowledge documents. `--reset` rebuilds the collection; consult `python scripts/index_knowledge_base.py --help` before changing indexing options.

## Run SupportPilot

From the project root, activate `.venv` and start FastAPI:

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Keep that terminal open while using the app. Open these addresses:

- **Frontend:** <http://127.0.0.1:8000/>
- **Interactive API docs:** <http://127.0.0.1:8000/docs>
- **Health and model availability:** <http://127.0.0.1:8000/health>
- **Historical model evaluation and artifact status:** <http://127.0.0.1:8000/models/performance>

If the frontend reports “Training metrics file was not found”, verify `training/model_metrics.json` exists at the configured project root and restart the API. A missing metrics registry and missing model weights are separate problems. If the browser reports `ERR_CONNECTION_REFUSED`, first check that the Uvicorn process started successfully and remains running.

The optional Streamlit developer dashboard can be started separately with `streamlit run app/dashboard.py` while the API is available. The HTML/CSS/JavaScript frontend is the primary web UI.

## API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | API and model health status |
| `POST` | `/tickets/predict` | Predict queue, type, priority, and tags when compatible artifacts are available |
| `POST` | `/tickets/resolve` | Run ticket analysis, retrieve sources, and draft a response |
| `GET` | `/tickets?limit=250` | List saved tickets |
| `GET` | `/tickets/{ticket_id}` | Retrieve a saved ticket |
| `PATCH` | `/tickets/{ticket_id}/status` | Update workflow status to Open, In Progress, or Resolved |
| `GET` | `/analytics` | Read ticket analytics from SQLite |
| `GET` | `/models/performance` | Return historical metrics and current artifact checks |
| `POST` | `/integrations/jira` | Explicitly create a Jira issue for a saved ticket |
| `POST` | `/integrations/email` | Explicitly send a ticket email using configured SMTP settings |

Example ticket body for `POST /tickets/predict`:

```json
{
  "subject": "VPN connection fails after sign-in",
  "body": "I can access the internet, but the VPN client fails with an authentication error.",
  "language": "en",
  "requester_name": "Example User",
  "requester_email": "user@example.com",
  "business_impact": "medium",
  "contact_method": "Email"
}
```

Use the live `/docs` page to verify the request schema for the version you are running. Do not send real passwords, access tokens, or other secrets in ticket descriptions.

## Optional Jira and email integrations

Fill in only the integration settings you need in `.env`. The endpoint calls are explicit; ticket submission does not automatically create Jira issues or send email.

For Jira Cloud, configure:

- `SUPPORTPILOT_JIRA_BASE_URL`
- `SUPPORTPILOT_JIRA_EMAIL`
- `SUPPORTPILOT_JIRA_API_TOKEN`
- `SUPPORTPILOT_JIRA_PROJECT_KEY`
- `SUPPORTPILOT_JIRA_ISSUE_TYPE`

For SMTP, configure:

- `SUPPORTPILOT_SMTP_HOST`
- `SUPPORTPILOT_SMTP_PORT`
- `SUPPORTPILOT_SMTP_USERNAME`
- `SUPPORTPILOT_SMTP_PASSWORD`
- `SUPPORTPILOT_SMTP_FROM`

Use test Jira projects and a development mailbox first. Apply least-privilege permissions and never commit secrets.

## Testing and code quality

Run tests from the project root:

```powershell
pytest -q
ruff check app training scripts tests
```

A successful test suite verifies only what those tests cover; it does not establish model accuracy or prove that external Jira/SMTP credentials work. For a full smoke test, start the backend, check `/health`, create a ticket, retrieve it, update its status, inspect `/analytics`, and test RAG with an approved knowledge document.

## Limitations and next steps

1. **Improve queue and priority models.** The held-out macro F1 scores are 37% and 45% respectively. Examine label imbalance, class-level recall, duplicated examples, language-specific error rates, thresholding, and data quality before deployment.
2. **Keep target labels distinct.** The dataset reports `priority`; there is no separately validated `severity` label in the supplied logs. Do not claim the brief's severity target has been met without a severity-labeled evaluation.
3. **Complete evaluation of tags.** Add micro/macro F1, precision-recall analysis, per-label metrics, and threshold validation. Do not use top-3 hit rate alone as tag accuracy.
4. **Validate generation quality and latency.** Measure factuality, source relevance, refusal/escalation behavior, and end-to-end response time on a held-out ticket set; do not assume the brief's under-five-second target is achieved.
5. **Secure before deployment.** Add authentication, authorization, request-rate limits, audit retention, secret-management policy, database migrations, monitoring, backups, model versioning, and a security review.
6. **Review knowledge sources.** Replace the sample troubleshooting article with accurate approved organizational content and establish a process for updating indexed documents.
7. **Keep humans in the loop.** Escalate security incidents, outages, low-confidence predictions, and unsupported solutions to a qualified support engineer.

## Acknowledgement of measured vs. target results

The score tables above summarize the supplied historical training logs and the project's metrics registry. Project-brief targets and illustrative screenshots are specifications, not empirical evidence. Recalculate metrics after any change to the dataset, split, preprocessing, label mapping, checkpoint, or hyperparameters, and record the test-set provenance with each run.
